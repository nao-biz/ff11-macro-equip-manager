"""Bilingual augment DAT loading using generated files, without installed assets."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from ff11reader.adapters import LocalReader
from ff11reader.application import load_snapshot
from ff11reader.edit_application import Editor
from ff11reader.equipment_stats import parse_line


def dmsg(strings):
    count, size = max(strings) + 1, 160
    body = bytearray(count * size)
    for i in range(count):
        struct.pack_into('<III', body, i * size, 1, 12, 0)
        value = strings.get(i, '').encode('cp932')
        body[i * size + 40:i * size + 40 + len(value)] = value
    header = bytearray(64); header[:8] = b'd_msg\0\0\0'
    struct.pack_into('<Q6I', header, 12, 0x300000003, 64 + len(body), 64, 0, size, len(body), count)
    return bytes(header + body)


class AugmentDictionaryTests(unittest.TestCase):
    def setUp(self):
        work = Path('work/test-augment-dictionary'); work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'USER').mkdir(); (self.root/'ROM'/'1').mkdir(parents=True)
        self.en = self.root/'ROM'/'1'/'0.DAT'; self.ja = self.root/'ROM'/'1'/'1.DAT'
        self.en.write_bytes(dmsg({2: 'Accuracy%+d', 7: 'New ability%+d', 8: 'Haste%+d%%'}))
        self.ja.write_bytes(dmsg({7: '新能力%+d', 2: '命中%+d', 8: 'ヘイスト%+d'}))
        table = bytearray((0xD98C + 1) * 2)
        struct.pack_into('<H', table, 0xD98C * 2, 128)
        struct.pack_into('<H', table, 0xD914 * 2, 129)
        (self.root/'FTABLE.DAT').write_bytes(table)

    def test_read_by_resource_id_and_track_unchanged_sources(self):
        reader = LocalReader(self.root)
        names = reader.load_augment_names()
        self.assertEqual(parse_line('New ability+12 Accuracy+5 Haste+3', names),
                         [('新能力', '', 12), ('命中', '', 5), ('ヘイスト', '%', 3)])
        self.assertEqual(len(reader.sources), 3)
        self.assertEqual(reader.verify_unchanged(), [])
        self.assertFalse(reader.diagnostics)

    def test_missing_corrupt_and_truncated_sources_do_not_invent_names(self):
        self.ja.unlink()
        reader = LocalReader(self.root)
        self.assertEqual(reader.load_augment_names(), {})
        self.assertTrue(reader.diagnostics)
        self.ja.write_bytes(b'unsupported')
        self.assertEqual(LocalReader(self.root).load_augment_names(), {})
        (self.root/'FTABLE.DAT').write_bytes(b'')
        self.assertEqual(LocalReader(self.root).load_augment_names(), {})

    def test_master_names_are_readonly_until_application_restart(self):
        with patch.object(LocalReader, 'load_items', return_value={}), patch.object(LocalReader, 'load_phrases', return_value={}):
            source = load_snapshot(self.root)
            editor = Editor(source, self.root/'draft.json', root=self.root)
            detached = editor.snapshot()
            with self.assertRaises(TypeError): detached.augment_names['new'] = 'changed'
            self.assertEqual(parse_line('New ability+12', editor.snapshot().augment_names), [('新能力', '', 12)])
            self.ja.write_bytes(dmsg({7: '更新能力%+d', 2: '命中%+d', 8: 'ヘイスト%+d'}))
            editor.reload()
            self.assertIs(editor.snapshot().master_data, source.master_data)
            self.assertEqual(parse_line('New ability+12', editor.snapshot().augment_names), [('新能力', '', 12)])
            restarted = load_snapshot(self.root)
            self.assertEqual(parse_line('New ability+12', restarted.augment_names), [('更新能力', '', 12)])
