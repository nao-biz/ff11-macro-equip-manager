"""Loaded source ownership, lifecycle and path-resolution regression guards."""
from pathlib import Path
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from ff11reader.loaded_files import LoadedFiles
from ff11reader.edit_application import Editor
from ff11reader.saving import digest


class LoadedFilesTests(MoveFixture):
    def test_owned_records_and_success_updates_are_independent(self):
        files = self.editor._session._saved._files
        exported = files.sources()
        exported[0]['sha256'] = 'outside'
        self.assertNotEqual(files.sources()[0]['sha256'], 'outside')
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc', 1, 'New'))
        self.assertIs(self.editor._session._working._files, files)
        plan = self.editor.prepare_writeback()
        self.editor.writeback(plan, self.base/'backups')
        current = self.editor._session._saved._files
        target = Path(plan[0].files[0].target)
        self.assertNotEqual(files.records()[target]['sha256'], current.records()[target]['sha256'])
        self.assertEqual(current.records()[target]['sha256'], digest(target.read_bytes()))

    def test_repeated_plans_do_not_resolve_unrelated_sources(self):
        unrelated = self.base/'game'/'ROM'/'unrelated.dat'
        unrelated.parent.mkdir()
        unrelated.write_bytes(b'fixture')
        self.source.sources.append({'path':str(unrelated), 'sha256':digest(b'fixture')})
        self.editor = Editor(self.source, self.base/'indexed.json')
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc', 1, 'New'))
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == unrelated: raise AssertionError('resolved unrelated loaded source again')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', resolve):
            first = self.editor.prepare_writeback()
            self.assertEqual(first, self.editor.prepare_writeback())
            self.editor.writeback(first, self.base/'backups')

    def test_changed_parent_resolution_is_rejected(self):
        files = LoadedFiles(self.source.sources)
        with patch.object(Path, 'resolve', return_value=self.base/'redirected'):
            with self.assertRaisesRegex(ValueError, '解決先'):
                files.children(self.folder)

    def test_new_load_builds_new_index_and_failed_save_keeps_old_index(self):
        before = self.editor._session._saved._files
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc', 1, 'New'))
        plans = self.editor.prepare_writeback()
        with patch('ff11reader.elevation.execute_with_permission', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.editor.writeback(plans, self.base/'backups')
        self.assertIs(self.editor._session._saved._files, before)
        reopened = Editor(self.load(), self.base/'reopened.json')
        self.assertIsNot(reopened._session._saved._files, before)
