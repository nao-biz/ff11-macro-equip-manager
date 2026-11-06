"""Exercise UI entry points; fail if application work returns to the Tk thread."""
from contextlib import ExitStack
import gc
import os
from pathlib import Path
from threading import get_ident
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from tests.test_ui_tasks import TkThreadGuard
from ff11reader.ui import ReaderWindow


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class ExecutionBoundaryTests(MoveFixture):
    def tearDown(self):
        # Release destroyed Tk object cycles on their owner before another worker starts.
        gc.collect()

    def test_draft_retry_waits_in_worker_and_recovers_after_failure(self):
        from ff11reader.ui_tasks import tasks
        from tests.test_draft_store import windows_error
        app=tk.Tk();app.tk=TkThreadGuard(app.tk)
        callbacks=[];ticks=[];job=None
        app.report_callback_exception=lambda *args:callbacks.append(args)
        owner=get_ident();actual_sleep=time.sleep;actual_replace=Path.replace
        failures=[windows_error(),windows_error(32)]
        def replace(temp,target):
            self.assertNotEqual(get_ident(),owner)
            if failures:raise failures.pop(0)
            return actual_replace(temp,target)
        def pause(delay):
            self.assertNotEqual(get_ident(),owner)
            actual_sleep(delay)
        def tick():
            nonlocal job
            ticks.append(1);job=app.after(5,tick)
        try:
            view=ReaderWindow(app,self.source,editor=self.editor);app.update()
            edit=self.editor.prepare_equipment_move('abc',1,45)
            view.run_edit(lambda:self.editor.apply(edit))
            job=app.after(1,tick)
            with patch.object(Path,'replace',replace),patch('ff11reader.draft_store.time.sleep',side_effect=pause):
                view.undo_button.invoke()
            self.assertFalse(failures)
            self.assertGreater(len(ticks),0)
            self.assertEqual(self.editor.edit_status(),(0,1,False))
            self.assertFalse(tasks(app).running)
            original=self.editor.store.path.read_bytes()
            messages=[]
            def showerror(*args,**kwargs):
                self.assertEqual(get_ident(),owner);messages.append(args)
            with patch.object(Path,'replace',side_effect=windows_error()), \
                    patch('ff11reader.draft_store.time.sleep',side_effect=pause), \
                    patch('ff11reader.ui.dialogs.showerror',side_effect=showerror):
                view.redo_button.invoke()
            self.assertEqual(len(messages),1)
            self.assertEqual(self.editor.store.path.read_bytes(),original)
            self.assertEqual(self.editor.edit_status(),(0,1,False))
            self.assertFalse(tasks(app).running)
            self.assertIsNone(app.grab_current())
            view.redo_button.invoke()
            self.assertEqual(self.editor.edit_status(),(1,1,True))
            self.assertFalse(callbacks)
        finally:
            if job is not None:app.after_cancel(job)
            app.destroy()

    def test_edit_history_save_reset_and_reload_use_worker(self):
        self.editor.root=self.folder.parent.parent
        app=tk.Tk()
        app.tk=TkThreadGuard(app.tk)
        errors=[]
        app.report_callback_exception=lambda *args:errors.append(args)
        owner=get_ident()
        seen=set()
        operations=('apply','undo','redo','prepare_combined_save',
                    'save_combined','start_fresh','reload','snapshot')
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            app.update()
            edit=self.editor.prepare_equipment_move('abc',1,45)
            def checked(name,operation):
                def call(*args,**kwargs):
                    self.assertNotEqual(get_ident(),owner,name+' ran on the UI thread')
                    seen.add(name)
                    return operation(*args,**kwargs)
                return call
            with ExitStack() as stack:
                for name in operations:
                    operation=getattr(self.editor,name)
                    stack.enter_context(patch.object(self.editor,name,side_effect=checked(name,operation)))
                stack.enter_context(patch('ff11reader.ui.dialogs.askyesno',return_value=True))
                stack.enter_context(patch('ff11reader.ui.dialogs.showerror',side_effect=AssertionError('Unexpected UI error')))
                view.run_edit(lambda:self.editor.apply(edit))
                edit_menu=app.nametowidget(view.operation_menu.entrycget(0,'menu'))
                edit_menu.invoke('Undo')
                view.redo_button.invoke()
                view.save_button.invoke()
                preview=app.grab_current()
                self.assertIsInstance(preview,tk.Toplevel)
                save=next(w for w in preview.winfo_children() if isinstance(w,ttk.Button))
                save.invoke()
                self.assertFalse(self.editor.session.dirty)
                view.reset_edits()
                view.reload_button.invoke()
            self.assertEqual(seen,set(operations))
            self.assertFalse(errors)
            self.assertEqual(self.editor.edit_status(),(0,0,False))
        finally:
            app.destroy()
