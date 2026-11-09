"""Real-data writeback measurement in an isolated, disposable-path replica.
Only aggregates are suitable for Git. Copied data and traces stay under work/.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import os
import json
import time
import hashlib
import dataclasses
import statistics
import tkinter as tk
from contextlib import ExitStack
from unittest.mock import patch
from uuid import uuid4
from ff11reader.application import installations, load_snapshot
from ff11reader.edit_application import Editor
from ff11reader.editing import macro_key
from ff11reader.ui import ReaderWindow
from ff11reader import combined_saving, macro_saving, equipment_saving


def main():
    roots = installations()
    assert len(roots) == 1, 'Specify a unique installation before measuring'
    live = Path(roots[0]).resolve()
    base = (ROOT / 'work/stack-evaluation' / ('real-' + uuid4().hex)).resolve()
    base.mkdir(parents=True)
    mirror = base / 'game'; mirror.mkdir()
    phase = ['copy']; violations = []
    # Refuse Python filesystem mutations anywhere except this measurement folder.
    # Also forbid reads from the live installation during the actual benchmark.
    def guard(event, args):
        paths = []
        if event == 'open':
            path, mode, flags = args
            if isinstance(path, int): return
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            path = Path(path).resolve()
            if write: paths = [path]
            elif phase[0] == 'measure' and path.is_relative_to(live):
                violations.append('live read'); raise PermissionError('Live read during measurement')
        elif event in ('os.remove', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.utime'):
            paths = [Path(args[0]).resolve()]
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            paths = [Path(args[0]).resolve(), Path(args[1]).resolve()]
        for path in paths:
            if not path.is_relative_to(base):
                violations.append('outside write'); raise PermissionError('Write outside isolated measurement folder')
    sys.addaudithook(guard)
    print('Reading source snapshot (read only)', flush=True)
    snapshot = load_snapshot(live)
    hashes = {}; total_bytes = 0
    for source in snapshot.sources:
        original = Path(source['path']).resolve()
        assert original.is_relative_to(live)
        raw = original.read_bytes(); fingerprint = hashlib.sha256(raw).hexdigest()
        assert fingerprint == source['sha256'], 'Source changed while copying'
        destination = mirror / original.relative_to(live)
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw)
        hashes[original] = fingerprint; total_bytes += len(raw)
    def relocate(value):
        if isinstance(value, str) and value.casefold().startswith(str(live).casefold()):
            return str(mirror / Path(value).relative_to(live))
        if dataclasses.is_dataclass(value):
            return dataclasses.replace(value, **{f.name: relocate(getattr(value, f.name)) for f in dataclasses.fields(value)})
        if isinstance(value, dict): return {k: relocate(v) for k,v in value.items()}
        if isinstance(value, list): return [relocate(v) for v in value]
        if isinstance(value, tuple): return tuple(relocate(v) for v in value)
        return value
    snapshot = relocate(snapshot)
    assert str(live).casefold() not in repr(snapshot).casefold()
    selected = max(snapshot.characters, key=lambda c: len(c.macros))
    editor = Editor(snapshot, base / 'session.json')
    app = tk.Tk(); errors = []; active = [None]; stages = []
    app.report_callback_exception = lambda *args: errors.append(str(args[0]))
    def timed(name, operation):
        def invoke(*args, **kwargs):
            started = time.perf_counter()
            try: return operation(*args, **kwargs)
            finally:
                if active[0] is not None:
                    stages.append(dict(sample=active[0],stage=name,ms=(time.perf_counter()-started)*1000))
        return invoke
    real_writeback = editor.writeback
    def save(plans, _backup):
        for plan in plans:
            assert all(Path(f.target).resolve().is_relative_to(mirror) for f in plan.files)
            assert all(Path(p).resolve().is_relative_to(mirror) for p,_ in plan.dependencies)
        return real_writeback(plans, base / 'backups')
    rows = []
    try:
        with ExitStack() as stack:
            # Copied files are isolated, so running-game detection is irrelevant.
            for module in ('saving','macro_saving','equipment_saving','combined_saving'):
                stack.enter_context(patch('ff11reader.'+module+'.require_game_closed', return_value=None))
            stack.enter_context(patch('ff11reader.ui.dialogs.showerror', side_effect=RuntimeError('UI error; see private local log')))
            stack.enter_context(patch.object(editor, 'writeback', side_effect=timed('backend.writeback',save)))
            for name in ('prepare_writeback','prepare_combined_save','save_combined','_save_checkpoint','snapshot'):
                stack.enter_context(patch.object(editor,name,side_effect=timed('editor.'+name,getattr(editor,name))))
            for module, name in ((combined_saving,'execute_batch'),(macro_saving,'validate_macro_plan'),(equipment_saving,'validate_equipment_plan')):
                stack.enter_context(patch.object(module,name,side_effect=timed(name,getattr(module,name))))
            for name in ('fsync','replace'):
                stack.enter_context(patch.object(os,name,side_effect=timed('os.'+name,getattr(os,name))))
            view = ReaderWindow(app,snapshot,editor=editor)
            view.character_choice.current(snapshot.characters.index(selected)); view.change_character()
            view.tabs.select('マクロ'); app.update()
            stack.enter_context(patch.object(view,'refresh_edits',side_effect=timed('ui.refresh_edits',view.refresh_edits)))
            phase[0] = 'measure'
            # Distinct palette files: compare 1-file and 20-file saves.
            macros = [m for m in selected.macros if m.bank=='ctrl' and m.key==1][:20]
            assert len(macros)==20
            for count in (1,20):
                for iteration in range(3):
                    for index, macro in enumerate(macros[:count]):
                        current = next(m for m in editor.snapshot().characters[snapshot.characters.index(selected)].macros if macro_key(m)==macro_key(macro))
                        editor.apply(editor.prepare_macro_edit(selected.folder_id,macro_key(current),f'B{count}{iteration}{index}',current.lines))
                    view.refresh_edits(); app.update()
                    for operation in ('save_preview','writeback'):
                        sample = f'{count}-{iteration}-{operation}'; active[0] = sample
                        start = last = time.perf_counter(); gaps = []; timer = [None]
                        def tick():
                            nonlocal last
                            now=time.perf_counter(); gaps.append((now-last)*1000); last=now
                            timer[0]=app.after(10,tick)
                        timer[0]=app.after(10,tick)
                        if operation=='save_preview': view.save_button.invoke()
                        else:
                            preview=app.grab_current(); assert isinstance(preview,tk.Toplevel)
                            preview.accept_button.invoke()
                        app.update_idletasks(); app.update()
                        end=time.perf_counter(); gaps.append((end-last)*1000); app.after_cancel(timer[0]); active[0]=None
                        rows.append(dict(sample=sample,changed_macros=count,iteration=iteration,operation=operation,elapsed_ms=(end-start)*1000,max_event_gap_ms=max(gaps)))
                        assert not errors, errors
                        print(json.dumps(rows[-1]),flush=True)
                    assert not editor.session.dirty
                    # Independent byte checks against the production save receipts.
                    for folder in (base/'backups').iterdir():
                        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
                        assert (folder/'verified.json').exists()
                    latest=max((base/'backups').iterdir(),key=lambda p:p.stat().st_mtime_ns)
                    receipt=json.loads((latest/'receipt.json').read_text(encoding='utf-8'))
                    assert len(receipt['files']) == count
                    for item in receipt['files']:
                        assert hashlib.sha256(Path(item['target']).read_bytes()).hexdigest()==item['after_sha256']
                        assert hashlib.sha256((latest/item['backup']).read_bytes()).hexdigest()==item['before_sha256']
    finally:
        app.destroy()
        phase[0]='verify'
        unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in hashes.items())
        result=dict(source_files=len(hashes),copied_bytes=total_bytes,characters=len(snapshot.characters),
                    macros=sum(len(c.macros) for c in snapshot.characters),inventory_rows=sum(len(c.inventory) for c in snapshot.characters),
                    selected_macros=len(selected.macros),rows=rows,stages=stages,source_hashes_unchanged=unchanged,
                    guard_violations=violations,callback_errors=errors)
        (base/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('RESULT '+str(base/'results.json'),flush=True)
        assert unchanged and not violations


if __name__ == '__main__': main()
