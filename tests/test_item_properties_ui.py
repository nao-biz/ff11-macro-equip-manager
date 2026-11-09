"""VIEW-007 and D-18: production selection, comparison and context changes."""
from dataclasses import replace
import os
from threading import get_ident
import time
import unittest
from unittest.mock import patch

from ff11reader import theme
from ff11reader.ui_tasks import tasks
from prototypes.item_properties import PropertyData
from tests import test_equipment_review_ui as review
from tests.test_equipment_slots import SlotFixture
from tests.test_practical_equipment_evaluation import offline
from tests.test_workspace_ui import WorkspaceMixin


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class ItemPropertyUITests(WorkspaceMixin, SlotFixture):
    open_dense_view = review.EquipmentReviewUITests.open_dense_view
    choose = review.EquipmentReviewUITests.choose
    values = review.EquipmentReviewUITests.values

    def setUp(self):
        super().setUp()
        network = offline(); network.__enter__()
        self.addCleanup(network.__exit__, None, None, None)
        self.reader_guard = patch('ff11reader.adapters.LocalReader.read', side_effect=AssertionError('Use loaded data'))
        self.reader_guard.start(); self.addCleanup(self.reader_guard.stop)

    def open_properties(self, **kwargs):
        return self.open_dense_view(data=PropertyData(), **kwargs)

    def extra(self):
        return self.view.equipment_summary.extra_properties.get('1.0', 'end-1c')

    def assert_inside(self, widget, parent=None):
        parent = parent or self.app
        self.assertTrue(widget.winfo_viewable())
        self.assertGreaterEqual(widget.winfo_rootx(), parent.winfo_rootx())
        self.assertGreaterEqual(widget.winfo_rooty(), parent.winfo_rooty())
        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), parent.winfo_rootx() + parent.winfo_width())
        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), parent.winfo_rooty() + parent.winfo_height())

    def test_selected_item_and_candidate_values_colors_zero_and_clear(self):
        view = self.open_properties(); summary = view.equipment_summary
        before = self.editor.edit_status()
        self.assertEqual(self.values('魔命'), ('320', '20', ''))
        self.assertTrue(all(h.cget('text') == '選択装備' for h in summary.value_headers))
        self.choose(2)
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        self.assertTrue(all(h.cget('text') == '候補計' for h in summary.value_headers))
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(summary.metric_labels['魔命', ''][2].cget('fg'), theme.REVIEW)
        self.assertEqual(summary.metric_labels['魔命', ''][3].cget('fg'), theme.ACCENT)
        self.assertEqual(summary.metric_labels['被魔法ダメージII', '%'][3].cget('fg'), theme.DANGER)
        self.assertIn('雨天のとき被ダメージ-5%', self.extra())
        self.assertIn('本体の全プロパティ', self.extra())
        self.assertIn('魔命+20', self.extra())
        self.choose(3)
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(self.values('魔命')[-1], '-5*')
        self.assertIn('既知分', summary.note.cget('text'))
        view.inspect_slot(view.selected.slots[0]); self.app.update()
        self.assertEqual(self.values('魔命'), ('320', '20', ''))
        self.assertEqual(view.slot_editor.chosen(), (None, None))
        for action, expected in (('keep', '未確定'), ('remove', '装備なし')):
            view.slot_editor.listing.selection_set(action); self.app.update()
            self.assertIn(expected, self.extra())
            self.assertNotIn('Path C', summary.comparison_label.cget('text'))
        view.slot_editor.cancel(); self.app.update()
        self.assertIn('Path A', summary.comparison_label.cget('text'))
        self.assertEqual(self.editor.edit_status(), before)

    def test_inventory_formats_follows_filters_layouts_and_transfers_exact_individual(self):
        view = self.open_properties(); before = self.editor.edit_status()
        view.open_inventory(13, 3); self.app.update()
        p = view.inventory_properties
        expected = p.contents()
        self.assertIn('HP+25  MP+10', expected[0])
        self.assertIn('攻+20\n命中+18', expected[0])
        self.assertIn('魔命+20', expected[1])
        self.assertIn('Path C', p.identity.cget('text'))
        for layout in ('パネル', 'リスト'):
            view.inventory_layout.set(layout); view.switch_inventory_layout(); self.app.update()
            self.assertEqual(view.active_inventory, 3)
            self.assertEqual(p.contents(), expected)
        view.inventory_compare_button.invoke(); self.app.update()
        self.assertEqual(view.mode.get(), '装備セット')
        self.assertEqual(view.slot_editor.chosen(), ('equip', (1000, 13, 3)))
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        for body in expected:
            self.assertIn(body, self.extra())
        self.assertEqual(self.editor.edit_status(), before)
        view.tabs.select('インベントリ'); self.app.update()
        self.assertEqual(p.contents(), expected)
        view.inventory_query.set('存在しない'); self.app.update()
        self.assertEqual(p.contents(), ('', ''))
        self.assertTrue(view.inventory_compare_button.instate(['disabled']))
        view.open_inventory(12, 4); self.app.update()
        self.assertIn('解析できません', p.contents()[1])
        self.assertNotIn('Path C', p.identity.cget('text'))

    def test_character_storage_and_missing_body_never_keep_previous_properties(self):
        view = self.open_properties(characters=2)
        view.open_inventory(13, 3); self.app.update()
        self.assertIn('Path C', view.inventory_properties.identity.cget('text'))
        view.character_choice.current(1); view.change_character(); self.app.update()
        self.assertEqual(view.inventory_properties.contents(), ('', ''))
        view.open_inventory(13, 3); self.app.update()
        self.assertNotIn('Path C', view.inventory_properties.identity.cget('text'))
        self.assertIn('未取得', view.inventory_properties.contents()[1])
        view.character_choice.current(0); view.change_character(); self.app.update()
        self.assertIn('Path C', view.inventory_properties.identity.cget('text'))
        view.open_inventory(12, 64); self.app.update()
        self.assertIn('本体の説明が未取得', view.inventory_properties.contents()[0])
        for state, label in (('loaded', '読込済み'), ('missing', '未取得'), ('unreadable', '読込不能')):
            view.character.inventory_coverage[0] = state
            view.open_inventory(0, 1); self.app.update()
            self.assertEqual(view.inventory_properties.contents(), ('', ''))
            self.assertIsNone(view.active_inventory)
            self.assertIn(label, view.subtitle.cget('text'))

    def test_inventory_transfer_keeps_compatible_slot_or_selects_first_and_disables_non_equipment(self):
        view = self.open_view()
        view.nav.selection_clear(0, 'end'); view.nav.selection_set(20); view.nav.activate(20)
        view.select_navigation()
        view.inspect_slot(next(s for s in view.selected.slots if s.name == 'ear2'))
        view.open_inventory(8, 8); self.app.update()
        before = self.editor.edit_status()
        view.inventory_compare_button.invoke(); self.app.update()
        self.assertEqual(view.selected.number, 21)
        self.assertEqual(view.active_slot, 'ear2')
        self.assertEqual(view.slot_editor.chosen(), ('equip', (0x2802, 8, 8)))
        view.inspect_slot(next(s for s in view.selected.slots if s.name == 'main'))
        view.open_inventory(8, 8); view.inventory_compare_button.invoke(); self.app.update()
        self.assertEqual(view.active_slot, 'ear1')
        self.assertEqual(self.editor.edit_status(), before)
        row = next(r for r in view.character.inventory if not view.snapshot.items.get(r.item_id, {}).get('equip_slots'))
        view.open_inventory(row.container, row.index); self.app.update()
        self.assertTrue(view.inventory_compare_button.instate(['disabled']))

    def test_missing_current_comparison_keeps_known_changes_and_clears_zero(self):
        view = self.open_properties()
        self.choose(3)
        view.slot_editor.preview_button.invoke(); self.app.update(); self.assertIsNone(self.app.grab_current())
        self.choose(0)
        self.assertEqual(self.values('HP')[-1], '')
        self.assertEqual(self.values('魔命')[-1], '+5*')
        self.assertIn('現在: 既知分のみ', view.equipment_summary.note.cget('text'))

    def test_both_layouts_fit_and_scroll_at_reference_and_minimum_sizes(self):
        view = self.open_properties()
        for size in ('1440x900', '1320x840'):
            self.app.geometry(size); view.tabs.select('装備セット'); self.choose(2); self.app.update()
            summary = view.equipment_summary
            for widget in (summary.extra_properties, summary.note, view.slot_editor.preview_button, view.slot_editor.listing):
                self.assert_inside(widget)
            self.assertGreaterEqual(summary.extra_properties.winfo_height(), 65)
            summary.extra_properties.yview_moveto(1); self.app.update()
            self.assertGreater(summary.extra_properties.yview()[0], 0)
            self.choose(1)
            self.assertEqual(summary.extra_properties.yview()[0], 0)
            view.open_inventory(13, 3)
            for layout in ('リスト', 'パネル'):
                view.inventory_layout.set(layout); view.switch_inventory_layout(); self.app.update()
                for widget in (*view.inventory_properties.texts, view.inventory_compare_button, view.inventory_details_button):
                    self.assert_inside(widget)

    def test_inventory_comparison_worker_blocks_inputs_and_recovers_after_failure(self):
        view = self.open_properties(); view.open_inventory(13, 3); self.app.update()
        owner = get_ident(); ticks = []; calls = []
        original = self.editor.equipment_candidates
        def tick():
            ticks.append(tasks(self.app).running)
            if tasks(self.app).running:
                view.inventory_compare_button.invoke()
                view.character_choice.event_generate('<<ComboboxSelected>>')
            if len(ticks) < 10:
                self.app.after(500, tick)
        def fail(*args):
            self.assertNotEqual(get_ident(), owner); calls.append(args)
            time.sleep(6.1)
            raise OSError('synthetic candidate failure')
        with patch.object(self.editor, 'equipment_candidates', side_effect=fail), patch('ff11reader.ui.dialogs.showerror') as error:
            self.app.after(100, tick)
            view.inventory_compare_button.invoke(); self.app.update()
            self.assertTrue(error.called)
        self.assertGreaterEqual(sum(ticks), 6); self.assertFalse(tasks(self.app).running)
        self.assertIsNone(self.app.grab_current())
        self.assertEqual(len(calls), 1)
        view.tabs.select('インベントリ'); self.app.update()
        self.assertIn('Path C', view.inventory_properties.identity.cget('text'))
        with patch.object(self.editor, 'equipment_candidates', wraps=original):
            view.inventory_compare_button.invoke(); self.app.update()
        self.assertEqual(self.values('魔命')[-1], '+15')
        for path, raw in self.original.items():
            self.assertEqual(path.read_bytes(), raw)
