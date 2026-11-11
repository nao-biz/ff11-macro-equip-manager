"""Generated MNC2 fixtures; no installed game files are used by tests."""
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest

from ff11reader.adapters import LocalReader
from ff11reader.augment_import import parse, export_value
from ff11reader.augment_observation import AugmentItem, reconcile
from ff11reader.augment_presentation import describe
from ff11reader.augment_store import AugmentStore
from ff11reader.domain import Equipset, Slot, Text, Snapshot
from ff11reader.equipment_stats import summarize
from ff11reader.item_properties import describe_item
from ff11reader.rank_augments import RankCatalog, abilities, decode_bundles, format_effect
from tests.test_augment_dictionary import dmsg
from tests.test_augment_import import fixture, encoded, character


def dat(effects, bundle=430):
    size = 12464 + (len(effects) + 1) * 76
    size = (size + 15) // 16 * 16
    data = bytearray(size)
    data[:4] = b'menu'; data[32:36] = b'mnc2'
    struct.pack_into('<I', data, 4, 0x101)
    struct.pack_into('<I', data, 36, ((size - 32) // 16 << 7) | 4)
    for index, (effect, parameter, values) in enumerate(effects, 1):
        struct.pack_into('<H', data, 176 + bundle * 12 + (index - 1) * 2, index)
        struct.pack_into('<HH31h', data, 12464 + index * 76 + 8, effect, parameter, *values)
    return bytes(data)


def item(rank=8, path='A', bundle=430):
    raw = b'\x03\x83\0\0' + struct.pack('<II', (rank << 18) | (3 << 23) | 'ABCD'.index(path), bundle) + bytes(12)
    return AugmentItem(1, 21581, 1, raw.hex(), 'decoded', ('Path: ' + path,), path, rank)


FORMATS = {133: '魔攻%+d ', 1286: 'マジックバーストダメージII%+d ',
           18: '命中%+d ', 24: '魔命%+d ', 143: 'ダブルアタック%+d%% ',
           36: '詠唱中断率%d%%ダウン ', 100: '命中%+d 魔命%+d ',
           128: 'ペット:', 697: '合成WS:', 47: 'ダメージ%+d%% '}


class RankAugmentTests(unittest.TestCase):
    def setUp(self):
        self.effects = ((133, 0, tuple(range(31))),
                        (1286, 0, tuple((r + 4) // 5 for r in range(31))),
                        (2052, 5, tuple(max(0, r - 15) for r in range(31))))
        self.data = dat(self.effects)
        self.catalog = RankCatalog(decode_bundles(self.data), FORMATS)

    def observation(self, value=None, catalog=None):
        data = fixture()
        from dataclasses import asdict
        data['bags'][12]['items'][0] = asdict(value or item())
        export = parse(encoded(data))
        return reconcile(export, character(), catalog or self.catalog)

    def test_rank_8_and_rank_boundaries_use_exact_rows(self):
        self.assertEqual(abilities(item(), self.catalog).lines, ('魔攻+8', 'マジックバーストダメージII+2'))
        for rank in range(31):
            result = abilities(item(rank), self.catalog)
            self.assertTrue(result.complete)
            self.assertEqual(any('命中' in s for s in result.lines), rank > 15)
        self.assertEqual(abilities(item(0), self.catalog).lines, ())
        self.assertIn('命中+15', abilities(item(30), self.catalog).lines)

    def test_masks_percent_compound_and_scoped_effects(self):
        self.assertEqual(format_effect(2052, 5, 7, FORMATS), ('命中+7', '魔命+7'))
        self.assertEqual(format_effect(100, 0, 7, FORMATS), ('命中+7 魔命+7',))
        self.assertEqual(format_effect(143, 0, 3, FORMATS), ('ダブルアタック+3%',))
        self.assertEqual(format_effect(36, 0, 5, FORMATS), ('詠唱中断率5%ダウン',))
        self.assertEqual(format_effect(2064, 100, 7, FORMATS), ('ペット:命中+7 魔命+7',))
        self.assertEqual(format_effect(2076, 697, 10, FORMATS), ('合成WS:ダメージ+10%',))
        for mask in (0, 8):
            with self.assertRaises(ValueError): format_effect(2052, mask, 7, FORMATS)

    def test_corrupt_dat_and_out_of_chunk_record_rejected(self):
        for data in (b'', self.data[:-16], b'x' + self.data[1:]):
            with self.assertRaises(ValueError): decode_bundles(data)
        data = bytearray(self.data)
        struct.pack_into('<H', data, 176 + 430 * 12, 60000)
        with self.assertRaises(ValueError): decode_bundles(data)

    def test_unknown_and_mismatched_metadata_keep_incomplete(self):
        for value, catalog in ((item(), None), (item(bundle=999), self.catalog),
                               (replace(item(), rank=9), self.catalog),
                               (replace(item(), path='B'), self.catalog), (item(31), self.catalog)):
            self.assertFalse(abilities(value, catalog).complete)
        unknown = RankCatalog(decode_bundles(dat(((3000, 1, (1,) * 31),))), FORMATS)
        result = abilities(item(), unknown)
        self.assertFalse(result.complete)
        self.assertIn('3000', result.reason)
        self.assertFalse(result.lines)

    def test_display_and_sum_share_resolution_without_double_count(self):
        # A future export containing strings must not double the DAT contribution.
        observation = self.observation(replace(item(), augments=('魔攻+8',)))
        row = Slot('hands', 'equip', 21581, 12, 1, '')
        master = {21581: {'name': '合成装備', 'description': '魔攻+35'}}
        report = summarize(Equipset(1, Text('', '', 'cp932'), (row,)), master, observation)
        self.assertIn(('魔攻', '', 43), report.totals)
        self.assertIn(('マジックバーストダメージII', '%', 2), report.totals)
        self.assertFalse(report.incomplete)
        self.assertIn('魔攻+8', describe(observation, row))
        self.assertIn('魔攻+8', describe_item(row, master, observation).augments)
        self.assertIn('Rank 8', describe_item(row, master, observation).identity)
        zero = self.observation(item(0))
        self.assertIn('付加能力なし', describe_item(row, master, zero).augments)

    def test_unmatched_location_and_nonbundle_unchanged(self):
        observation = self.observation()
        self.assertIsNone(observation.item(Slot('hands', 'equip', 21581, 12, 2, '')))
        ordinary = replace(item(), extdata='00' * 24, augments=('HP+5',), path=None, rank=None)
        self.assertEqual(abilities(ordinary, self.catalog).lines, ('HP+5',))

    def test_negative_partial_and_scoped_values_in_comparison(self):
        effects = ((133, 0, tuple(-r for r in range(31))),
                   (2064, 100, (7,) * 31), (2076, 697, (10,) * 31),
                   (3000, 0, (1,) * 31))
        catalog = RankCatalog(decode_bundles(dat(effects)), FORMATS)
        observation = self.observation(catalog=catalog)
        row = Slot('hands', 'equip', 21581, 12, 1, '')
        equip = Equipset(1, Text('', '', 'cp932'), (row,))
        report = summarize(equip, {21581: {'description': '魔攻+35'}}, observation)
        self.assertIn(('魔攻', '', 27), report.totals)
        self.assertFalse(any(n in ('命中', '魔命', 'ダメージ') for n, _, _ in report.totals))
        self.assertTrue(report.incomplete)
        self.assertTrue(any('3000' in line for _, line in report.missing))
        later = self.observation(item(9), catalog)
        candidate = summarize(equip, {21581: {'description': '魔攻+35'}}, later)
        self.assertIn(('魔攻', '', 26), candidate.totals)

    def test_adapter_reload_and_persistence_preserve_original_export(self):
        work = Path('work/test-rank-augments'); work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            root = Path(tmp); (root/'ROM/1').mkdir(parents=True)
            table = bytearray((0xD914 + 1) * 2)
            struct.pack_into('<H', table, 0x51 * 2, 128)
            struct.pack_into('<H', table, 0xD914 * 2, 129)
            (root/'FTABLE.DAT').write_bytes(table)
            (root/'ROM/1/0.DAT').write_bytes(self.data)
            dictionary = root/'ROM/1/1.DAT'; dictionary.write_bytes(dmsg(FORMATS))
            reader = LocalReader(root); catalog = reader.load_rank_augments()
            self.assertEqual(reader.verify_unchanged(), [])
            self.assertEqual(len(reader.sources), 3)
            self.assertEqual(abilities(item(), catalog).lines[0], '魔攻+8')
            observation = self.observation()
            original = export_value(observation.export)
            storage = AugmentStore(root/'saved')
            c = character()
            from ff11reader.augment_sources import AugmentSource
            storage.sources.register(AugmentSource('install',c.folder_id,
                observation.export.character_id,observation.export.server,str(root),'synthetic observation'))
            storage.save('install', c.folder_id, observation.export)
            dictionary.write_bytes(dmsg({**FORMATS, 133: '更新能力%+d'}))
            snapshot = Snapshot('id', '', [c], {}, [], [], 'install', rank_augments=reader.load_rank_augments())
            restored, errors = storage.restore(snapshot)
            self.assertFalse(errors)
            current = restored[c.folder_id]
            self.assertEqual(export_value(current.export), original)
            self.assertEqual(current.abilities(current.export.bags[12].items[0]).lines[0], '更新能力+8')
            dictionary.unlink()
            self.assertIsNone(LocalReader(root).load_rank_augments())


if __name__ == '__main__':
    unittest.main()
