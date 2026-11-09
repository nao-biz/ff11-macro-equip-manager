"""Repeated production save/reload checks using an existing private replica only."""
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
    base = (ROOT/'work/stack-evaluation'/('cycles-'+uuid4().hex)).resolve()
    base.mkdir()
    mirror = base/'replica'
    violations = []
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
        token_macro = next(m for m in chosen.macros if any(t.tokens for t in m.lines)
                           and any(not t.tokens for t in m.lines))
        address = macro_key(token_macro)
        number = chosen.equipsets[0].number
        candidates = [(name, r) for name in ('head', 'body', 'hands', 'feet', 'main')
                      for r in chosen.inventory if name in snapshot.items.get(r.item_id, {}).get('equip_slots', ())]
        assert candidates
        slot, inventory = candidates[0]
        initial_values = snapshot_value(snapshot)
        for cycle, action in enumerate(('equip', 'remove', 'keep'), 1):
            editor = Editor(snapshot, base/f'session-{cycle}.json', root=mirror)
            assert not editor.session.dirty
            before = fingerprints(mirror)
            start = time.perf_counter()
            macro = editor._session.read(folder, 'macros', address)
            lines = list(macro.lines)
            line_index = next(i for i, line in enumerate(lines) if not line.tokens)
            lines[line_index] = Text(f'/echo persist-{cycle}', '', 'draft')
            editor.apply(editor.prepare_macro_edit(folder, address, f'Cycle{cycle}', lines))
            editor.apply(editor.prepare_equipment_name_edit(folder, number, f'Persist {cycle}'))
            selection = (inventory.item_id, inventory.container, inventory.index) if action == 'equip' else None
            editor.apply(editor.prepare_equipment_slot_edit(folder, number, slot, action, selection))
            expected = snapshot_value(editor.snapshot())
            edit_seconds = time.perf_counter()-start
            start = time.perf_counter()
            plans = editor.prepare_writeback()
            targets = {str(Path(f.target).relative_to(mirror)): f for p in plans for f in p.files}
            assert len(targets) == 2
            for plan in plans:
                assert all(Path(p).resolve().is_relative_to(mirror) for p, _ in plan.dependencies)
            backups = editor.writeback(plans, base/'backups')
            save_seconds = time.perf_counter()-start
            assert not editor.session.dirty
            after = fingerprints(mirror)
            assert {p for p in before if before[p] != after[p]} == set(targets)
            for relative, file in targets.items():
                assert (mirror/relative).read_bytes() == file.replacement
            for backup in backups:
                backup = Path(backup)
                receipt = json.loads((backup/'receipt.json').read_text(encoding='utf-8'))
                assert (backup/'verified.json').exists()
                for item in receipt['files']:
                    assert hashlib.sha256((backup/item['backup']).read_bytes()).hexdigest() == item['before_sha256']
            start = time.perf_counter()
            snapshot = (load_snapshot(mirror, snapshot.master_data) if '--reuse-masters' in sys.argv
                        else load_snapshot(mirror))
            reload_seconds = time.perf_counter()-start
            assert snapshot_value(snapshot) == expected
            if '--reuse-masters' in sys.argv:
                # Independent restart verifies disk contents without the shared master.
                restarted = load_snapshot(mirror)
                assert snapshot_value(restarted) == expected
                assert restarted.items == snapshot.items and restarted.phrases == snapshot.phrases
            reopened = Editor(snapshot, base/f'reopened-{cycle}.json', root=mirror)
            assert not reopened.session.dirty and reopened.prepare_writeback() == ()
            assert reopened.session.history_length() == 0
            # Every unedited character remains semantically identical across all cycles.
            assert all(snapshot_value(snapshot)[f] == values for f, values in initial_values.items() if f != folder)
            row = dict(cycle=cycle, slot_action=action, written_files=len(targets),
                       edit_seconds=edit_seconds, save_seconds=save_seconds, reload_seconds=reload_seconds,
                       all_models_equal=True, untouched_files_equal=True, clean_after_reopen=True)
            rows.append(row)
            print(json.dumps(row), flush=True)
    assert fingerprints(source) == original_hashes and not violations
    result = dict(source_files=len(original_hashes), characters=len(snapshot.characters),
                  macros=sum(len(c.macros) for c in snapshot.characters),
                  equipment_sets=sum(len(c.equipsets) for c in snapshot.characters),
                  initial_load_seconds=initial_load, reuse_masters='--reuse-masters' in sys.argv, cycles=rows, source_copy_unchanged=True,
                  guard_violations=violations, live_directory_access=False)
    (base/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('RESULT '+str(base/'results.json'), flush=True)


if __name__ == '__main__': main()
