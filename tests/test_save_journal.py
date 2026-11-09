"""Game-write recovery keeps fingerprints, never resumable edit history."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from ff11reader.edit_application import Editor
from tests import test_macro_saving as fixtures


class SaveJournalTests(unittest.TestCase):
    setUp = fixtures.MacroSavingTests.setUp
    load = fixtures.MacroSavingTests.load

    def test_edit_history_is_memory_only_and_old_drafts_are_ignored(self):
        path = self.editor.state_path
        self.assertFalse(path.exists())
        path.write_text('old corrupt draft', encoding='utf-8')
        self.editor.undo(); self.editor.redo()
        reopened = Editor(self.load(), path)
        self.assertIsNone(reopened.blocked)
        self.assertEqual(reopened.edit_status(), (0, 0, False))
        self.assertEqual(path.read_text(encoding='utf-8'), 'old corrupt draft')

    def test_journal_has_only_target_fingerprints_and_rejects_concurrent_save(self):
        self.editor.journal.begin(self.plan).close()
        raw = self.editor.journal.path.read_bytes()
        data = json.loads(raw)
        self.assertEqual(set(data), {'version', 'installation', 'files'})
        self.assertEqual(len(data['files']), 2)
        self.assertEqual(set(data['files'][0]), {'path', 'before', 'after'})
        with self.assertRaises(FileExistsError): self.editor.journal.begin(self.plan)
        self.assertEqual(self.editor.journal.path.read_bytes(), raw)
        reopened = Editor(self.load(), self.editor.state_path)
        self.assertIsNone(reopened.blocked)
        self.assertEqual(reopened.edit_status(), (0, 0, False))
        self.assertFalse(reopened.journal.path.exists())

    def test_journal_failure_precedes_game_write_and_preserves_edits(self):
        before = self.editor.snapshot(); status = self.editor.edit_status()
        with patch('ff11reader.save_journal.json.dump', side_effect=OSError('full')):
            with self.assertRaises(OSError): self.editor.save_macros(self.plan, self.base / 'backups')
        self.assertEqual(self.editor.snapshot(), before)
        self.assertEqual(self.editor.edit_status(), status)
        self.assertFalse(self.editor.journal.path.exists())
        for f in self.plan.files: self.assertEqual(Path(f.target).read_bytes(), f.original)

    def test_partial_write_blocks_but_completed_write_loads_fresh(self):
        self.editor.journal.begin(self.plan).close()
        first = self.plan.files[0]; Path(first.target).write_bytes(first.replacement)
        blocked = Editor(self.load(), self.editor.state_path)
        self.assertTrue(blocked.blocked)
        with self.assertRaises(ValueError): blocked.undo()
        for f in self.plan.files: Path(f.target).write_bytes(f.replacement)
        fresh = Editor(self.load(), self.editor.state_path)
        self.assertIsNone(fresh.blocked)
        self.assertEqual(fresh.edit_status(), (0, 0, False))
        self.assertFalse(fresh.journal.path.exists())

    def test_legacy_pending_uses_sources_only_without_restoring_history(self):
        sources = sorted((str(s['path']), s['sha256']) for s in self.source.sources)
        data = {'version': 4, 'installation': self.source.installation_key,
                'sources': sources, 'history': 'not an edit history', 'cursor': 999}
        self.editor.journal.path.write_text(json.dumps(data), encoding='utf-8')
        fresh = Editor(self.load(), self.editor.state_path)
        self.assertIsNone(fresh.blocked)
        self.assertEqual(fresh.edit_status(), (0, 0, False))

    def test_unknown_target_and_corrupt_journal_are_preserved(self):
        for data in ('broken', json.dumps({'version': 1, 'installation': 'test',
                                         'files': [{'path': 'outside', 'before': 'a', 'after': 'b'}]})):
            self.editor.journal.path.write_text(data, encoding='utf-8')
            blocked = Editor(self.load(), self.editor.state_path)
            self.assertTrue(blocked.blocked)
            self.assertEqual(blocked.journal.path.read_text(encoding='utf-8'), data)

    @unittest.skipUnless(os.name == 'nt', 'Windows game-write exclusion')
    def test_starting_another_window_cannot_remove_active_write_record(self):
        with self.editor.journal.begin(self.plan):
            raw = self.editor.journal.path.read_bytes()
            other = Editor(self.load(), self.editor.state_path)
            self.assertTrue(other.blocked)
            self.assertEqual(self.editor.journal.path.read_bytes(), raw)
        fresh = Editor(self.load(), self.editor.state_path)
        self.assertIsNone(fresh.blocked)
        self.assertFalse(fresh.journal.path.exists())
