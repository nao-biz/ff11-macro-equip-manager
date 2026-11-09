"""Synthetic Tk flow: preview, draft apply, history and restart. No game access."""
import os
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from tests.test_editing import snapshot, TEMP_ROOT
from ff11reader.edit_application import Editor
from ff11reader.ui import ReaderWindow


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Enable Tk integration checks')
class EditingUITests(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()

    def test_edit_preview_undo_redo_fix_and_reopen(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            path=Path(tmp)/'draft.json';source=snapshot();app=tk.Tk();app.withdraw();errors=[]
            app.report_callback_exception=lambda *args:errors.append(args)
            def dialogs():
                return [w for w in app.winfo_children() if isinstance(w,tk.Toplevel)]
            def button(window,contains):
                for w in window.winfo_children():
                    if isinstance(w,ttk.Button) and contains in str(w.cget('text')):return w
                    found=button(w,contains)
                    if found:return found
            def entries(window):
                result=[]
                for w in window.winfo_children():
                    if isinstance(w,tk.Entry):result.append(w)
                    else:result.extend(entries(w))
                return result
            try:
                with patch('ff11reader.ui.Editor',side_effect=lambda s:Editor(s,path)):
                    view=ReaderWindow(app,source)
                view.mode.set('マクロ');view.change_mode();app.update()
                view.inspect_macro(view.character.macros[0]);view.edit_selected_macro();app.update()
                editor=view.macro_panel.frame;fields=entries(editor)
                with patch('ff11reader.macro_editor_ui.ime_composing',return_value=False):view.macro_panel.toggle_line(0)
                fields[0].delete(0,'end');fields[0].insert(0,'Edited')
                button(editor,'入力を確定').invoke();app.update()
                self.assertIsNone(app.grab_current())
                self.assertEqual(view.character.macros[0].title.display,'Edited')
                view.undo_fix();app.update();self.assertEqual(view.character.macros[0].title.display,'Regen')
                view.redo_edit();app.update();self.assertEqual(view.character.macros[0].title.display,'Edited')
                view.show_macro_inventory();app.update();button(dialogs()[-1],'まとめて確認').invoke();app.update()
                dialogs()[-1].accept_button.invoke();app.update()
                self.assertIn('"Robe" 2 <wait 2>',view.character.macros[0].lines[0].display)
                self.assertEqual(view.macro_item_refs[0].state,'match')
                self.assertEqual(view.editor.session.cursor,2)
                resumed=Editor(source,path)
                self.assertEqual(resumed.session.working.characters[0].macros,source.characters[0].macros)
                self.assertEqual(resumed.edit_status(),(0,0,False))
                view.undo_fix();app.update();self.assertEqual(view.macro_item_refs[0].state,'unspecified_unique')
                self.assertEqual(source.characters[0].macros[0].title.display,'Regen')
                self.assertFalse(errors,errors)
            finally:app.destroy()
