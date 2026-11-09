"""Reload tests use generated game files and application drafts only."""
from pathlib import Path
import os
import tkinter as tk
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from tests.test_saving import checksum
from ff11reader.edit_application import Editor


class ReloadTests(MoveFixture):
    def tearDown(self):
        import gc
        gc.collect()

    def setUp(self):
        super().setUp()
        self.editor.root=self.folder.parent.parent

    def test_reload_discards_history_and_loads_latest(self):
        self.move();self.editor.capture_transfer('abc','equipment',((45,),))
        path=self.folder/'es0.dat'
        raw=bytearray(path.read_bytes());raw[24:29]=b'Fresh';path.write_bytes(checksum(raw))
        game={p:p.read_bytes() for p in self.folder.iterdir()}
        self.editor.reload()
        self.assertEqual(self.editor.edit_status(),(0,0,False))
        self.assertIsNone(self.editor.transfer)
        self.assertEqual(self.editor.snapshot().characters[0].equipsets[0].title.display,'Fresh')
        self.assertFalse(self.editor.state_path.exists())
        self.assertEqual(game,{p:p.read_bytes() for p in self.folder.iterdir()})

    def test_read_failure_keeps_history_and_transfer(self):
        self.move();self.editor.capture_transfer('abc','equipment',((45,),))
        before=self.editor.snapshot();status=self.editor.edit_status();transfer=self.editor.transfer
        with patch('ff11reader.application.load_snapshot',side_effect=OSError('read failure')):
            with self.assertRaises(OSError):self.editor.reload()
        self.assertEqual(self.editor.snapshot(),before)
        self.assertEqual(self.editor.edit_status(),status);self.assertEqual(self.editor.transfer,transfer)

    def test_pending_recovery_prevents_reload_and_reset(self):
        self.move();status=self.editor.edit_status()
        self.editor.journal.path.write_text('{}')
        with patch('ff11reader.application.load_snapshot') as read:
            for action in (self.editor.reload,self.editor.start_fresh):
                with self.assertRaisesRegex(ValueError,'復旧'):action()
            read.assert_not_called()
        self.assertEqual(self.editor.edit_status(),status)

    def test_wrong_installation_keeps_work(self):
        self.move();before=self.editor.snapshot()
        fresh=self.load();fresh.installation_key='different'
        with patch('ff11reader.application.load_snapshot',return_value=fresh):
            with self.assertRaisesRegex(ValueError,'インストール先'):self.editor.reload()
        self.assertEqual(self.editor.snapshot(),before)

    def test_cancel_and_confirm_ui(self):
        if os.environ.get('FF11_RUN_INTEGRATION')!='1':self.skipTest('Enable synthetic Tk checks')
        from ff11reader.ui import ReaderWindow
        app=tk.Tk();app.withdraw()
        try:
            self.move();view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            with patch('ff11reader.ui.dialogs.askyesno',return_value=False),patch.object(self.editor,'reload') as reload:
                view.reload_button.invoke();reload.assert_not_called()
            with patch('ff11reader.ui.dialogs.askyesno',return_value=True):view.reload_button.invoke()
            self.assertEqual(self.editor.edit_status(),(0,0,False))
            self.assertIn('最新',view.footer.cget('text'))
            self.assertEqual(view.character.folder_id,'abc')
            self.assertEqual(str(view.undo_button.cget('state')),'disabled')
            fresh=self.load();fresh.characters=[]
            with patch('ff11reader.application.load_snapshot',return_value=fresh),patch('ff11reader.ui.dialogs.askyesno',return_value=True):view.reload_button.invoke()
            self.assertIsNone(view.character)
            self.assertEqual(view.navigation,[])
            self.assertEqual(str(view.edit_button.cget('state')),'disabled')
        finally:app.destroy()

    def test_slow_reload_keeps_native_event_loop_responsive(self):
        if os.environ.get('FF11_RUN_INTEGRATION')!='1':self.skipTest('Enable synthetic Tk checks')
        from threading import get_ident
        import time
        from ff11reader.ui import ReaderWindow
        from ff11reader.ui_tasks import tasks
        from tests.test_ui_tasks import TkThreadGuard
        app=tk.Tk();app.tk=TkThreadGuard(app.tk)
        errors=[];app.report_callback_exception=lambda *args:errors.append(args)
        ticks=[];frames=[];worker_threads=[];job=None
        try:
            view=ReaderWindow(app,self.source,editor=self.editor);app.update()
            owner=get_ident();original=self.editor.reload
            def slow_reload():
                worker_threads.append(get_ident())
                end=time.monotonic()+6.2
                # CPU-bound Python work as well as file work must leave Tk responsive.
                while time.monotonic()<end:sum(range(2000))
                return original()
            def heartbeat():
                nonlocal job
                ticks.append(time.monotonic())
                runner=tasks(app)
                if runner.screen and runner.screen.progress:
                    frames.append(float(runner.screen.progress[0]['value']))
                app.geometry('1200x740' if len(ticks)%2 else '1220x760')
                job=app.after(40,heartbeat)
            job=app.after(40,heartbeat)
            start=time.monotonic()
            with patch.object(self.editor,'reload',side_effect=slow_reload),patch('ff11reader.ui.dialogs.askyesno',return_value=True):
                view.reload_button.invoke()
            elapsed=time.monotonic()-start
            self.assertGreaterEqual(elapsed,6)
            self.assertGreater(len(ticks),30)
            self.assertLess(max(b-a for a,b in zip(ticks,ticks[1:])),1.0)
            self.assertGreater(len(set(frames)),3)
            self.assertNotEqual(worker_threads,[owner])
            self.assertFalse(errors)
            self.assertIn('最新',view.footer.cget('text'))
            self.assertFalse(tasks(app).running)
            print(f'Reload responsiveness: {elapsed:.2f}s, {len(ticks)} UI ticks, max gap {max(b-a for a,b in zip(ticks,ticks[1:])):.3f}s')
        finally:
            if job:app.after_cancel(job)
            app.destroy()
