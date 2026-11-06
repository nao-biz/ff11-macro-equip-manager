import unittest
from dataclasses import replace
from ff11reader.equipment_stats import EquipmentStats
from ff11reader.equipment_stats_presentation import GROUPS, comparison, display_totals


class EquipmentStatsPresentationTests(unittest.TestCase):
    def test_stable_groups_preserve_additional_properties_and_units(self):
        names = [n for _, _, metrics in GROUPS for n, _, _ in metrics]
        rows = [(name, '', index) for index, name in enumerate(names)]
        rows += [('非常に長い名前の追加能力', '', 7), ('HP', '%', 5)]
        ordered = display_totals(rows[::-1])
        self.assertCountEqual(ordered, rows)
        self.assertEqual(ordered[:2], [('HP', '', 0), ('HP', '%', 5)])
        changed = [(n, u, -v) for n, u, v in rows]
        self.assertEqual([(n, u) for n, u, _ in display_totals(changed)], [(n, u) for n, u, _ in ordered])

    def test_comparison_reports_unknown_without_inventing_zero_delta(self):
        current = EquipmentStats((('魔命', '', 20), ('被物理ダメージ', '%', -10)), (), ())
        trial = EquipmentStats((('魔命', '', 35), ('被物理ダメージ', '%', -12)), (), ())
        self.assertEqual(comparison(current, trial)['魔命', ''], ('20', '35', '+15'))
        self.assertEqual(comparison(current, trial)['被物理ダメージ', '%'], ('-10%', '-12%', '-2%'))
        self.assertEqual(comparison(current)['魔命', ''], ('20', '—', '—'))
        self.assertEqual(comparison(current, replace(trial, incomplete=True))['魔命', ''][-1], '未確定')
        self.assertEqual(comparison(replace(current, incomplete=True), trial)['魔命', ''][-1], '未確定')
