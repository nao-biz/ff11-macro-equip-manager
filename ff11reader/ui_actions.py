"""Explicit busy actions for heavy UI operations."""
from .theme import ACCENT, SELECT
from .ui_operation_state import operations
from contextlib import contextmanager
import tkinter as tk
from tkinter import ttk


class BusyState:
    def __init__(self,root):
        self.root=root;self.depth=0;self.cursors=[];self.notice=None;self.message="処理中です…"

    def show(self):
        def visit(widget):
            try:
                if 'cursor' in widget.keys():
                    self.cursors.append((widget,widget.cget('cursor')))
                    widget.configure(cursor='wait')
                for child in widget.winfo_children():visit(child)
            except tk.TclError:pass
        if self.notice is None or not self.notice.winfo_exists():
            self.notice=tk.Label(self.root,bg=SELECT,fg=ACCENT,padx=24,pady=12,font=('MS Gothic',12,'bold'),relief='ridge',borderwidth=2)
        self.notice.configure(text=self.message)
        self.notice.place(relx=.5,y=8,anchor='n');self.notice.lift()
        visit(self.root)
        # Flush drawing only. Do not dispatch another click/key while the action runs.
        try:self.root.update_idletasks()
        except tk.TclError:pass

    def restore(self):
        try:
            if self.notice is not None:self.notice.place_forget()
        except tk.TclError:pass
        cursors,self.cursors=self.cursors,[]
        for widget,cursor in reversed(cursors):
            try:widget.configure(cursor=cursor)
            except tk.TclError:pass  # The callback may destroy its window.
        # Commit cursor/notice cleanup before returning to the native event loop.
        # This also lets widgets created during work inherit the restored cursor.
        if cursors:
            try:self.root.update_idletasks()
            except tk.TclError:pass

    @contextmanager
    def handling(self,message="処理中です…"):
        outer=self.depth==0;self.depth+=1
        try:
            if outer:
                self.message=message;self.show()
            yield
        finally:
            self.depth-=1
            if outer:self.restore()

    @contextmanager
    def waiting(self):
        """A nested event loop waits for a user, so it must have normal cursors."""
        depth=self.depth;message=self.message
        self.restore();self.depth=0
        try:yield
        finally:
            self.depth=depth;self.message=message
            if depth:self.show()


def state(widget):
    return operations(widget).busy(BusyState)


@contextmanager
def input_wait(widget):
    with state(widget).waiting():yield


def run_action(widget, command, *, busy=False, message="処理中です…"):
    """Shared entry for buttons and keyboard commands; paint before doing work."""
    if operations(widget).blocked:return
    if not busy:return command()
    with state(widget).handling(message):return command()


class ActionButton(ttk.Button):
    """Declare busy=True at construction; the action itself stays UI-independent."""
    def __init__(self,master=None,*,command=None,busy=False,busy_message="処理中です…",**kwargs):
        self._action=command;self._busy=busy;self._busy_message=busy_message
        super().__init__(master,command=self._run,**kwargs)
        self.bind('<Destroy>',self._release_action,add='+')

    def _release_action(self,event):
        if event.widget is self:self._action=None

    def _run(self):
        if self._action is None:return
        return run_action(self,self._action,busy=self._busy,message=self._busy_message)

    def configure(self,cnf=None,**kwargs):
        if isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        if 'command' in kwargs:
            self._action=kwargs['command'];kwargs['command']=self._run
        if 'busy_message' in kwargs:self._busy_message=kwargs.pop('busy_message')
        if 'busy' in kwargs:self._busy=kwargs.pop('busy')
        return super().configure(cnf,**kwargs)

    config=configure
