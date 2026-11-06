import unittest
from dataclasses import replace
from ff11reader.domain import Equipset, Slot, Text
from ff11reader.augment_observation import AugmentItem, AugmentBag, AugmentExport, AugmentObservation
from ff11reader.equipment_stats import EquipmentStats, summarize
from ff11reader.equipment_stats_presentation import GROUPS, comparison, comparison_note, display_totals


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

    def test_comparison_labels_known_partial_delta(self):
        current = EquipmentStats((('魔命', '', 20), ('被物理ダメージ', '%', -10)), (), ())
        trial = EquipmentStats((('魔命', '', 35), ('被物理ダメージ', '%', -12)), (), ())
        self.assertEqual(comparison(current, trial)['魔命', ''], ('20', '35', '+15'))
        self.assertEqual(comparison(current, trial)['被物理ダメージ', '%'], ('-10%', '-12%', '-2%'))
        self.assertEqual(comparison(current)['魔命', ''], ('20', '—', '—'))
        self.assertEqual(comparison(current, replace(trial, incomplete=True))['魔命', ''][-1], '+15*')
        self.assertEqual(comparison(replace(current, incomplete=True), trial)['魔命', ''][-1], '+15*')
        self.assertEqual(comparison_note(current, replace(trial, incomplete=True)), '* は既知分')

    def reports(self, before='魔命+20', after='魔命+35', observed=True, common_unknown=False):
        slots = (Slot('main', 'equip', 1, 12, 1, ''),)
        if common_unknown:
            slots += (Slot('head', 'equip', 3, 12, 3, ''), Slot('body', 'keep', None, None, None, ''))
        equipment = Equipset(1, Text('合成比較', '', 'cp932'), slots)
        candidate = replace(equipment, slots=(replace(slots[0], item_id=2, index=2), *slots[1:]))
        items = {1: {'description': before}, 2: {'description': after}}
        bag = AugmentBag(12, 'ready', tuple(AugmentItem(i, i, 1, '', 'decoded', (), None, None) for i in (1, 2)))
        observation = AugmentObservation(AugmentExport('', 1, '', 1, (bag,)), frozenset({12}), ()) if observed else None
        return summarize(equipment, items, observation), summarize(candidate, items, observation)

    def test_weapon_text_and_missing_augments_preserve_known_difference(self):
        for observed in (False, True):
            with self.subTest(observed=observed):
                current, trial = self.reports('D100 隔200\n魔命+20', 'D110 隔210\n魔命+35', observed)
                self.assertEqual(comparison(current, trial)['魔命', ''], ('20', '35', '+15' + ('' if observed else '*')))
                self.assertEqual(comparison(current, trial)['HP', ''][-1], '±0' + ('' if observed else '*'))
                self.assertIn(('main / 1', 'D100 隔200'), current.excluded)

    def test_unchanged_missing_equipment_and_keep_cancel_out(self):
        current, trial = self.reports(common_unknown=True)
        self.assertTrue(current.incomplete and trial.incomplete)
        self.assertEqual(comparison(current, trial)['魔命', ''], ('20', '35', '+15'))
        self.assertEqual(comparison_note(current, trial), '')
        self.assertEqual(comparison(current, current)['魔命', ''][-1], '±0')

    def test_unavailable_changed_part_is_not_zero_even_with_known_other_parts(self):
        for current, trial in (self.reports(after=None, observed=False),
                               self.reports(before=None, observed=False)):
            self.assertEqual(comparison(current, trial)['魔命', ''][-1], '未確定')
        current, trial = self.reports(after=None, observed=False)
        self.assertEqual(comparison(current, trial)['魔命', ''][1], '未確定')
        # Known unrelated equipment must not mask the unavailable changed weapon.
        shared = ((('head', 'equip', 9, 12, 9), EquipmentStats((('HP', '', 10),), (), ())),)
        current = replace(current, parts=current.parts + shared, available=True)
        trial = replace(trial, parts=trial.parts + shared, available=True)
        self.assertEqual(comparison(current, trial)['魔命', ''][-1], '未確定')

    def test_same_name_and_item_at_other_position_do_not_cancel_unknown_augments(self):
        current, trial = self.reports(observed=False)
        ref, report = current.parts[0]
        moved = replace(current, parts=(((*ref[:-1], 2), report),))
        self.assertEqual(comparison(current, moved)['魔命', ''][-1], '±0*')

    def test_partial_negative_percentage_decimal_and_no_candidate(self):
        current, trial = self.reports('被物理ダメージ-10% 魔命+1.1', '被物理ダメージ-12% 魔命+2.2', False)
        self.assertEqual(comparison(current, trial)['被物理ダメージ', '%'], ('-10%', '-12%', '-2%*'))
        self.assertEqual(comparison(current, trial)['魔命', ''][-1], '+1.1*')
        self.assertEqual(comparison(current)['魔命', ''], ('1.1', '—', '—'))
        self.assertEqual(comparison_note(current, None), '')

    def test_conditional_and_non_summary_effects_do_not_mark_other_rows(self):
        current, trial = self.reports('D100 隔200 HP+80\n魔命+20\n受け流しスキル+10～20\nファントムロール数:被ダメージ-4%',
                                     'D110 隔210 HP+90\n魔命+35\nファントムロール数:被ダメージ-6%')
        rows = comparison(current, trial)
        self.assertEqual(rows['HP', ''], ('80', '90', '+10'))
        self.assertEqual(rows['魔命', ''], ('20', '35', '+15'))
        self.assertEqual(rows['被ダメージ', '%'], ('0%', '0%', '±0'))
        self.assertTrue(current.unparsed)
        self.assertFalse(current.incomplete)
        self.assertFalse(any('*' in cell or cell == '未確定' for row in rows.values() for cell in row))
        self.assertEqual(comparison_note(current, trial), '')

    def test_unresolved_named_effect_marks_only_the_affected_row(self):
        current, trial = self.reports('魔命+20\nファストキャスト効果アップ HP+50', '魔命+35\nファストキャスト+4% HP+60')
        rows = comparison(current, trial)
        self.assertEqual(rows['魔命', ''], ('20', '35', '+15'))
        self.assertEqual(rows['HP', ''], ('50', '60', '+10'))
        self.assertEqual(rows['ファストキャスト', '%'], ('0%*', '4%', '+4%*'))
        self.assertEqual(comparison_note(current, None), '* は既知分')
