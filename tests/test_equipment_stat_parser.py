"""Synthetic equipment formats; no game assets embedded in fixtures."""
import unittest
from decimal import Decimal

from ff11reader.equipment_stat_parser import analyze_line, parse_line
from prototypes.augment_dictionary_fixture import names


class EquipmentStatParserTests(unittest.TestCase):
    def test_weapon_metadata_and_bonuses_on_the_same_line(self):
        for text in ('Ｄ100 隔200 HP+80', 'D+100隔+200 HP+80', 'Ｄ１００　隔２００　ＨＰ＋８０'):
            result = analyze_line(text)
            self.assertEqual(result.values, (('HP', '', 80),))
            self.assertTrue(result.outside)
            self.assertFalse(result.unparsed)
            self.assertFalse(result.uncertain)
        self.assertEqual(parse_line('D100 隔200'), [])
        self.assertEqual(parse_line('防75 HP+20 HP+5 % 魔命-1.2'),
                         [('防', '', 75), ('HP', '', 20), ('HP', '%', 5), ('魔命', '', Decimal('-1.2'))])

    def test_separate_unknown_effect_does_not_discard_known_neighbors(self):
        result = analyze_line('HP+50 Unknown bonus+7 魔命+20', names())
        self.assertEqual(result.values, (('HP', '', 50), ('魔命', '', 20)))
        self.assertTrue(result.unparsed)
        self.assertFalse(result.uncertain)

    def test_missing_numeric_effect_only_affects_its_own_stat(self):
        result = analyze_line('ファストキャスト効果アップ HP+50', names())
        self.assertEqual(result.values, (('HP', '', 50),))
        self.assertEqual(result.uncertain, frozenset({('ファストキャスト', '%')}))
        self.assertTrue(result.unparsed)

    def test_range_and_unsupported_suffix_do_not_become_fixed_bonuses(self):
        result = analyze_line('HP+50 魔命+20～30 STR+5')
        self.assertEqual(result.values, (('HP', '', 50), ('STR', '', 5)))
        self.assertEqual(result.uncertain, frozenset({('魔命', '')}))
        for text in ('HP+50～100', 'HP+50 MPをHPに変換', 'HP+50%以下'):
            self.assertIsNone(parse_line(text))

    def test_conditional_prefix_and_postfix_are_outside_unconditional_totals(self):
        for text in ('ファントムロール数:被ダメージ-4%', 'ペット:魔命+20',
                     'Magic burst dmg.+5% when active', 'HP+50 時々発動'):
            result = analyze_line(text, names())
            self.assertEqual(result.values, ())
            self.assertTrue(result.outside)
            self.assertFalse(result.unparsed)
            self.assertFalse(result.uncertain)
        result = analyze_line('HP+50 潜在能力:MP+100')
        self.assertEqual(result.values, (('HP', '', 50),))
        self.assertTrue(result.conditional)
        result = analyze_line('HP+50～100 潜在能力:MP+100')
        self.assertEqual(result.values, ())
        self.assertEqual(result.uncertain, frozenset({('HP', '')}))
        result = analyze_line('HP+50 ファントムロール数:被ダメージ-4%')
        self.assertEqual(result.values, (('HP', '', 50),))

    def test_unresolved_extra_stat_retains_its_own_identity(self):
        result = analyze_line('短剣スキル+20～30')
        self.assertEqual(result.uncertain, frozenset({('短剣スキル', '')}))
        result = analyze_line('受け流しスキル+20～30')
        self.assertEqual(result.uncertain, frozenset({('受け流しスキル', '')}))
