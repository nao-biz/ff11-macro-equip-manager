"""EX-EVAL10: useful numeric and textual evaluation without external enrichment."""
from contextlib import contextmanager, ExitStack
from dataclasses import replace
import unittest
from unittest.mock import patch

from ff11reader.augment_observation import AugmentItem, AugmentBag, AugmentExport, AugmentObservation
from ff11reader.domain import Equipset, Slot, Text
from ff11reader.equipment_stats import summarize
from ff11reader.equipment_stats_presentation import comparison, exclusion_groups


@contextmanager
def offline():
    with ExitStack() as stack:
        for target in ('socket.create_connection', 'socket.socket.connect', 'socket.socket.connect_ex'):
            stack.enter_context(patch(target, side_effect=AssertionError('External data must not be required')))
        yield


class PracticalEquipmentEvaluationTests(unittest.TestCase):
    def reports(self, current_description, candidate_description, common_description=None):
        slots = (Slot('main', 'equip', 101, 12, 1, ''),)
        if common_description is not None:
            slots += (Slot('head', 'equip', 103, 12, 3, ''),)
        current = Equipset(1, Text('合成評価', '', 'cp932'), slots)
        candidate = replace(current, slots=(Slot('main', 'equip', 102, 12, 2, ''), *slots[1:]))
        items = {101: {'name': '合成の剣A', 'description': current_description},
                 102: {'name': '合成の剣B', 'description': candidate_description},
                 103: {'name': '合成の兜', 'description': common_description}}
        bag = AugmentBag(12, 'ready', tuple(AugmentItem(i, ident, 1, '', 'decoded', (), None, None)
                                          for i, ident in ((1, 101), (2, 102), (3, 103))))
        observation = AugmentObservation(AugmentExport('', 1, 'Synthetic', 1, (bag,)), frozenset({12}), ())
        with offline(), patch('ff11reader.adapters.LocalReader.read', side_effect=AssertionError('Use loaded data')):
            return summarize(current, items, observation), summarize(candidate, items, observation)

    def test_numeric_totals_and_raw_properties_remain_usable_without_enrichment(self):
        original = 'Ｄ100 隔200 HP+50\nＺＺＺアップ\n雨天のとき被ダメージ-5%\n魔命+20'
        candidate = 'D110 隔210 HP+80\n未知能力アップ\n攻撃のとき命中+100\n魔命+35'
        current, trial = self.reports(original, candidate)
        self.assertEqual(current.totals, (('HP', '', 50), ('魔命', '', 20)))
        self.assertEqual(trial.totals, (('HP', '', 80), ('魔命', '', 35)))
        self.assertEqual(comparison(current, trial)['HP', ''], ('50', '80', '+30'))
        self.assertEqual(comparison(current, trial)['魔命', ''], ('20', '35', '+15'))
        self.assertIn(('main / 合成の剣A', 'ＺＺＺアップ'), current.excluded)
        self.assertIn(('main / 合成の剣A', '雨天のとき被ダメージ-5%'), current.excluded)
        self.assertIn(('main / 合成の剣B', '未知能力アップ'), trial.excluded)
        self.assertFalse(current.incomplete or trial.incomplete)

    def test_numeric_properties_and_opaque_properties_from_other_slots_coexist(self):
        current, trial = self.reports('XXXのときYYY\nZZZアップ', '追加効果の説明\n別の能力アップ', 'HP+50')
        self.assertEqual(comparison(current, trial)['HP', ''], ('50', '50', '±0'))
        self.assertEqual([line for _, line in current.excluded], ['XXXのときYYY', 'ZZZアップ'])
        self.assertFalse(current.incomplete)

    def test_missing_source_and_textual_effect_are_distinct(self):
        current, trial = self.reports('HP+50\nZZZアップ', None)
        self.assertEqual(dict(exclusion_groups(current))['取得不足'], ())
        self.assertTrue(dict(exclusion_groups(current))['解析未対応'])
        self.assertTrue(dict(exclusion_groups(trial))['取得不足'])
        self.assertEqual(comparison(current, trial)['HP', ''], ('50', '未確定', '未確定'))
