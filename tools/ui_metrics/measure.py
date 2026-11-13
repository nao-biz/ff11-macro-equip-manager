"""Count application operations in isolated synthetic Tk scenarios."""
import argparse
from collections import Counter
from contextlib import ExitStack
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
from threading import Lock
import tkinter as tk
from unittest.mock import patch

from ff11reader.ui import ReaderWindow
from ff11reader.ui_tasks import tasks, BackgroundTasks
from ff11reader.selection_ui import SelectionCommands
from ff11reader.edit_application import Editor
from tests.test_equipment_moves import MoveFixture

SCENARIOS=('palette_transfer','undo_redo','navigation','save_preview')
METRICS=('worker_calls','selection_paints','workspace_rebuilds','macro_renders',
         'card_creations','snapshot_exports','widget_creations','widget_destructions')
ROOT=Path(__file__).resolve().parents[2]


def transfer(view):
    view.commands.select('palette',(1,1));view.commands.run('copy')
    view.commands.select('palette',(1,2));view.commands.run('paste')


def exercise(name, view):
    if name=='palette_transfer':transfer(view)
    elif name=='undo_redo':
        view.commands.run('undo');view.commands.run('redo')
    elif name=='navigation':
        for tab in ('装備セット','インベントリ','マクロ'):view.tabs.select(tab)
        view.commands.select('palette',(1,2));view.commands.select('palette',(1,1))
    else:
        view.preview_combined_save()
        window=view.app.grab_current()
        if not isinstance(window,tk.Toplevel):raise AssertionError('保存プレビューが開きませんでした。')
        window.destroy()


def run_scenario(name):
    fixture=MoveFixture();app=None;view=None
    try:
        fixture.setUp()
        fixture.editor.apply(fixture.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Measured',['/echo measured']+['']*5))
        app=tk.Tk();app.geometry('1440x900+0+0');errors=[]
        app.report_callback_exception=lambda *args:errors.append(args[0].__name__)
        counts=Counter(dict.fromkeys(METRICS,0));lock=Lock()
        def instrument(stack, owner, method, metric):
            original=getattr(owner,method)
            def counted(*args,**kwargs):
                with lock:counts[metric]+=1
                return original(*args,**kwargs)
            stack.enter_context(patch.object(owner,method,counted))
        with ExitStack() as stack:
            for owner,method,metric in (
                (BackgroundTasks,'call','worker_calls'),(SelectionCommands,'paint','selection_paints'),
                (ReaderWindow,'change_mode','workspace_rebuilds'),(ReaderWindow,'render_macros','macro_renders'),
                (ReaderWindow,'card','card_creations'),(Editor,'snapshot','snapshot_exports'),
                (tk.BaseWidget,'__init__','widget_creations'),(tk.BaseWidget,'destroy','widget_destructions')):
                instrument(stack,owner,method,metric)
            # Bind callbacks to instrumented methods before building the UI.
            view=ReaderWindow(app,fixture.editor.snapshot(),editor=fixture.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            if name=='undo_redo':transfer(view);app.update()
            counts.clear();counts.update(dict.fromkeys(METRICS,0))
            exercise(name,view)
            app.update()  # Include queued callbacks before ending the measurement.
        if errors:raise AssertionError('Tk callbacks: '+', '.join(errors))
        if tasks(app).running or app.grab_current() is not None:raise AssertionError('待機が解除されていません。')
        if name in ('palette_transfer','undo_redo'):
            target=next(m for m in view.character.macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            if target.title.display!='Measured':raise AssertionError('貼り付け結果が一致しません。')
        if name=='navigation' and (view.mode.get()!='マクロ' or view.selected!=(1,1)):
            raise AssertionError('切替後の選択が一致しません。')
        if any(p.read_bytes()!=raw for p,raw in fixture.original.items()):
            raise AssertionError('プレビューで合成ゲームファイルが変更されました。')
        return dict(counts),str(app.tk.call('info','patchlevel')),str(app.tk.call('package','require','Tk'))
    finally:
        if app is not None:app.destroy()
        fixture.doCleanups()
        del view,app,fixture
        gc.collect()  # Collect Tk cycles on the owner thread before the next worker.


def measure(repeats=3):
    if repeats<1:raise ValueError('repeats must be positive')
    digest=hashlib.sha256()
    for path in ('tools/ui_metrics/measure.py','tests/test_equipment_moves.py'):
        digest.update((ROOT/path).read_text(encoding='utf-8').replace('\r\n','\n').encode())
    result=dict(schema_version=1,suite_revision=digest.hexdigest(),
                environment=dict(python=platform.python_version(),os=platform.system()),
                commit=os.environ.get('GITHUB_SHA'),run_id=os.environ.get('GITHUB_RUN_ID'),scenarios={})
    for name in SCENARIOS:
        samples=[]
        for _ in range(repeats):
            counts,tcl,tk_version=run_scenario(name);samples.append(counts)
        result['environment'].update(tcl=tcl,tk=tk_version)
        result['scenarios'][name]=dict(samples=samples,metrics={key:dict(
            min=min(s[key] for s in samples),max=max(s[key] for s in samples)) for key in METRICS})
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='work/ui-metrics')
    parser.add_argument('--repeats',type=int,default=3);args=parser.parse_args()
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    try:
        result=measure(args.repeats);result['status']='success'
    except Exception as exc:
        (output/'measurement.json').write_text(json.dumps(dict(status='failed',error_type=type(exc).__name__)),encoding='utf-8')
        raise
    (output/'measurement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Measured '+', '.join(result['scenarios']))


if __name__=='__main__':main()
