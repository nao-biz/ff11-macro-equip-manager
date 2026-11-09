"""Save-facing contracts preserve ownership and publish only after verified execution."""
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture


class SaveSessionContractTests(MoveFixture):
    def test_capture_and_plan_inputs_are_independent(self):
        self.move()
        before = self.editor.snapshot()
        captured = self.editor.capture_save_session()
        identities = captured.changes_since_save()
        saved, working, sources = captured.save_inputs('abc', identities)
        saved.characters[0].macros.clear()
        working.characters[0].equipsets.clear()
        sources.sources()[0]['sha256'] = 'outside'
        captured.undo()
        self.assertEqual(self.editor.snapshot(), before)
        self.assertTrue(self.editor.session.dirty)

    def test_cross_character_checkpoint_is_rejected(self):
        captured = self.editor.capture_save_session()
        record = captured.read('abc', 'equipsets', (1,))
        with self.assertRaisesRegex(ValueError, '別キャラ'):
            captured.record_saved('abc', {('other', 'equipsets', (1,)):record})

    def test_failed_execution_does_not_publish_candidate(self):
        self.move()
        before = self.editor.snapshot()
        plans = self.editor.prepare_writeback()
        with patch.object(self.editor, 'publish_saved_session', wraps=self.editor.publish_saved_session) as publish:
            with patch('ff11reader.elevation.execute_with_permission', side_effect=OSError('injected')):
                with self.assertRaises(OSError):
                    self.editor.writeback(plans, self.base/'backups')
            publish.assert_not_called()
        self.assertEqual(self.editor.snapshot(), before)
        self.assertTrue(self.editor.session.dirty)
