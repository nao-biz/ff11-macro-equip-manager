"""Synthetic draft replacement failures, recovery and concurrent external edits."""
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ff11reader.draft_store import DraftStore
from ff11reader.edit_application import Editor
from tests.test_editing import snapshot


def windows_error(code=5):
    error = PermissionError('synthetic Windows replacement denial')
    error.winerror = code
    return error


class DraftReplacementTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'work' / 'draft-store-tests'
        root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'draft.json'
        self.source = snapshot()
        self.editor = Editor(self.source, self.path)
        self.editor.apply(self.edit('First'))
        self.original = self.path.read_bytes()
        self.revision = self.editor.store.revision
        self.state = self.editor.snapshot()
        self.status = self.editor.edit_status()

    def edit(self, title):
        return self.editor.prepare_macro_edit('one', (1, 1, 'ctrl', 1), title, [''] * 6)

    def assert_original_state(self):
        self.assertEqual(self.editor.snapshot(), self.state)
        self.assertEqual(self.editor.edit_status(), self.status)
        self.assertEqual(self.editor.store.revision, self.revision)
        self.assertFalse(self.path.with_suffix('.lock').exists())
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_transient_windows_denials_publish_once_and_reopen_history(self):
        actual_replace = Path.replace
        failures = [windows_error(code) for code in (5, 32, 33)]
        attempts = []
        def replace(temp, target):
            attempts.append(temp)
            self.assertEqual(self.path.read_bytes(), self.original)
            self.assertEqual(self.editor.edit_status(), self.status)
            if failures:
                raise failures.pop(0)
            return actual_replace(temp, target)
        with patch.object(Path, 'replace', replace), patch('ff11reader.draft_store.time.sleep'):
            self.editor.apply(self.edit('Second'))
        self.assertEqual(len(attempts), 4)
        self.assertEqual(len(set(attempts)), 1)
        self.assertEqual(self.editor.edit_status(), (2, 2, True))
        reopened = Editor(self.source, self.path)
        self.assertIsNone(reopened.blocked)
        self.assertEqual(reopened.snapshot(), self.editor.snapshot())
        reopened.undo()
        self.assertEqual(reopened.snapshot(), self.state)
        reopened.redo()
        self.assertEqual(reopened.snapshot(), self.editor.snapshot())

    def test_persistent_denial_is_bounded_and_preserves_state_then_recovers(self):
        error = windows_error()
        with patch.object(Path, 'replace', side_effect=error) as replace, \
                patch('ff11reader.draft_store.time.sleep') as sleep:
            with self.assertRaises(PermissionError) as raised:
                self.editor.apply(self.edit('Second'))
        self.assertIs(raised.exception, error)
        self.assertLessEqual(replace.call_count, 10)
        self.assertGreater(replace.call_count, 1)
        self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), 0.5)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assert_original_state()
        self.editor.apply(self.edit('Second'))
        self.assertEqual(self.editor.edit_status(), (2, 2, True))

    def test_other_errors_are_not_retried(self):
        for error in (PermissionError('not a Windows sharing failure'), OSError('disk error'), windows_error(112)):
            with self.subTest(error=error), patch.object(Path, 'replace', side_effect=error) as replace, \
                    patch('ff11reader.draft_store.time.sleep') as sleep:
                with self.assertRaises(OSError) as raised:
                    self.editor.apply(self.edit('Second'))
                self.assertIs(raised.exception, error)
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(self.path.read_bytes(), self.original)
                self.assert_original_state()

    def test_external_update_or_deletion_during_wait_is_preserved(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted):
                self.path.write_bytes(self.original)
                def external_change(delay):
                    if deleted:
                        self.path.unlink()
                    else:
                        self.path.write_bytes(b'external edit')
                with patch.object(Path, 'replace', side_effect=windows_error()) as replace, \
                        patch('ff11reader.draft_store.time.sleep', side_effect=external_change):
                    with self.assertRaisesRegex(ValueError, '別の画面'):
                        self.editor.apply(self.edit('Second'))
                replace.assert_called_once()
                if deleted:
                    self.assertFalse(self.path.exists())
                else:
                    self.assertEqual(self.path.read_bytes(), b'external edit')
                self.assert_original_state()

    def test_store_lock_is_held_while_waiting(self):
        other = DraftStore(self.path)
        def competing_save(delay):
            with self.assertRaises(FileExistsError):
                other.save(self.editor.session)
        with patch.object(Path, 'replace', side_effect=windows_error()), \
                patch('ff11reader.draft_store.time.sleep', side_effect=competing_save):
            with self.assertRaises(PermissionError):
                self.editor.apply(self.edit('Second'))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assert_original_state()

    def test_first_save_does_not_overwrite_a_file_created_during_wait(self):
        target = self.path.parent / 'new-draft.json'
        editor = Editor(self.source, target)
        edit = editor.prepare_macro_edit('one', (1, 1, 'ctrl', 1), 'New', [''] * 6)
        with patch.object(Path, 'replace', side_effect=windows_error()) as replace, \
                patch('ff11reader.draft_store.time.sleep', side_effect=lambda delay: target.write_bytes(b'external')):
            with self.assertRaisesRegex(ValueError, '別の画面'):
                editor.apply(edit)
        replace.assert_called_once()
        self.assertEqual(target.read_bytes(), b'external')
        self.assertEqual(editor.edit_status(), (0, 0, False))
        self.assertIsNone(editor.store.revision)

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_real_reader_handle_releases_before_retry(self):
        with self.path.open('rb') as reader:
            def release_reader(delay):
                self.assertEqual(self.editor.edit_status(), self.status)
                self.assertEqual(self.path.read_bytes(), self.original)
                reader.close()
            with patch('ff11reader.draft_store.time.sleep', side_effect=release_reader) as sleep:
                self.editor.apply(self.edit('Second'))
            self.assertTrue(reader.closed)
            self.assertGreater(sleep.call_count, 0)
        self.assertEqual(self.editor.edit_status(), (2, 2, True))
        self.assertEqual(Editor(self.source, self.path).snapshot(), self.editor.snapshot())


