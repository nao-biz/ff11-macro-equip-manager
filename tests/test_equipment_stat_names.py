"""Mixed-language, tier, unit and provenance contracts using decoded strings."""
from decimal import Decimal
import unittest
from ff11reader.domain import Equipset, Slot, Text
from ff11reader.equipment_stats import parse_line as parse_with_dictionary, summarize
from ff11reader.equipment_stat_names import from_dictionary
from prototypes.augment_dictionary_fixture import names
from ff11reader.augment_import import parse
from ff11reader.augment_observation import reconcile
from tests.test_augment_import import character, encoded, fixture


def parse_line(line):
    return parse_with_dictionary(line, names())


class StatNameTests(unittest.TestCase):
    def report(self, description, augments):
        data = fixture()
        data['bags'][12]['items'][0]['augments'] = augments
        observation = reconcile(parse(encoded(data)), character())
        equipment = Equipset(1, Text('合成装備', '', 'cp932'), (Slot('main', 'equip', 21581, 12, 1, ''),))
        return summarize(equipment, {21581: {'name': '合成装備', 'description': description}}, observation, names())

    def test_names_follow_resource_ids_and_dictionary_changes(self):
        english = {7: 'Novel stat%+d', 8: 'Attack%+d', 9: 'Haste%+d%%'}
        japanese = {9: 'ヘイスト%+d', 7: '新能力%+d', 8: '攻%+d'}
        table = from_dictionary(english, japanese)
        self.assertEqual(parse_with_dictionary('Novel stat+7 Haste+3', table), [('新能力', '', 7), ('ヘイスト', '%', 3)])
        japanese[7] = '更新能力%+d'
        self.assertEqual(parse_with_dictionary('Novel stat+7', from_dictionary(english, japanese)), [('更新能力', '', 7)])
        self.assertIsNone(parse_with_dictionary('Accuracy+10'))
        self.assertEqual(parse_with_dictionary('魔命+10 HP+20'), [('魔命', '', 10), ('HP', '', 20)])

    def test_missing_conflicting_or_complex_records_do_not_guess(self):
        table = from_dictionary({1: 'Ambiguous%+d', 2: 'Ambiguous%+d', 3: 'Missing%+d',
                                 4: 'Pair%+d Other%+d', 5: 'Pet: Attack%+d'},
                                {1: '攻%+d', 2: '命中%+d', 4: '攻%+d 命中%+d', 5: 'ペット:攻%+d'})
        for line in ('Ambiguous+5', 'Missing+5', 'Pair+5 Other+5', 'Pet: Attack+5'):
            self.assertIsNone(parse_with_dictionary(line, table))
        units = from_dictionary({1: 'Rate%+d', 2: 'Rate%+d%%'}, {1: '新数値%+d', 2: '新数値%+d%%'})
        self.assertIsNone(parse_with_dictionary('Rate+5', units))
        self.assertEqual(parse_with_dictionary('Rate+5%', units), [('新数値', '%', 5)])

    def test_quoted_english_augments_join_japanese_base_and_keep_raw(self):
        raw = ['"Mag. Acc."+10', '"Store TP"+5', '"Dbl.Atk."+3', 'Haste+2',
               '"Fast Cast"+4', '"Mag.Atk.Bns."+6', 'Magic burst dmg.+5%']
        report = self.report('魔命+20 ストアTP+7 ダブルアタック+2% ヘイスト+5%\n'
                             'ファストキャスト+8% 魔攻+9 マジックバーストダメージ+10', raw)
        self.assertEqual({(n, u): v for n, u, v in report.totals}, {
            ('魔命', ''): 30, ('ストアTP', ''): 12, ('ダブルアタック', '%'): 5,
            ('ヘイスト', '%'): 7, ('ファストキャスト', '%'): 12, ('魔攻', ''): 15,
            ('マジックバーストダメージ', '%'): 15})
        self.assertFalse(report.incomplete)
        self.assertEqual(report.excluded, ())
        self.assertEqual([line for _, line in report.included][-len(raw):], raw)

    def test_tiers_and_damage_types_survive_translation(self):
        report = self.report('モクシャ+10 モクシャII+4\n被ダメージ-5% 被物理ダメージ-10% '
                             '被物理ダメージII-3% 被魔法ダメージ-7% 被魔法ダメージII-9%\n'
                             'マジックバーストダメージ+20 マジックバーストダメージII+6 物理ダメージ上限+8%',
                             ['"Subtle Blow"+3', '"Subtle Blow II"+2', 'Phys. dmg. taken -2',
                              'Phys. dmg. taken II-4%', 'Magic dmg. taken -3%', 'Magic dmg. taken II-5%',
                              'Magic burst dmg.+1%', 'Magic burst dmg. II+2%', 'Physical damage limit+3%'])
        values = {(n, u): v for n, u, v in report.totals}
        self.assertEqual(values, {('モクシャ', ''): 13, ('モクシャII', ''): 6, ('被ダメージ', '%'): -5,
                         ('被物理ダメージ', '%'): -12, ('被物理ダメージII', '%'): -7,
                         ('被魔法ダメージ', '%'): -10, ('被魔法ダメージII', '%'): -14,
                         ('マジックバーストダメージ', '%'): 21, ('マジックバーストダメージII', '%'): 8,
                         ('物理ダメージ上限', '%'): 11})

    def test_typography_hyphen_skills_and_explicit_units(self):
        self.assertEqual(parse_line('“mag.acc.”＋１０ 「Store TP」+ 3'), [('魔命', '', 10), ('ストアTP', '', 3)])
        self.assertEqual(parse_line('モクシャⅡ+2'), [('モクシャII', '', 2)])
        self.assertEqual(parse_line('Hand-to-Hand skill+5 Dagger skill+10'), [('格闘スキル', '', 5), ('短剣スキル', '', 10)])
        self.assertEqual(parse_line('Mag. Acc+10 /Mag. Dmg.+10'), [('魔命', '', 10), ('魔法ダメージ', '', 10)])
        self.assertEqual(parse_line('HP+25 HP+5%'), [('HP', '', 25), ('HP', '%', 5)])
        self.assertEqual(parse_line('ウェポンスキルダメージ+1.1'), [('ウェポンスキルのダメージ', '%', Decimal('1.1'))])
        for text in ('Spell interruption rate down -8%', 'Spell interruption rate down +8%', '詠唱中断率8%ダウン'):
            self.assertEqual(parse_line(text), [('詠唱中断率', '%', -8)])

    def test_unknown_or_qualified_english_retains_original_outside_totals(self):
        raw = ['Pet: "Mag.Atk.Bns."+15', 'Latent effect: "Store TP"+10', 'Unknown bonus+4',
               'Vs. beasts: Accuracy+20', 'Magic burst dmg.+5% when active']
        report = self.report('魔命+20', raw)
        self.assertEqual(report.totals, (('魔命', '', 20),))
        self.assertEqual([line for _, line in report.excluded], raw)
        self.assertFalse(report.incomplete)
        self.assertEqual([line for _, line in report.unparsed], ['Unknown bonus+4'])
        self.assertFalse(report.uncertain)


if __name__ == '__main__':
    unittest.main()
