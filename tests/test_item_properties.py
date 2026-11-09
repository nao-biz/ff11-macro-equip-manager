"""Selected properties from synthetic descriptions and exact individual observations."""
from dataclasses import replace
import unittest

from ff11reader.augment_observation import AugmentBag, AugmentExport, AugmentItem, AugmentObservation
from ff11reader.domain import InventoryRow, Slot
from ff11reader.equipment_stat_names import from_dictionary
from ff11reader.item_properties import ItemProperties, describe_item, format_properties, summarize_item, other_properties


class ItemPropertyTests(unittest.TestCase):
    def setUp(self):
        self.row = InventoryRow(8, 2, 1, 1)
        self.items = {1: {'name': '合成装備', 'description': 'HP+25 MP+10 STR+5 DEX+6\n攻+20 命中+18\n雨天のとき命中+10'}}
        self.names = from_dictionary({1: 'Accuracy+%d'}, {1: '命中+%d'})
        item = AugmentItem(2, 1, 1, '', 'decoded', ('"Accuracy"+12',), 'B', 15)
        self.observation = AugmentObservation(AugmentExport('合成取得日時', 1, '', 1,
                                             (AugmentBag(8, 'ready', (item,)),)), frozenset({8}), ())

    def test_properties_and_totals_use_same_dictionary_and_individual(self):
        p = describe_item(self.row, self.items, self.observation, self.names, {8: 'ワードローブ1'})
        self.assertEqual(p.identity, 'ワードローブ1 / 位置 2 / Path B / Rank 15')
        self.assertEqual(p.augments, '命中+12')
        self.assertEqual(p.metadata, '取得日時: 合成取得日時')
        self.assertIn('HP+25  MP+10\nSTR+5  DEX+6\n攻+20\n命中+18', p.body)
        self.assertIn('雨天のとき命中+10', p.body)
        report = summarize_item(self.row, self.items, self.observation, self.names)
        self.assertIn(('命中', '', 30), report.totals)
        self.assertIn('雨天のとき命中+10', other_properties(report))

    def test_metadata_and_numeric_lines_leave_conditions_intact(self):
        text = 'Ｄ100 隔200 HP+25 MP+10\nLv99〜 装備可能ジョブ: 戦赤シ\n雨天のとき命中+10 攻+20\nＨＰ＋５０～１００'
        self.assertEqual(format_properties(text), 'D100\n隔200\nHP+25  MP+10\nLv99〜\n装備可能ジョブ: 戦赤シ\n雨天のとき命中+10 攻+20\nＨＰ＋５０～１００')

    def test_unmatched_and_unaccepted_individuals_do_not_borrow_augment(self):
        for row, observed in ((replace(self.row, container=10), self.observation),
                              (replace(self.row, index=3), self.observation),
                              (replace(self.row, item_id=2), self.observation),
                              (self.row, replace(self.observation, accepted_bags=frozenset()))):
            p = describe_item(row, self.items, observed, self.names)
            self.assertNotIn('Path B', p.identity)
            self.assertNotIn('命中+12', p.augments)
            self.assertIn('再取得が必要', p.augments)
        self.assertIn('本体の説明が未取得', describe_item(replace(self.row, item_id=2), {}).body)

    def test_empty_undecoded_and_path_only_are_distinct(self):
        self.assertEqual(describe_item(None, self.items), ItemProperties())
        self.assertIn('未取得', describe_item(self.row, self.items).augments)
        bag = self.observation.export.bags[0]
        for item, expected in ((replace(bag.items[0], augments=(), path=None), '付加能力なし'),
                               (replace(bag.items[0], augments=()), 'Path B の能力が未取得'),
                               (replace(bag.items[0], decode_state='unknown'), '解析できません')):
            observed = replace(self.observation, export=replace(self.observation.export, bags=(replace(bag, items=(item,)),)))
            p = describe_item(self.row, self.items, observed, self.names)
            self.assertIn(expected, p.augments)
        for action, text in (('keep', '未確定'), ('remove', '装備なし')):
            p = describe_item(Slot('head', action, None, None, None, ''), self.items, self.observation)
            self.assertIn(text, p.body)
            self.assertEqual((p.identity, p.augments), ('', ''))
