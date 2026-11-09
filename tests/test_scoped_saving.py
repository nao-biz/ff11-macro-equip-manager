"""The save-state candidate must keep plans and rollback/history semantics."""
import unittest
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from ff11reader.edit_state import SnapshotState
from ff11reader.save_state import SaveRequest, storage_member
from dataclasses import replace


class ScopedSaveTests(MoveFixture):
    def test_narrow_plan_matches_full_plan_and_copies_only_changed_records(self):
        from ff11reader.combined_saving import prepare_combined_save
        scoped_snapshot = SnapshotState.save_input
        self.rename('Narrow')
        session = self.editor._session
        expected = prepare_combined_save(session.saved, session.working, 'abc', ())
        with patch.object(SnapshotState, 'save_input', autospec=True, side_effect=scoped_snapshot) as copying:
            actual = self.editor.prepare_writeback()[0]
        self.assertEqual(actual, expected)
        for call in copying.call_args_list:
            detached = scoped_snapshot(*call.args)
            self.assertEqual(len(detached.characters[0].macros), 1)
            self.assertEqual(detached.characters[0].equipsets, [])

    def rename(self, title):
        macro = self.editor._session.read('abc', 'macros', (1, 1, 'ctrl', 1))
        self.editor.apply(self.editor.prepare_macro_edit('abc', (1, 1, 'ctrl', 1),
            title, [line.display for line in macro.lines]))

    def test_compaction_preserves_history_and_discards_reverted_changes(self):
        self.rename('B')
        self.rename('C')
        request = SaveRequest.capture(self.editor._session)
        self.assertEqual(len(request.identities), 1)
        self.assertEqual(request.members('abc'), {('abc', 'macros', 0)})
        self.assertEqual(self.editor._session.history_length(), 2)
        self.editor.undo()
        self.editor.undo()
        self.assertEqual(self.editor.prepare_writeback(), ())
        self.assertEqual(self.editor._session.history_length(), 2)
        # Captured state remains C even after the live session returns to A.
        self.assertEqual(request.session.read('abc', 'macros', (1, 1, 'ctrl', 1)).title.display, 'C')

    def test_unrelated_file_in_plan_is_rejected(self):
        self.rename('B')
        request = SaveRequest.capture(self.editor._session)
        plan = request.prepare('abc')
        extra = replace(plan.macro.files[0], page=1)
        corrupted = replace(plan, macro=replace(plan.macro, files=plan.macro.files+(extra,)))
        with self.assertRaisesRegex(ValueError, 'ファイル範囲'):
            request.validate_scope(corrupted)
        missing = replace(plan, macro=replace(plan.macro, files=()))
        with self.assertRaisesRegex(ValueError, 'ファイル範囲'):
            request.validate_scope(missing)

    def test_storage_boundaries(self):
        self.assertEqual(storage_member(('abc', 'macros', (2, 1, 'alt', 10))), ('abc', 'macros', 10))
        self.assertEqual(storage_member(('abc', 'equipsets', (20,))), ('abc', 'equipsets', 0))
        self.assertEqual(storage_member(('abc', 'equipsets', (21,))), ('abc', 'equipsets', 1))

    def test_return_to_original_needs_no_write_and_stale_plan_is_rejected(self):
        original = self.editor._session.read('abc', 'macros', (1, 1, 'ctrl', 1)).title.display
        self.rename('B')
        plans = self.editor.prepare_writeback()
        self.rename(original)
        self.assertEqual(self.editor.prepare_writeback(), ())
        with self.assertRaisesRegex(ValueError, '編集内容'):
            self.editor.writeback(plans, self.base/'backups')
        self.assertEqual({p:p.read_bytes() for p in self.original}, self.original)
        self.assertEqual(self.editor._session.history_length(), 2)

    def test_unrelated_characters_are_not_materialized_or_selected(self):
        from ff11reader.edit_application import Editor
        scoped_snapshot = SnapshotState.save_input
        extra = [replace(self.source.characters[0], folder_id=f'extra{i}') for i in range(20)]
        self.editor = Editor(replace(self.source, characters=self.source.characters+extra), self.base/'many.json')
        self.rename('B')
        with patch.object(SnapshotState, 'save_input', autospec=True, side_effect=scoped_snapshot) as materialize:
            plans = self.editor.prepare_writeback()
        self.assertEqual([call.args[1] for call in materialize.call_args_list], ['abc', 'abc'])
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(plans[0].files), 1)

    def test_move_save_avoids_full_export_and_keeps_history(self):
        self.move()
        expected = self.editor.prepare_writeback()
        with patch.object(SnapshotState, 'export', side_effect=AssertionError('full-state export')):
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
        scoped_snapshot = SnapshotState.save_input
        before = self.editor.snapshot()
        detached = scoped_snapshot(self.editor._session._working, 'abc')
        detached.characters[0].macros.clear()
        detached.sources[0]['sha256'] = 'changed'
        self.assertEqual(self.editor.snapshot(), before)


if __name__ == '__main__': unittest.main()
