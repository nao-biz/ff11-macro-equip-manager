"""The save-state candidate must keep plans and rollback/history semantics."""
import unittest
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from ff11reader.edit_state import SnapshotState
from scoped_save import installed


class ScopedSaveTests(MoveFixture):
    def test_move_plan_matches_baseline_without_full_export(self):
        self.move()
        expected = self.editor.prepare_writeback()
        with installed(), patch.object(SnapshotState, 'export', side_effect=AssertionError('full-state export')):
            actual = self.editor.prepare_writeback()
            self.assertEqual(actual, expected)
            self.editor.writeback(actual, self.base/'backups')
            self.assertFalse(self.editor.session.dirty)
        saved = self.bytes_after_save()
        self.editor.undo()
        self.assertTrue(self.editor.session.dirty)
        self.editor.redo()
        self.assertFalse(self.editor.session.dirty)
        self.assertEqual(self.bytes_after_save(), saved)

    def bytes_after_save(self):
        return {p.name:p.read_bytes() for p in self.folder.iterdir()}

    def test_exported_plan_inputs_cannot_mutate_saved_or_working(self):
        from scoped_save import scoped_snapshot
        before = self.editor.snapshot()
        detached = scoped_snapshot(self.editor._session._working, 'abc')
        detached.characters[0].macros.clear()
        detached.sources[0]['sha256'] = 'changed'
        self.assertEqual(self.editor.snapshot(), before)


if __name__ == '__main__': unittest.main()