class CheckpointReplacementTests(unittest.TestCase):
    def test_complete_checkpoint_uses_one_publication_with_bounded_retry(self):
        from tests.property_support import GameFixture, isolated
        with isolated() as base:
            fixture=GameFixture(base,'macro',127,1);fixture.fix();plan=fixture.preview()
            pending=fixture.editor.store.path.with_suffix('.pending.json')
            actual=Path.replace;attempts=[]
            def replace(temp,target):
                if Path(target)==pending:
                    data=json.loads(temp.read_text(encoding='utf-8'))
                    self.assertEqual(data['draft_revision'],fixture.editor.store.revision)
                    self.assertEqual(fixture.bytes(),fixture.all_original)
                    self.assertFalse(pending.exists())
                    attempts.append(temp)
                    if len(attempts)<3:raise windows_error()
                return actual(temp,target)
            with patch.object(Path,'replace',replace),patch('ff11reader.draft_store.time.sleep'):
                fixture.save(plan)
            self.assertEqual(len(attempts),3);self.assertEqual(len(set(attempts)),1)
            self.assertFalse(pending.exists());fixture.reopen()
            self.assertIsNone(fixture.editor.blocked);self.assertFalse(fixture.editor.session.dirty)

    def test_failed_checkpoint_keeps_game_and_work_then_can_retry(self):
        from tests.property_support import GameFixture, isolated
        with isolated() as base:
            fixture=GameFixture(base,'macro',127,1);fixture.fix();plan=fixture.preview()
            pending=fixture.editor.store.path.with_suffix('.pending.json')
            original=fixture.editor.store.path.read_bytes();status=fixture.editor.edit_status()
            actual=Path.replace
            def replace(temp,target):
                if Path(target)==pending:raise windows_error()
                return actual(temp,target)
            with patch.object(Path,'replace',replace),patch('ff11reader.draft_store.time.sleep'):
                with self.assertRaises(PermissionError):fixture.save(plan)
            self.assertEqual(fixture.bytes(),fixture.all_original)
            self.assertEqual(fixture.editor.store.path.read_bytes(),original)
            self.assertEqual(fixture.editor.edit_status(),status)
            self.assertFalse(pending.exists());self.assertFalse(list(base.glob('*.tmp')))
            fixture.save(plan);fixture.reopen();self.assertIsNone(fixture.editor.blocked)
