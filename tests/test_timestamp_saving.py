"""Hash detection despite preserved timestamps and repeated saves against isolated game-format fixtures."""
import os
from pathlib import Path
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from ff11reader.edit_application import Editor


class TimestampSavingTests(MoveFixture):
    def load(self):
        snapshot = super().load()
        for source in snapshot.sources:
            source['mtime_ns'] = Path(source['path']).stat().st_mtime_ns
        return snapshot

    def setUp(self):
        super().setUp()
        for source in self.source.sources:
            source['mtime_ns'] = Path(source['path']).stat().st_mtime_ns
        self.editor = Editor(self.source, self.base/'timestamp.json')

    def rename(self, name):
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc', 1, name))

    def test_macro_reload_validation_and_second_save(self):
        for name in ('First', 'Second'):
            macro = self.editor._session.read('abc', 'macros', (1, 1, 'ctrl', 1))
            self.editor.apply(self.editor.prepare_macro_edit('abc', (1, 1, 'ctrl', 1), name, macro.lines))
            self.editor.writeback(self.editor.prepare_writeback(), self.base/'backups')
            self.assertFalse(self.editor.session.dirty)
            self.assertEqual(self.load().characters[0].macros[0].title.display, name)

    def test_timestamp_only_change_keeps_same_content_valid(self):
        self.rename('Changed')
        plans = self.editor.prepare_writeback()
        path = self.folder/'mcr1.dat'
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns+1000000000))
        self.editor.writeback(plans, self.base/'backups')

    def test_preserved_timestamp_content_change_is_rejected(self):
        self.rename('Changed')
        plans = self.editor.prepare_writeback()
        path = self.folder/'mcr1.dat'
        stat = path.stat()
        raw = bytearray(path.read_bytes()); raw[0] ^= 1
        path.write_bytes(raw)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, '変わりました'):
            self.editor.writeback(plans, self.base/'backups')
        self.assertEqual(path.read_bytes(), raw)
