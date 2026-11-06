"""VIEW-007 / EX-PROP01-06 on native synthetic UI, with no game or network I/O."""
from dataclasses import replace
import gc
import tkinter as tk
from tkinter import font
import unittest
from unittest.mock import patch

from tests.test_practical_equipment_evaluation import offline
from tests.test_ui_tasks import TkThreadGuard
from ff11reader import theme
from .item_properties import ItemPropertiesMock
from .item_property_panel import format_properties, property_content


class PropertyFormattingTests(unittest.TestCase):
    def test_basic_stats_grouped_and_other_properties_one_per_line(self):
        text = 'HP+25 MP+10 STR+5 DEX+6\n攻+20 命中+18 魔命+15 被ダメージ-5%'
        self.assertEqual(format_properties(text, {}),
                         'HP+25  MP+10\nSTR+5  DEX+6\n攻+20\n命中+18\n魔命+15\n被ダメージ-5%')

    def test_conditional_and_unparsed_text_keeps_its_meaning(self):
        text = '雨天のとき命中+10 攻+20\nペット: 魔命+30\n特殊な能力アップ\nＨＰ＋５０～１００'
        self.assertEqual(format_properties(text, {}), text)

    def test_weapon_metadata_and_level_have_their_own_lines(self):
        self.assertEqual(format_properties('Ｄ100 隔200 HP+25 MP+10\nLv99〜 装備可能ジョブ: 戦赤シ', {}),
                         'D100\n隔200\nHP+25  MP+10\nLv99〜\n装備可能ジョブ: 戦赤シ')


class ItemPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.connection_guard = offline()
        self.connection_guard.__enter__()
        self.addCleanup(self.connection_guard.__exit__, None, None, None)
        read_guard = patch('ff11reader.adapters.LocalReader.read', side_effect=AssertionError('Mock must use synthetic data'))
        read_guard.start(); self.addCleanup(read_guard.stop)
        self.root = tk.Tk(); self.root.tk = TkThreadGuard(self.root.tk)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.ui = ItemPropertiesMock(self.root)
        self.root.update()

    def tearDown(self):
        self.root.destroy(); gc.collect()
        self.assertFalse(self.errors)

    def choose(self, key):
        self.ui.equipment.candidates.selection_set(key)
        self.root.update()

    def extra_text(self):
        return self.ui.equipment.extra_properties.get('1.0', 'end-1c')

    def values(self, name):
        return tuple(w.cget('text') for w in self.ui.equipment.metric_labels[name, ''][1:])

    def test_selection_properties_and_comparison_apply_cancel_undo(self):
        e = self.ui.equipment
        self.assertEqual(e.inspected_key, '0:0')
        self.assertEqual(self.values('魔命'), ('320', '20', ''))
        self.assertTrue(all(w.cget('text') == '選択装備' for col, w in e.value_headers if col == 2))
        before = list(e.selection)
        self.choose('0:2')
        self.assertIn('魔命+20', self.extra_text())
        self.assertIn('Path C', e.comparison_title.cget('text'))
        self.assertIn('雨天のとき被ダメージ-5%', self.extra_text())
        self.assertIn('特殊な能力アップ', self.extra_text())
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        self.assertTrue(all(w.cget('text') == '候補計' for col, w in e.value_headers if col == 2))
        self.assertEqual(e.selection, before)
        self.assertFalse(e.history)
        e.cancel_button.invoke(); self.root.update()
        self.assertEqual(e.inspected_key, '0:0')
        self.assertEqual(self.values('魔命'), ('320', '20', ''))
        self.choose('0:1'); e.apply_button.invoke(); self.root.update()
        self.assertEqual(e.inspected_key, '0:1')
        self.assertEqual(self.values('魔命'), ('315', '15', ''))
        e.undo_button.invoke(); self.root.update()
        self.assertEqual(e.selection, before)
        self.assertEqual(e.inspected_key, '0:0')
        self.assertEqual(self.values('魔命'), ('320', '20', ''))

    def test_inventory_modes_share_individual_properties_and_compare_without_applying(self):
        self.choose('0:2')
        expected = property_content(self.ui.data, '0:2')[2:]
        for text in expected:
            self.assertIn(text, self.extra_text())
        self.ui.tab_buttons['インベントリ'].invoke(); self.root.update()
        inventory = self.ui.inventory
        inventory.listing.selection_set('0:2'); self.root.update()
        self.assertEqual(inventory.properties.contents(), expected)
        self.assertIn('ワードローブ2', inventory.properties.identity.cget('text'))
        for mode in ('パネル', 'リスト'):
            inventory.layout.set(mode); inventory.render(); self.root.update()
            self.assertEqual(inventory.properties.key, '0:2')
            self.assertEqual(inventory.properties.contents(), expected)
        inventory.layout.set('パネル'); inventory.render(); self.root.update()
        inventory.panel_buttons['0:1'].invoke(); self.root.update()
        self.assertIn('Path B', inventory.properties.identity.cget('text'))
        self.assertIn('STR+10', inventory.properties.contents()[1])
        before = list(self.ui.equipment.selection)
        inventory.compare_button.invoke(); self.root.update()
        self.assertEqual(self.ui.mode, '装備セット')
        self.assertEqual(self.ui.equipment.inspected_key, '0:1')
        self.assertEqual(self.ui.equipment.selection, before)
        self.assertFalse(self.ui.equipment.history)

    def test_missing_and_mismatched_observations_keep_known_body(self):
        self.choose('0:3')
        e = self.ui.equipment
        self.assertIn('オーグメント未取得', self.extra_text())
        self.assertIn('Ｄ100', self.extra_text())
        self.assertNotIn('Path', e.comparison_title.cget('text'))
        self.ui.data.observation = replace(self.ui.data.observation, accepted_bags=frozenset({12}))
        self.choose('0:2')
        self.assertIn('オーグメント未取得', self.extra_text())
        self.assertNotIn('魔命+20', self.extra_text())
        self.ui.equipment.cards[15].invoke(); self.root.update()
        self.choose('15:3')
        self.assertIn('本体の説明が未取得', self.extra_text())

    def test_partial_comparison_hides_zero_but_keeps_nonzero_and_missing_information(self):
        e = self.ui.equipment
        self.choose('0:3')
        self.assertTrue(e.trial_report.incomplete)
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(self.values('魔命')[-1], '-5*')
        self.assertIn('既知分', e.coverage.cget('text'))
        self.assertIn('オーグメント未取得', self.extra_text())
        e.apply_button.invoke(); self.root.update()
        self.choose('0:0')
        self.assertTrue(e.current_report.incomplete)
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(self.values('魔命')[-1], '+5*')
        self.assertIn('既知分', e.coverage.cget('text'))

    def test_filter_storage_and_non_item_selection_clear_old_properties(self):
        self.choose('remove')
        self.assertIn('装備を外す', self.ui.equipment.comparison_title.cget('text'))
        self.assertNotIn('魔命+20', self.extra_text())
        self.choose('keep')
        self.assertIn('未確定', self.extra_text())
        self.ui.select_tab('インベントリ'); self.root.update()
        inventory = self.ui.inventory
        inventory.choose('0:2'); self.root.update()
        inventory.bags.selection_clear(0, 'end'); inventory.bags.selection_set(1)
        inventory.bags.event_generate('<<ListboxSelect>>'); self.root.update()
        self.assertIsNone(inventory.properties.key)
        self.assertEqual(inventory.properties.contents(), ('', ''))
        inventory.choose('0:0'); inventory.query.set('存在しない装備'); self.root.update()
        self.assertFalse(inventory.visible_keys)
        self.assertEqual(inventory.properties.contents(), ('', ''))
        self.assertTrue(inventory.compare_button.instate(['disabled']))

    def test_dense_layout_and_scrolling_at_both_sizes(self):
        e = self.ui.equipment
        for size in ('1440x900', '1320x840'):
            self.root.geometry(size); self.ui.select_tab('装備セット'); self.root.update()
            self.choose('0:2')
            for widget in (*e.cards, e.candidates, e.apply_button, e.cancel_button,
                           e.extra_properties, e.coverage):
                self.assert_visible_inside_root(widget)
            self.assertGreaterEqual(e.candidates.winfo_height(), 160)
            self.assertGreaterEqual(e.extra_properties.winfo_height(), 70)
            e.extra_properties.yview_moveto(1); self.root.update()
            self.assertGreater(e.extra_properties.yview()[0], 0)
            self.choose('0:1')
            self.assertEqual(e.extra_properties.yview()[0], 0)
            for _, heading in e.value_headers:
                self.assertLessEqual(font.Font(root=self.root, font=heading.cget('font')).measure(heading.cget('text')) + 2,
                                     heading.winfo_width())
            for cells in e.metric_labels.values():
                for cell in cells:
                    self.assert_visible_inside_root(cell)
                    self.assertLessEqual(font.Font(root=self.root, font=cell.cget('font')).measure(cell.cget('text')) + 2,
                                         cell.winfo_width())
            self.ui.select_tab('インベントリ'); self.root.update()
            inventory = self.ui.inventory
            for layout in ('リスト', 'パネル'):
                inventory.layout.set(layout); inventory.render(); self.root.update()
                for widget in (inventory.properties, *inventory.properties.texts, inventory.compare_button):
                    self.assert_visible_inside_root(widget)

    def test_extra_metrics_raw_effects_and_direction_colors(self):
        e = self.ui.equipment
        self.choose('0:2')
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(e.metric_labels['魔命', ''][-1].cget('fg'), theme.ACCENT)
        self.assertEqual(e.metric_labels['ストアTP', ''][-1].cget('fg'), theme.DANGER)
        self.assertEqual(e.metric_labels['被魔法ダメージII', '%'][-1].cget('fg'), theme.DANGER)
        self.assertEqual(e.metric_labels['魔命', ''][2].cget('fg'), theme.REVIEW)
        e.cards[12].invoke(); self.root.update()
        extra = self.extra_text().split('本体の全プロパティ')[0]
        self.assertIn('HP+3%', extra)
        self.assertIn('リジェネ+2', extra)
        self.assertIn('潜在能力: 攻+40', extra)
        self.assertEqual(self.values('魔命')[-1], '')
        self.assertEqual(e.metric_labels['魔命', ''][2].cget('fg'), theme.REVIEW)

    def assert_visible_inside_root(self, widget):
        self.assertTrue(widget.winfo_viewable())
        self.assertGreaterEqual(widget.winfo_rootx(), self.root.winfo_rootx())
        self.assertGreaterEqual(widget.winfo_rooty(), self.root.winfo_rooty())
        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), self.root.winfo_rootx() + self.root.winfo_width())
        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())


if __name__ == '__main__':
    unittest.main()
