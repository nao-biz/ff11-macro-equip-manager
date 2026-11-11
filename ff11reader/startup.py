"""Startup preparation off the Tk thread; one-way ownership handoff to the UI."""
from .theme import BG, FG, PANEL, install
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event
import tkinter as tk
from tkinter import ttk
import hashlib


def unchanged(result):
    snapshot, _ = result
    try:
        return all(hashlib.sha256(Path(s['path']).read_bytes()).hexdigest() == s['sha256']
                   for s in snapshot.sources)
    except OSError:return False


def prepare(root, report):
    from .application import installations, load_snapshot
    from .edit_application import Editor
    from .tracing import configure, span
    configure(Path(__file__).resolve().parent.parent/'work'/'logs'/'timings.jsonl')
    with span('startup.prepare'):
        report('ゲームデータを読み込んでいます…')
        roots=installations() if root is None else [root]
        if len(roots)!=1:raise ValueError('FF11のインストール先を特定できません。--rootで指定してください。')
        with span('startup.read'):snapshot=load_snapshot(Path(roots[0]).resolve())
        report('編集画面を準備しています…')
        with span('startup.edit_session'):
            editor=Editor(snapshot,root=roots[0])
            snapshot=editor.snapshot()
        return snapshot,editor


class Startup:
    def __init__(self, app, prepare_work, ready, *, probe=None):
        install(app)
        self.app=app;self.prepare_work=prepare_work;self.ready=ready
        self.messages=Queue();self.closed=False;self.started=False;self.poll_id=None
        self.probe=probe;self.stop_event=Event()
        app.title('FF11 ワークスペース — 起動中');app.geometry('480x180');app.configure(bg=BG)
        self.panel=tk.Frame(app,bg=BG,padx=24,pady=24);self.panel.pack(fill='both',expand=True)
        tk.Label(self.panel,text='FF11 ワークスペースを起動しています',bg=BG,fg=FG,font=('MS Gothic',13,'bold')).pack(anchor='w')
        self.status=tk.Label(self.panel,text='準備しています…',bg=BG,fg=FG,wraplength=430,justify='left');self.status.pack(anchor='w',pady=12)
        self.progress=ttk.Progressbar(self.panel,mode='indeterminate');self.progress.pack(fill='x');self.progress.start(40)
        app.protocol('WM_DELETE_WINDOW',self.close)
        self.binding=app.bind('<Map>',self.mapped,add='+')

    def mapped(self,event):
        if event.widget is not self.app or self.started:return
        self.started=True;self.app.unbind('<Map>',self.binding)
        self.app.after_idle(self.start)

    def start(self):
        if self.closed:return
        def work():
            while not self.stop_event.is_set():
                try:
                    if self.probe and self.probe():
                        self.messages.put(('status','ゲームの終了を待っています。FF11とPlayOnlineを終了すると自動で読み込みます。'))
                        self.stop_event.wait(1);continue
                    result=self.prepare_work(lambda text:self.messages.put(('status',text)))
                    if self.probe and self.probe():continue
                    if self.probe:
                        if not unchanged(result):continue
                        if self.stop_event.wait(.5):return
                        if self.probe() or not unchanged(result):continue
                    self.messages.put(('ready',result));return
                except Exception as exc:
                    if not self.probe:
                        self.messages.put(('error',str(exc)));return
                    self.messages.put(('status','ゲームと保存データを再確認しています…\n'+str(exc)))
                    self.stop_event.wait(1)
        # Finish any interrupted-save check even if the window is closed.
        self.worker=Thread(target=work,name='ff11-startup',daemon=False);self.worker.start()
        self.poll_id=self.app.after(40,self.poll)

    def poll(self):
        self.poll_id=None
        if self.closed:return
        try:
            while True:
                kind,value=self.messages.get_nowait()
                if kind=='status':self.status.configure(text=value)
                else:
                    self.progress.stop()
                    if kind=='error':self.fail(value);return
                    try:
                        self.panel.destroy();self.app.protocol('WM_DELETE_WINDOW',self.app.destroy)
                        self.ready(value)
                    except Exception as exc:
                        from . import dialogs
                        dialogs.showerror('起動できませんでした',str(exc),parent=self.app)
                        self.app.destroy()
                    return
        except Empty:pass
        self.poll_id=self.app.after(40,self.poll)

    def fail(self,message):
        self.app.title('FF11 ワークスペース — 起動エラー')
        self.status.configure(text='起動できませんでした。')
        self.progress.pack_forget()
        detail=tk.Text(self.panel,height=6,bg=PANEL,fg=FG,wrap='word')
        detail.insert('1.0',message);detail.configure(state='disabled');detail.pack(fill='both',expand=True)
        ttk.Button(self.panel,text='閉じる',command=self.close).pack(pady=8)
        self.app.geometry('600x340')

    def close(self):
        self.closed=True
        self.stop_event.set()
        if self.poll_id:self.app.after_cancel(self.poll_id)
        self.progress.stop();self.app.destroy()


def launch(root=None):
    app=tk.Tk()
    def ready(result):
        from .ui import ReaderWindow
        snapshot,editor=result
        app.view=ReaderWindow(app,snapshot,editor=editor)
        from . import dialogs
        dialogs.when_visible(app,lambda:app.view.configure_windower(first=True))
        from .sync_ui import SyncMonitor
        app.sync_monitor=SyncMonitor(app.view)
    from .game_process import game_running
    app.startup=Startup(app,lambda report:prepare(root,report),ready,probe=game_running)
    app.mainloop()
