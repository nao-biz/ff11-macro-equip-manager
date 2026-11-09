"""Single-slot editing and persistence timing using an existing private replica only."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import os
import json
import shutil
import hashlib
import time
from uuid import uuid4
from contextlib import ExitStack
from unittest.mock import patch
from ff11reader.application import load_snapshot
from ff11reader.edit_application import Editor
from ff11reader.editing import macro_key
from ff11reader.edit_values import snapshot_value
from ff11reader.domain import Text


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    source = (ROOT/'work/stack-evaluation/real-9709a6c3e21c4d4398eb2e3118b4cb99/game').resolve()
    assert source.is_relative_to(ROOT/'work') and source.is_dir()
    base = (ROOT/'work/stack-evaluation'/('single-slot-'+uuid4().hex)).resolve()
    base.mkdir()
    mirror = base/'replica'
    violations = []
    active = [None]
    reads = {}
    def timed(label, operation):
        active[0] = label
        reads[label] = set()
        start = time.perf_counter()
        try: return operation(), time.perf_counter()-start
        finally: active[0] = None
    allowed_reads = (ROOT, Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve())

    def guard(event, args):
        writes = []
        if event == 'open':
            if isinstance(args[0], int): return
            path = Path(args[0]).resolve()
            if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                writes = [path]
            elif not any(path.is_relative_to(root) for root in allowed_reads):
                violations.append(event)
                raise PermissionError('Read outside replica/code roots')
            if active[0] and path.is_relative_to(mirror) and not args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                reads[active[0]].add(str(path.relative_to(mirror)))
        elif event in ('os.listdir', 'os.scandir'):
            if isinstance(args[0], int): return
            path = Path(args[0]).resolve()
            if not any(path.is_relative_to(root) for root in allowed_reads):
                violations.append(event)
                raise PermissionError('Directory access outside replica/code roots')
        elif event in ('os.remove', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.utime'):
            writes = [Path(args[0]).resolve()]
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            writes = [Path(p).resolve() for p in args[:2]]
        for path in writes:
            if not path.is_relative_to(base):
                violations.append(event)
                raise PermissionError('Write outside isolated run')

    sys.addaudithook(guard)
    original_hashes = fingerprints(source)
    shutil.copytree(source, mirror)
    assert fingerprints(mirror) == original_hashes
    rows = []
    with ExitStack() as stack:
        for module in ('saving', 'macro_saving', 'equipment_saving', 'combined_saving'):
            stack.enter_context(patch('ff11reader.'+module+'.require_game_closed', return_value=None))
        stack.enter_context(patch('ff11reader.application.installations', side_effect=AssertionError('No discovery')))
        start = time.perf_counter()
        snapshot = load_snapshot(mirror)
        initial_load = time.perf_counter()-start
        chosen = max((c for c in snapshot.characters if c.equipsets and c.inventory), key=lambda c:len(c.macros))
        folder = chosen.folder_id
        number = chosen.equipsets[0].number
        candidates = [(name, r) for name in ('head', 'body', 'hands', 'feet', 'main')
                      for r in chosen.inventory if name in snapshot.items.get(r.item_id, {}).get('equip_slots', ())]
        assert candidates
        slot, inventory = candidates[0]
        initial_values = snapshot_value(snapshot)
        initial_action = next(s.action for s in chosen.equipsets[0].slots if s.name == slot)
        actions = ('equip', 'remove', 'keep') if initial_action != 'equip' else ('remove', 'equip', 'keep')
        for cycle, action in enumerate(actions, 1):
            editor = Editor(snapshot, base/f'session-{cycle}.json', root=mirror)
            assert not editor.session.dirty
            before = fingerprints(mirror)
            selection = (inventory.item_id, inventory.container, inventory.index) if action == 'equip' else None
            edit, prepare_edit_seconds = timed('prepare_edit', lambda: editor.prepare_equipment_slot_edit(folder, number, slot, action, selection))
            _, apply_seconds = timed('apply_edit', lambda: editor.apply(edit))
            expected = snapshot_value(editor.snapshot())
            plans, preview_seconds = timed('preview', editor.prepare_writeback)
            targets = {str(Path(f.target).relative_to(mirror)): f for p in plans for f in p.files}
            assert len(targets) == 1
            assert all(plan.macro is None for plan in plans)
            for plan in plans:
                assert all(Path(p).resolve().is_relative_to(mirror) for p, _ in plan.dependencies)
            backups, save_seconds = timed('writeback', lambda: editor.writeback(plans, base/'backups'))
            assert not editor.session.dirty
            after = fingerprints(mirror)
            assert {p for p in before if before[p] != after[p]} == set(targets)
            for relative, file in targets.items():
                assert (mirror/relative).read_bytes() == file.replacement
                from ff11reader.edit_values import SLOT_NAMES
                offset = 24+(number-1)%20*80+16+SLOT_NAMES.index(slot)*4
                changed_bytes = [i for i,(a,b) in enumerate(zip(file.original,file.replacement)) if a != b]
                assert set(changed_bytes) <= set(range(8,24)) | set(range(offset,offset+4))
                assert len(file.original) == len(file.replacement) == 1624
            for backup in backups:
                backup = Path(backup)
                receipt = json.loads((backup/'receipt.json').read_text(encoding='utf-8'))
                assert (backup/'verified.json').exists()
                for item in receipt['files']:
                    assert hashlib.sha256((backup/item['backup']).read_bytes()).hexdigest() == item['before_sha256']
            snapshot, reload_seconds = timed('reload', lambda: load_snapshot(mirror))
            reloaded_values = snapshot_value(snapshot)
            assert reloaded_values == expected
            reopened = Editor(snapshot, base/f'reopened-{cycle}.json', root=mirror)
            assert not reopened.session.dirty and reopened.prepare_writeback() == ()
            assert reopened.session.history_length() == 0
            # Every unedited character remains semantically identical across all cycles.
            assert all(reloaded_values[f] == values for f, values in initial_values.items() if f != folder)
            row = dict(cycle=cycle, slot_action=action, written_files=len(targets),
                       prepare_edit_seconds=prepare_edit_seconds, apply_seconds=apply_seconds,
                       preview_seconds=preview_seconds, save_seconds=save_seconds, reload_seconds=reload_seconds,
                       unique_read_files={k:len(v) for k,v in reads.items()},
                       bytes_replaced=1624, changed_byte_count=len(changed_bytes), slot_and_checksum_only=True,
                       all_models_equal=True, untouched_files_equal=True, clean_after_reopen=True)
            rows.append(row)
            print(json.dumps(row), flush=True)
    assert fingerprints(source) == original_hashes and not violations
    result = dict(source_files=len(original_hashes), characters=len(snapshot.characters),
                  macros=sum(len(c.macros) for c in snapshot.characters),
                  equipment_sets=sum(len(c.equipsets) for c in snapshot.characters),
                  initial_load_seconds=initial_load, cycles=rows, source_copy_unchanged=True,
                  guard_violations=violations, live_directory_access=False)
    (base/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('RESULT '+str(base/'results.json'), flush=True)


if __name__ == '__main__': main()
