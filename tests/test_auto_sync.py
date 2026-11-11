"""Automatic synchronization against generated files and injected process state."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from ff11reader.sync_observation import SyncObserver, SyncConflict
from tests.test_equipment_moves import MoveFixture
from tests.test_saving import checksum


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root/'USER'/'abc'/'inventory.dat'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'old')
        self.running = False
        self.observer = SyncObserver(self.root, [], self.root/'config', probe=lambda:self.running)

    def test_running_does_not_read_then_requires_stable_files(self):
        self.running = True
        with patch.object(self.observer, 'paths', side_effect=AssertionError('read while running')):
            self.assertEqual(self.observer.sample().state, 'running')
        self.running = False
        self.assertEqual(self.observer.sample().state, 'settling')
        ready = self.observer.sample()
        self.assertEqual(ready.state, 'ready')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('unnecessary hash')):
            self.assertEqual(self.observer.sample(), ready)
        self.file.write_bytes(b'new')
        with self.assertRaises(ValueError):self.observer.validate(ready)

    def test_exit_rehashes_even_same_size_and_timestamp(self):
        self.observer.sample();before = self.observer.sample()
        stamp = self.file.stat()
        self.running = True;self.observer.sample()
        self.file.write_bytes(b'new')
        os.utime(self.file, ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        self.running = False
        self.assertEqual(self.observer.sample().state, 'settling')
        self.assertNotEqual(self.observer.sample().data, before.data)


class SynchronizeTests(MoveFixture):
    def setUp(self):
        super().setUp()
        self.editor.root = self.folder.parent.parent

    def test_inventory_refresh_preserves_move_undo_redo_and_pending_input(self):
        self.move()
        before = self.editor.edit_status()
        fresh = self.load()
        from tests.test_augment_import import character
        fresh.characters[0].inventory = character().inventory
        with patch('ff11reader.application.load_snapshot',return_value=fresh):
            self.editor.synchronize(pending_input=True)
        self.assertEqual(self.editor.snapshot().characters[0].inventory, fresh.characters[0].inventory)
        self.assertEqual(self.editor.edit_status(), before)
        self.assertTrue(self.editor.has_pending_move('abc'))
        self.assertEqual(self.editor.snapshot().characters[0].equipsets[44].title.display, 'Set A')
        self.editor.undo();self.assertFalse(self.editor.edit_status()[2])
        self.assertEqual(self.editor.snapshot().characters[0].inventory, fresh.characters[0].inventory)
        self.editor.redo();self.assertEqual(self.editor.edit_status(), before)

    def change_game(self):
        path = self.folder/'es0.dat'
        raw = bytearray(path.read_bytes());raw[24:29] = b'Other'
        path.write_bytes(checksum(raw))

    def test_external_edit_conflict_retains_work_and_pending_text(self):
        self.move();before = self.editor.snapshot()
        self.change_game()
        with self.assertRaises(SyncConflict):self.editor.synchronize()
        self.assertEqual(self.editor.snapshot(), before)
        self.editor.start_fresh()
        with self.assertRaises(SyncConflict):self.editor.synchronize(pending_input=True)
        self.editor.synchronize()
        self.assertEqual(self.editor.snapshot().characters[0].equipsets[0].title.display, 'Other')

    def test_validation_failure_does_not_publish(self):
        before = self.editor.snapshot();self.change_game()
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.editor.synchronize(validate=lambda:(_ for _ in ()).throw(ValueError('changed')))
        self.assertEqual(self.editor.snapshot(), before)
