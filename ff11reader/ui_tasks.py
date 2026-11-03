"""Exclusive worker execution with a responsive Tk modal wait.

Only the caller/poller touches Tk. The worker receives a callable with captured
plain arguments, owns application state until completion, and returns via Queue.
"""
from contextvars import copy_context
from queue import Queue, Empty
from threading import Thread, get_ident
import tkinter as tk
from tkinter import ttk


class TaskScreen:
    """Block application input while keeping the native event loop running."""
    def __init__(self, root, message):
        self.root = root
        self.focus = root.focus_get()
        self.grab = root.grab_current()
        self.grab_status = self.grab.grab_status() if self.grab else None
        self.layers = []
        self.progress = []
        self.protocols = []
        self.bindings = []
        self.tag = 'FF11TaskInput' + str(id(self))
        self.label = None
        self.display_job = None
        # A first bindtag also covers keys already queued before focus moves.
        for event in ('<KeyPress>', '<KeyRelease>', '<ButtonPress>', '<ButtonRelease>',
                      '<MouseWheel>', '<Configure>', '<<ListboxSelect>>', '<<TreeviewSelect>>', '<<ComboboxSelected>>'):
            root.tk.call('bind', self.tag, event, 'break')
        windows = []
        def visit(widget):
            self.bindings.append((widget, widget.bindtags(), bool(widget.bind('<Configure>'))))
            widget.bindtags((self.tag,) + widget.bindtags())
            if isinstance(widget, (tk.Tk, tk.Toplevel)):windows.append(widget)
            for child in widget.winfo_children():visit(child)
        visit(root)
        for window in windows:
            previous = window.protocol('WM_DELETE_WINDOW')
            command = window.register(self.request_close)
            window.tk.call('wm', 'protocol', window._w, 'WM_DELETE_WINDOW', command)
            self.protocols.append((window, previous, command))
            layer = tk.Frame(window, bg='#080f22', cursor='wait', takefocus=True)
            # Show after a short delay so fast operations do not flash an overlay.
            layer.bindtags((self.tag,))
            panel = tk.Frame(layer,bg='#101b38',padx=24,pady=20,highlightthickness=1,highlightbackground='#8491b2')
            panel.place(relx=.5,rely=.5,anchor='center')
            label = tk.Label(panel,text=message,bg='#101b38',fg='#fff3c4',font=('MS Gothic',12),wraplength=420)
            label.pack()
            progress = ttk.Progressbar(panel,mode='indeterminate',length=300)
            progress.pack(pady=(16,0))
            self.layers.append(layer);self.progress.append(progress)
            if window is root:self.label=label;self.layer=layer
        self.layer.grab_set();self.layer.focus_set()
        self.display_job=root.after(150,self.show)

    def show(self):
        self.display_job=None
        for layer, progress in zip(self.layers,self.progress):
            layer.place(x=0,y=0,relwidth=1,relheight=1);layer.lift();progress.start(35)
        self.layer.focus_set()

    def finish(self):
        if self.display_job:
            self.root.after_cancel(self.display_job);self.display_job=None
        for progress in self.progress:progress.stop()
        self.progress=[]
        self.layer.destroy()

    def request_close(self):
        self.label.configure(text='処理中です。完了してから閉じてください。')

    def close(self):
        if self.display_job:
            try:self.root.after_cancel(self.display_job)
            except tk.TclError:pass
            self.display_job=None
        for progress in self.progress:
            try:progress.stop()
            except tk.TclError:pass
        for layer in self.layers:
            try:layer.destroy()
            except tk.TclError:pass
        for widget, tags, configure in self.bindings:
            try:
                widget.bindtags(tags)
                # Re-layout covered content once after work, rather than repeatedly
                # competing with the worker for Python execution during resizing.
                if configure:
                    widget.event_generate('<Configure>',width=widget.winfo_width(),height=widget.winfo_height(),when='tail')
            except tk.TclError:pass
        for window, previous, command in self.protocols:
            try:
                window.tk.call('wm','protocol',window._w,'WM_DELETE_WINDOW',previous)
                window.deletecommand(command)
            except tk.TclError:pass
        try:
            for event in self.root.tk.call('bind',self.tag):
                self.root.tk.call('bind',self.tag,event,'')
        except tk.TclError:pass
        try:
            if self.grab and self.grab.winfo_exists():
                if self.grab_status=='global':self.grab.grab_set_global()
                else:self.grab.grab_set()
            if self.focus and self.focus.winfo_exists():self.focus.focus_set()
        except tk.TclError:pass


class BackgroundTasks:
    def __init__(self, root):
        self.root=root
        self.ui_thread=get_ident()
        self.running=False
        self.screen=None
        self.worker=None

    def call(self, operation, message):
        if get_ident()!=self.ui_thread:raise RuntimeError('UIスレッドから呼び出してください。')
        if self.running:raise RuntimeError('別の処理を実行中です。')
        self.running=True
        results=Queue();context=copy_context();outcome=[];poll_id=None
        def work():
            try:results.put((True,context.run(operation)))
            except BaseException as exc:results.put((False,exc))
        def poll():
            nonlocal poll_id
            poll_id=None
            try:outcome.append(results.get_nowait())
            except Empty:
                poll_id=self.root.after(20,poll);return
            self.screen.finish()
        try:
            self.screen=TaskScreen(self.root,message)
            self.worker=Thread(target=work,name='ff11-operation',daemon=False)
            self.worker.start()
            poll_id=self.root.after(20,poll)
            # A modal Tk event loop handles paint/timers/OS messages. No update loop.
            self.root.wait_window(self.screen.layer)
            if not outcome:raise tk.TclError('処理中にウィンドウが破棄されました。')
        finally:
            if poll_id:
                try:self.root.after_cancel(poll_id)
                except tk.TclError:pass
            try:
                if self.screen:self.screen.close()
            finally:self.screen=None;self.running=False
        ok,value=outcome[0]
        if not ok:raise value
        return value


def tasks(widget):
    root=widget._root()
    if not hasattr(root,'_background_tasks'):root._background_tasks=BackgroundTasks(root)
    return root._background_tasks


def is_running(widget):
    runner=getattr(widget._root(),'_background_tasks',None)
    return bool(runner and runner.running)


def background(widget, function, *args, message='処理しています…', **kwargs):
    from .ui_actions import state
    with state(widget).handling(message):
        return tasks(widget).call(lambda:function(*args,**kwargs),message)
