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
from ff11reader.save_state import SaveRequest


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class ExecutionBoundaryTests(MoveFixture):
    def tearDown(self):
        # Release destroyed Tk object cycles on their owner before another worker starts.
        gc.collect()

    def test_edit_history_save_reset_and_reload_use_worker(self):
        self.editor.root=self.folder.parent.parent
        app=tk.Tk()
        app.tk=TkThreadGuard(app.tk)
        errors=[]
        app.report_callback_exception=lambda *args:errors.append(args)
        owner=get_ident()
        seen=set()
        operations=('apply','undo','redo',
                    'save_combined','prepare_writeback','writeback','start_fresh','reload','snapshot')
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
                stack.enter_context(patch.object(SaveRequest,'prepare',autospec=True,
                    side_effect=checked('prepare_save_request',SaveRequest.prepare)))
                stack.enter_context(patch('ff11reader.ui.dialogs.askyesno',return_value=True))
                stack.enter_context(patch('ff11reader.ui.dialogs.showerror',side_effect=AssertionError('Unexpected UI error')))
                view.run_edit(lambda:self.editor.apply(edit))
                edit_menu=view.common_menus['編集']
                edit_menu.invoke('Undo')
                view.redo_button.invoke()
                view.save_button.invoke()
                preview=app.grab_current()
                self.assertIsInstance(preview,tk.Toplevel)
                save=preview.accept_button
                save.invoke()
                self.assertFalse(self.editor.session.dirty)
                view.reset_edits()
                view.reload_button.invoke()
            self.assertEqual(seen,set(operations)|{'prepare_save_request'})
            self.assertFalse(errors)
            self.assertEqual(self.editor.edit_status(),(0,0,False))
        finally:
            app.destroy()
