import gc
import os
from pathlib import Path
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import patch
from ff11reader.windower_settings import WindowerSettings
from ff11reader.windower_settings_ui import FolderDialog, configure
from tests.test_windower_settings import make_windower
from tests.test_ui_tasks import TkThreadGuard
from tests.test_equipment_moves import MoveFixture


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class FolderUITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.settings = WindowerSettings(self.base/'settings.json')
        self.app = tk.Tk()
        self.app.tk = TkThreadGuard(self.app.tk)
        self.app.geometry('1000x650')
        self.app.update()

    def tearDown(self):
        self.app.destroy()
        del self.app
        gc.collect()

    def test_first_defer_then_save_restart_skip_and_change(self):
        with patch.object(FolderDialog, 'wait', autospec=True, side_effect=lambda dialog: (
                dialog.cancel(), None)[1]):
            self.assertFalse(configure(self.app, self.settings, first=True))
        self.assertFalse(self.settings.path.exists())
        folder = make_windower(self.base/'Windower')
        threads = []
        save = self.settings.save
        def saving(path):
            threads.append(threading.get_ident())
            return save(path)
        def answer(dialog):
            dialog.finish(str(folder))
            return dialog.result
        with patch.object(FolderDialog, 'wait', autospec=True, side_effect=answer), \
                patch.object(self.settings, 'save', side_effect=saving):
            self.assertTrue(configure(self.app, self.settings, first=True))
        self.assertNotEqual(threads, [threading.get_ident()])
        with patch('ff11reader.windower_settings_ui.FolderDialog') as dialog:
            self.assertFalse(configure(self.app, self.settings, first=True))
            dialog.assert_not_called()
        second = make_windower(self.base/'second')
        seen = []
        def change(dialog):
            seen.append(dialog.entry.get())
            dialog.finish(str(second))
            return dialog.result
        with patch.object(FolderDialog, 'wait', autospec=True, side_effect=change):
            self.assertTrue(configure(self.app, self.settings))
        self.assertEqual(seen, [str(folder)])
        self.assertEqual(self.settings.read(), second)

    def test_folder_picker_cancel_and_layout(self):
        dialog = FolderDialog(self.app, str(self.base), first=True)
        self.app.update()
        with patch('ff11reader.windower_settings_ui.filedialog.askdirectory', return_value=''):
            dialog.browse_button.invoke()
        self.assertEqual(dialog.entry.get(), str(self.base))
        with patch('ff11reader.windower_settings_ui.filedialog.askdirectory', return_value=str(self.base/'selected')):
            dialog.browse_button.invoke()
        self.assertEqual(dialog.entry.get(), str(self.base/'selected'))
        self.assertEqual(dialog.cancel_button.cget('text'), 'あとで設定')
        self.assertLess(dialog.panel.winfo_x()+dialog.panel.winfo_width(), self.app.winfo_width())
        self.assertLess(dialog.bar.winfo_y()+dialog.bar.winfo_height(), dialog.panel.winfo_height())
        self.app.after(10, dialog.cancel_button.invoke)
        self.assertIsNone(dialog.wait())

    def test_save_failure_and_cancel_keep_config(self):
        folder = make_windower(self.base/'Windower')
        self.settings.save(folder)
        before = self.settings.path.read_bytes()
        answers = iter((str(folder), None))
        def answer(dialog):
            dialog.finish(next(answers))
            return dialog.result
        with patch.object(FolderDialog, 'wait', autospec=True, side_effect=answer), \
                patch.object(self.settings, 'save', side_effect=OSError('disk failure')), \
                patch('ff11reader.windower_settings_ui.dialogs.showerror') as error:
            self.assertFalse(configure(self.app, self.settings))
            error.assert_called_once()
        self.assertEqual(self.settings.path.read_bytes(), before)


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class WorkspaceSettingsTests(MoveFixture):
    def test_settings_button_keeps_edits_and_pending_macro(self):
        from ff11reader.ui import ReaderWindow
        self.move()
        before = self.editor.edit_status()
        app = tk.Tk()
        app.tk = TkThreadGuard(app.tk)
        try:
            view = ReaderWindow(app, self.editor.snapshot(), editor=self.editor)
            view.mode.set('マクロ'); view.change_mode()
            view.inspect_macro(view.character.macros[0])
            view.macro_panel.variables[0].set('Pending')
            view.macro_panel.capture()
            pending = dict(view.macro_panel.pending)
            folder = make_windower(self.base/'Windower')
            def answer(dialog):
                dialog.finish(str(folder))
                return dialog.result
            with patch.object(FolderDialog, 'wait', autospec=True, side_effect=answer):
                view.settings_button.invoke()
            self.assertEqual(view.augment_store.settings.read(), folder)
            self.assertEqual(self.editor.edit_status(), before)
            self.assertEqual(view.macro_panel.pending, pending)
            self.assertEqual(self.original, {p:p.read_bytes() for p in self.folder.iterdir()})
        finally:
            app.destroy()
            del app
            gc.collect()

    def test_launch_offers_settings_once_after_main_window_is_visible(self):
        from ff11reader.startup import launch
        calls = []
        def configure_view(view, *, first=False):
            calls.append((first, bool(view.app.winfo_viewable())))
            view.app.after_idle(view.app.destroy)
        with patch('ff11reader.startup.prepare', return_value=(self.editor.snapshot(), self.editor)), \
                patch('ff11reader.ui.ReaderWindow.configure_windower', autospec=True, side_effect=configure_view):
            launch()
        self.assertEqual(calls, [(True, True)])
        gc.collect()
