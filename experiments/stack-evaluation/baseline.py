"""Synthetic Tk E2E baseline. Production modules are imported, never edited.
Run: .venv/Scripts/python.exe -X utf8 -B experiments/stack-evaluation/baseline.py
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import gc
import json
import platform
import statistics
import subprocess
import time
import tkinter as tk
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from ff11reader.ui import ReaderWindow
from ff11reader import tracing


def run(file_count, repetitions=6):
    fixture = MoveFixture(); fixture.setUp()
    app = None
    rows = []
    try:
        template = (fixture.folder / 'mcr.dat').read_bytes()
        for index in range(2, file_count):
            (fixture.folder / f'mcr{index}.dat').write_bytes(template)
        # Decode every generated file through the production codec.
        from ff11reader import codecs
        from ff11reader.edit_application import Editor
        snapshot = fixture.load()
        character = snapshot.characters[0]
        for index in range(2, file_count):
            path = fixture.folder / f'mcr{index}.dat'
            character.macros.extend(codecs.macros(path.read_bytes(), index))
        editor = Editor(snapshot, fixture.base / 'baseline-state.json')
        app = tk.Tk(); errors = []
        app.report_callback_exception = lambda *args: errors.append(repr(args))
        view = ReaderWindow(app, snapshot, editor=editor)
        view.tabs.select('マクロ'); app.update()
        entry = view.macro_panel.entries[0]
        address = view.active_macro
        original_writeback = editor.writeback
        # Save actual synthetic bytes, but keep backups inside the disposable fixture.
        def writeback(plans, _destination):
            return original_writeback(plans, fixture.base / 'backups')
        def measure(name, action, iteration):
            gaps = []; last = time.perf_counter(); timer = None
            def tick():
                nonlocal last, timer
                now = time.perf_counter(); gaps.append((now-last)*1000); last = now
                timer = app.after(10, tick)
            timer = app.after(10, tick)
            start = time.perf_counter()
            with tracing.span('e2e.' + name):
                action(); app.update_idletasks(); app.update()
            end = time.perf_counter()
            gaps.append((end-last)*1000)
            app.after_cancel(timer)
            assert not errors, errors
            rows.append(dict(operation=name, iteration=iteration, elapsed_ms=(end-start)*1000,
                             max_event_gap_ms=max(gaps), heartbeats=len(gaps)-1))
        with patch.object(editor, 'writeback', side_effect=writeback), patch('ff11reader.macro_editor_ui.ime_composing', return_value=False):
            for iteration in range(repetitions):
                entry.focus_force(); app.update()
                entry.event_generate('<Return>'); app.update()
                entry.delete(0, 'end'); entry.insert(0, f'Bench{iteration}')
                app.update()
                cursor = editor.edit_status()[0]
                measure('edit_commit', lambda: entry.event_generate('<Return>'), iteration)
                assert editor.edit_status()[0] == cursor+1
                assert app.focus_get() is entry
                measure('undo', lambda: view.undo_button.invoke(), iteration)
                assert editor.edit_status()[0] == cursor
                measure('redo', lambda: view.redo_button.invoke(), iteration)
                assert editor.edit_status()[0] == cursor+1
                measure('tab_inventory', lambda: view.tabs.select('インベントリ'), iteration)
                measure('tab_macro', lambda: view.tabs.select('マクロ'), iteration)
                assert view.active_macro == address
                measure('save_preview', lambda: view.save_button.invoke(), iteration)
                preview = app.grab_current()
                assert isinstance(preview, tk.Toplevel)
                measure('writeback', lambda: preview.accept_button.invoke(), iteration)
                assert not editor.session.dirty
                # Verify persisted bytes with an independent reload of the fixture.
                saved = fixture.load().characters[0].macros
                assert next(m for m in saved if (m.book,m.palette,m.bank,m.key)==address).title.display == f'Bench{iteration}'
        summary = []
        for name in dict.fromkeys(row['operation'] for row in rows):
            warm = [r for r in rows if r['operation']==name and r['iteration']>0]
            values = sorted(r['elapsed_ms'] for r in warm)
            summary.append(dict(operation=name, samples=len(values), median_ms=statistics.median(values),
                                max_ms=max(values), max_event_gap_ms=max(r['max_event_gap_ms'] for r in warm)))
        return dict(macro_files=file_count, macros=len(character.macros), characters=1,
                    inventory_rows=len(character.inventory), rows=rows, summary=summary,
                    callback_errors=errors, assertions='commit/undo/redo cursor, edit focus, tab target, clean save, saved bytes')
    finally:
        if app is not None: app.destroy()
        fixture.doCleanups(); gc.collect()


if __name__ == '__main__':
    output = ROOT / 'work/stack-evaluation'; output.mkdir(parents=True, exist_ok=True)
    # A fresh trace for each run; keep separate output directories for comparisons.
    (output / 'baseline-spans.jsonl').write_text('', encoding='utf-8')
    tracing.configure(output / 'baseline-spans.jsonl')
    result = dict(commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
                  python=sys.version, platform=platform.platform(),
                  scope='Synthetic Tk UI event dispatch through actual Editor and filesystem; excludes OS input/display latency, real IME, installed game and cold startup.',
                  cases=[])
    for count in (20, 200):
        result['cases'].append(run(count))
        (output/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result['cases'][-1].items() if k!='rows'},ensure_ascii=False),flush=True)
