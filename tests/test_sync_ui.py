"""Synthetic Tk/process transitions; never starts the game or changes its files."""
import gc
import os
import tkinter as tk
import unittest
from unittest.mock import patch
from ff11reader.sync_observation import SyncObserver, Observation
from ff11reader.sync_ui import SyncMonitor
from ff11reader.ui_operation_state import operations
from ff11reader.ui import ReaderWindow
from ff11reader.ui_actions import run_action
from tests.test_auto_sync import SynchronizeTests
from tests.test_ui_tasks import TkThreadGuard


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class SyncUITests(SynchronizeTests):
    def setUp(self):
        super().setUp()
        self.app = tk.Tk();self.app.tk = TkThreadGuard(self.app.tk)
        self.view = ReaderWindow(self.app,self.editor.snapshot(),editor=self.editor)
        self.observer = SyncObserver(self.editor.root,self.view.snapshot.sources,self.base,probe=lambda:False)
        self.monitor = SyncMonitor(self.view,observer=self.observer,interval=30000)
        self.monitor.stop.set();self.monitor.worker.join(2)
        self.addCleanup(self.cleanup_ui)
        self.app.update()

    def cleanup_ui(self):
        self.monitor.unblock();self.app.destroy()
        gc.collect()

    def ready(self):
        self.observer.sample()
        return self.observer.sample()

    def test_gate_retains_edits_and_pending_macro_then_refreshes_only_once(self):
        self.move();self.view.refresh_edits()
        macro = self.view.character.macros[0]
        from ff11reader.editing import macro_key
        key = ('abc',macro_key(macro))
        # Existing pending-map contract stores the source, title and six line values.
        self.view.macro_panel.pending[key] = (macro,'Pending',macro.lines)
        before = self.editor.edit_status()
        self.monitor.accept(self.ready())
        self.monitor.accept(Observation('running'))
        calls = []
        run_action(self.app,lambda:calls.append('edit'))
        self.assertFalse(calls)
        self.assertIsNotNone(self.monitor.screen)
        self.assertTrue(operations(self.app).game_blocked)
        with patch.object(self.editor,'synchronize',wraps=self.editor.synchronize) as reload:
            self.monitor.accept(self.ready());self.monitor.accept(self.ready())
            reload.assert_not_called()
        self.assertIsNone(self.monitor.screen)
        self.assertEqual(self.editor.edit_status(),before)
        self.assertEqual(self.view.macro_panel.pending[key][1],'Pending')
        run_action(self.app,lambda:calls.append('edit'));self.assertEqual(calls,['edit'])

    def test_changed_game_automatically_loads_but_conflict_keeps_edits(self):
        self.monitor.accept(self.ready())
        self.change_game()
        with patch.object(self.editor,'synchronize',wraps=self.editor.synchronize) as reload:
            self.monitor.accept(self.ready());self.monitor.accept(self.ready())
            self.assertEqual(reload.call_count,1)
        self.assertEqual(self.view.character.equipsets[0].title.display,'Other')
        self.move()
        raw = bytearray((self.folder/'es0.dat').read_bytes());raw[24:29] = b'Third'
        from tests.test_saving import checksum
        (self.folder/'es0.dat').write_bytes(checksum(raw))
        before = self.editor.snapshot()
        self.monitor.accept(self.ready())
        self.assertEqual(self.editor.snapshot(),before)
        self.assertTrue(self.editor.blocked)
        self.assertEqual(str(self.view.save_button['state']),'disabled')
        self.assertIn('競合',self.view.footer['text'])
