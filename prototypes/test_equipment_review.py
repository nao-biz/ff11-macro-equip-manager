"""Behavior and density checks on synthetic native UI; no game I/O."""
import gc
import tkinter as tk
from tkinter import font
import unittest

from tests.test_ui_tasks import TkThreadGuard
from .equipment_review import EquipmentReviewMock
from .equipment_review_data import SLOTS, totals


class EquipmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.tk = TkThreadGuard(self.root.tk)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.ui = EquipmentReviewMock(self.root)
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        gc.collect()
        self.assertFalse(self.errors)

    def choose(self, key):
        self.ui.candidates.selection_set(key)
        self.root.update()

    def values(self, key):
        return [cell.cget('text') for cell in self.ui.metric_labels[key][1:]]

    def test_preview_cancel_apply_and_undo(self):
        before = list(self.ui.selection)
        self.choose('0:2')
        self.assertEqual(self.ui.selection, before)
        self.assertEqual(self.values(('魔命', '')), ['320', '335', '+15'])
        self.assertEqual(self.values(('ストアTP', '')), ['96', '92', '-4'])
        self.assertTrue(self.ui.summary.winfo_ismapped())
        self.assertTrue(self.ui.gear_grid.winfo_ismapped())
        self.ui.cancel_button.invoke()
        self.root.update()
        self.assertEqual(self.ui.selection, before)
        self.assertEqual(self.values(('魔命', '')), ['320', '—', '—'])
        self.choose('0:2')
        self.ui.apply_button.invoke()
        self.root.update()
        self.assertEqual(self.ui.selection[0], '0:2')
        self.assertEqual(self.values(('魔命', '')), ['335', '—', '—'])
        self.ui.undo_button.invoke()
        self.root.update()
        self.assertEqual(self.ui.selection, before)
        self.assertEqual(self.values(('魔命', '')), ['320', '—', '—'])

    def test_unknown_keep_and_remove_are_distinct(self):
        self.choose('0:3')
        self.assertEqual(self.values(('魔命', ''))[-1], '未確定')
        self.assertIn('候補: 既知分のみ', self.ui.coverage.cget('text'))
        self.choose('keep')
        self.assertEqual(self.values(('HP', ''))[-1], '未確定')
        self.choose('remove')
        self.assertEqual(self.values(('HP', ''))[-1], '-25')
        self.ui.apply_button.invoke()
        self.root.update()
        self.assertEqual(self.ui.selection[0], 'remove')
        self.assertEqual(self.values(('HP', ''))[0], '375')

    def test_filter_and_navigation_clear_stale_preview(self):
        self.choose('0:2')
        self.ui.query.set('Path B')
        self.root.update()
        self.assertEqual(self.ui.candidates.get_children(), ('0:1',))
        self.assertIsNone(self.ui.trial_key)
        self.choose('0:1')
        self.ui.cards[8].invoke()
        self.root.update()
        self.assertIsNone(self.ui.trial_key)
        self.assertEqual(self.ui.slot_index, 8)
        self.assertIn('8:2', self.ui.candidates.get_children())
        self.choose('8:2')
        self.ui.set_list.selection_clear(0, 'end')
        self.ui.set_list.selection_set(1)
        self.ui.set_list.event_generate('<<ListboxSelect>>')
        self.root.update()
        self.assertIsNone(self.ui.trial_key)
        self.assertEqual(self.ui.selection[8], '8:1')
        self.assertEqual(self.ui.data.sets[0][8], '8:0')

    def test_current_unknown_is_not_a_confirmed_delta(self):
        self.ui.set_index = 3
        self.ui.select_slot(4)
        self.choose('4:0')
        self.assertIn('現在: 既知分のみ', self.ui.coverage.cget('text'))
        self.assertEqual(self.values(('魔命', ''))[-1], '未確定')
        self.ui.apply_button.invoke()
        self.root.update()
        self.assertNotIn('既知分のみ', self.ui.coverage.cget('text'))

    def test_dense_layout_and_game_order_at_reference_sizes(self):
        for size in ('1440x900', '1320x840'):
            self.root.geometry(size)
            self.root.update()
            self.assertEqual(len(self.ui.metric_labels), 43)
            for part, button in enumerate(self.ui.cards):
                self.assertEqual(button.cget('text').splitlines()[0], SLOTS[part])
                self.assertEqual(int(button.master.grid_info()['row']), part // 4)
                self.assertEqual(int(button.master.grid_info()['column']), part % 4)
            before = [(cells[0].winfo_rootx(), cells[0].winfo_rooty())
                      for cells in self.ui.metric_labels.values()]
            for key in ('0:2', '0:3'):
                self.choose(key)
                for cells in self.ui.metric_labels.values():
                    for cell in cells:
                        x, y = cell.winfo_rootx(), cell.winfo_rooty()
                        self.assertGreaterEqual(x, self.ui.summary.winfo_rootx())
                        self.assertLessEqual(x + cell.winfo_width(), self.root.winfo_rootx() + self.root.winfo_width())
                        self.assertLessEqual(y + cell.winfo_height(), self.ui.coverage.winfo_rooty())
                        measured = font.Font(root=self.root, font=cell.cget('font')).measure(cell.cget('text'))
                        self.assertLessEqual(measured + 2, cell.winfo_width())
                self.assertEqual(before, [(cells[0].winfo_rootx(), cells[0].winfo_rooty())
                                          for cells in self.ui.metric_labels.values()])
                self.assertTrue(self.ui.candidates.winfo_ismapped())
                self.assertLessEqual(self.ui.coverage.winfo_rooty() + self.ui.coverage.winfo_height(),
                                     self.ui.summary.winfo_rooty() + self.ui.summary.winfo_height())
                self.assertLess(self.ui.apply_button.winfo_rooty() + self.ui.apply_button.winfo_height(),
                                self.root.winfo_rooty() + self.root.winfo_height())

    def test_player_priorities_have_independent_totals_and_deltas(self):
        self.choose('0:2')
        expected = {
            ('モクシャ', ''): ['10', '13', '+3'],
            ('モクシャII', ''): ['4', '5', '+1'],
            ('被ダメージ', '%'): ['-25%', '-25%', '±0'],
            ('被物理ダメージ', '%'): ['-5%', '-6%', '-1%'],
            ('被物理ダメージII', '%'): ['-6%', '-8%', '-2%'],
            ('被魔法ダメージ', '%'): ['-10%', '-12%', '-2%'],
            ('被魔法ダメージII', '%'): ['-8%', '-11%', '-3%'],
            ('物理ダメージ上限', '%'): ['6%', '8%', '+2%'],
            ('マジックバーストダメージ', '%'): ['8%', '9%', '+1%'],
            ('マジックバーストダメージII', '%'): ['4%', '7%', '+3%'],
        }
        for key, values in expected.items():
            self.assertEqual(self.values(key), values, key)
        self.ui.apply_button.invoke()
        self.root.update()
        for key, values in expected.items():
            self.assertEqual(self.values(key), [values[1], '—', '—'], key)

    def test_details_preserve_extra_metrics_units_and_exclusions(self):
        report = self.ui.current_report
        values = totals(report)
        self.assertEqual(values['HP', ''], 400)
        self.assertEqual(values['HP', '%'], 3)
        self.assertEqual(values['連携ボーナス', '%'], 10)
        self.assertEqual(values['被ダメージ', '%'], -25)
        text = self.ui.report_text()
        self.assertIn('リジェネ  2', text)
        self.assertIn('ウェポンスキルのダメージ', text)
        self.assertIn('潜在能力: 攻+40', text)
        self.choose('0:2')
        self.ui.show_item_details()
        self.root.update()
        windows = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(windows), 1)
        view = next(w for w in windows[0].winfo_children()[0].winfo_children() if isinstance(w, tk.Text))
        self.assertIn('"Mag. Acc."+20', view.get('1.0', 'end'))
        self.assertEqual(self.values(('魔命', '')), ['320', '335', '+15'])
        windows[0].destroy()


if __name__ == '__main__':
    unittest.main()
