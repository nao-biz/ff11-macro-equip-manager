"""Production evaluation UI with dense, synthetic, raw-English augment inputs."""
from dataclasses import replace
import os
from threading import get_ident
import time
import tkinter as tk
from tkinter import font
import unittest
from unittest.mock import patch

from ff11reader.domain import InventoryRow, Slot
from ff11reader.edit_application import Editor
from ff11reader.ui_tasks import tasks
from prototypes.equipment_review_data import ReviewData, SLOT_KEYS
from tests.test_equipment_slots import SlotFixture
from tests.test_workspace_ui import WorkspaceMixin
from tests.test_practical_equipment_evaluation import offline


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class EquipmentReviewUITests(WorkspaceMixin, SlotFixture):
    def open_dense_view(self, weapon_text=False, unknown_armor=False, extra_weapon_text='', data=None):
        errors = patch('ff11reader.ui.dialogs.showerror', side_effect=AssertionError('Unexpected UI error'))
        errors.start(); self.addCleanup(errors.stop)
        data = ReviewData() if data is None else data
        if weapon_text:
            item = data.items['0:0']
            data.master[item.item_id]['description'] = ('D100 隔200 HP+80\n' + data.master[item.item_id]['description']
                                                      + '\nファントムロール数:被ダメージ-4%')
        if extra_weapon_text:
            item = data.items['0:0']
            data.master[item.item_id]['description'] = extra_weapon_text + '\n' + data.master[item.item_id]['description']
        if unknown_armor:
            data.master[data.items['4:0'].item_id]['description'] = None
        c = self.source.characters[0]
        self.source.augment_names = data.names
        c.inventory = [InventoryRow(12, i.position, i.item_id, 1) for i in data.items.values()]
        c.inventory_coverage[12] = 'loaded'
        slots = {}
        for part, key in enumerate(data.sets[0]):
            item = data.items[key]
            original = next(s for s in c.equipsets[0].slots if s.name == SLOT_KEYS[part])
            slots[SLOT_KEYS[part]] = Slot(SLOT_KEYS[part], 'equip', item.item_id, 12, item.position, original.raw_hex)
            self.source.items[item.item_id] = dict(data.master[item.item_id], equip_slots=(SLOT_KEYS[part],))
        c.equipsets[0] = replace(c.equipsets[0], slots=tuple(slots[s.name] for s in c.equipsets[0].slots))
        self.editor = Editor(self.source, self.base / 'dense.json')
        view = self.open_view()
        view.augment_observations['abc'] = data.observation
        view.change_mode(); self.app.update()
        return view

    def choose(self, row):
        self.view.slot_editor.listing.selection_set(str(row)); self.app.update()

    def values(self, name, unit=''):
        return tuple(c.cget('text') for c in self.view.equipment_summary.metric_labels[name, unit][1:])

    def test_live_raw_augment_comparison_apply_undo_and_unknown(self):
        view = self.open_dense_view()
        before = self.editor.edit_status()
        self.choose(2)
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        self.assertEqual(self.values('モクシャII'), ('4', '5', '+1'))
        self.assertEqual(self.values('被魔法ダメージII', '%'), ('-8%', '-11%', '-3%'))
        self.assertEqual(self.editor.edit_status(), before)
        view.slot_editor.preview_button.invoke(); self.preview_window().cancel_button.invoke(); self.app.update()
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        self.choose(3)
        self.assertEqual(self.values('魔命')[-1], '-5*')
        self.assertIn('* は既知分', view.equipment_summary.note.cget('text'))
        view.slot_editor.cancel(); self.app.update()
        self.assertEqual(self.values('魔命'), ('320', '—', '—'))
        self.choose(2)
        view.slot_editor.preview_button.invoke(); self.preview_window().accept_button.invoke(); self.app.update()
        self.assertEqual(self.values('魔命'), ('335', '—', '—'))
        view.undo_fix(); self.app.update()
        self.assertEqual(self.values('魔命'), ('320', '—', '—'))
        view.redo_edit(); self.app.update()
        self.assertEqual(self.values('魔命')[0], '335')
        view.open_slot_editor(next(s for s in view.selected.slots if s.name == 'head'))
        self.choose(2)
        state = view.slot_editor.input_state()
        view.tabs.select('インベントリ'); view.tabs.select('装備セット'); self.app.update()
        self.assertIs(view.active_card, view.card_widgets['head'])
        self.assertEqual(view.slot_editor.slot_name, 'head')
        self.assertEqual(view.slot_editor.input_state(), state)
        for path, raw in self.original.items(): self.assertEqual(path.read_bytes(), raw)

    def test_density_and_live_controls_at_both_sizes(self):
        view = self.open_dense_view(weapon_text=True)
        for size in ('1440x900', '1320x840'):
            self.app.geometry(size); self.app.update()
            for candidate in (2, 3):
                self.choose(candidate)
                for tab in ('インベントリ', 'マクロ'):
                    view.tabs.select(tab); view.tabs.select('装備セット'); self.app.update()
                right = self.app.winfo_rootx() + self.app.winfo_width()
                bottom = view.right_panel.winfo_rooty() + view.right_panel.winfo_height()
                self.assertEqual(len(view.equipment_summary.metric_labels), 43)
                for cells in view.equipment_summary.metric_labels.values():
                    for cell in cells:
                        self.assertLessEqual(cell.winfo_rootx() + cell.winfo_width(), right)
                        self.assertLessEqual(cell.winfo_rooty() + cell.winfo_height(), bottom)
                        self.assertLessEqual(font.Font(root=self.app, font=cell.cget('font')).measure(cell.cget('text')) + 2,
                                             cell.winfo_width())
                self.assertLessEqual(view.equipment_summary.note.winfo_rooty() + view.equipment_summary.note.winfo_height(), bottom)
                for widget in (view.slot_editor.preview_button, view.save_button):
                    self.assertTrue(widget.winfo_viewable())
                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), self.app.winfo_rooty() + self.app.winfo_height())
                last = view.card_widgets['feet']
                self.assertLessEqual(last.winfo_y() + last.winfo_height(), view.canvas.winfo_height())

    def test_weapon_metadata_difference_cancel_apply_and_undo(self):
        view = self.open_dense_view(weapon_text=True, unknown_armor=True)
        owner = get_ident()
        from ff11reader.equipment_stats import summarize
        def checked_summary(*args):
            self.assertEqual(get_ident(), owner)
            return summarize(*args)
        with patch('ff11reader.equipment_summary_ui.summarize', side_effect=checked_summary), \
             patch('ff11reader.adapters.LocalReader.read', side_effect=AssertionError('Candidate selection must not read files')):
            self.choose(2)
            self.assertEqual(self.values('魔命')[-1], '+15')
            self.assertEqual(self.values('HP')[0], '455')
            self.assertNotIn('* は', view.equipment_summary.note.cget('text'))
            view.slot_editor.cancel(); self.app.update()
            self.assertEqual(self.values('魔命')[-1], '—')
            self.assertNotIn('* は', view.equipment_summary.note.cget('text'))
        self.choose(2)
        previous = self.values('魔命')[0]
        candidate = self.values('魔命')[1]
        view.slot_editor.preview_button.invoke(); self.preview_window().accept_button.invoke(); self.app.update()
        self.assertEqual(self.values('魔命'), (candidate, '—', '—'))
        view.undo_fix(); self.app.update()
        self.assertEqual(self.values('魔命'), (previous, '—', '—'))
        for path, raw in self.original.items(): self.assertEqual(path.read_bytes(), raw)

    def test_unchanged_unknown_armor_allows_confirmed_weapon_difference(self):
        view = self.open_dense_view(unknown_armor=True)
        self.choose(2)
        self.assertEqual(self.values('魔命')[-1], '+15')
        self.assertIn('現在: 既知分のみ', view.equipment_summary.note.cget('text'))

    def test_unresolved_effect_is_scoped_to_its_row_and_details(self):
        view = self.open_dense_view(extra_weapon_text='ファストキャスト効果アップ\n受け流しスキル+10～20')
        self.choose(2)
        self.assertEqual(self.values('魔命')[-1], '+15')
        self.assertTrue(self.values('ファストキャスト', '%')[-1].endswith('*'))
        self.assertTrue(self.values('ファストキャスト', '%')[0].endswith('*'))
        details = view.equipment_summary.details_text()
        self.assertIn('解析未対応', details)
        self.assertIn('受け流しスキル+10～20', details)
        self.assertIn('集計対象外', details)
        self.assertNotIn('取得不足', details)

    def test_offline_evaluation_exposes_original_properties_in_real_details_window(self):
        data = ReviewData()
        source_text, candidate_text = 'ＺＺＺアップ', '候補固有の能力アップ'
        bag = data.observation.export.bags[0]
        observed = tuple(replace(item, augments=(*item.augments, candidate_text))
                         if item.index == data.items['0:2'].position else item for item in bag.items)
        data.observation = replace(data.observation, export=replace(data.observation.export,
                                   bags=(replace(bag, items=observed),)))
        with offline():
            view = self.open_dense_view(extra_weapon_text=source_text + '\n雨天のとき被ダメージ-5%', data=data)
            before = self.editor.edit_status()
            with patch('ff11reader.adapters.LocalReader.read', side_effect=AssertionError('Use loaded data')):
                self.choose(2)
                self.assertEqual(self.values('HP'), ('400', '400', '±0'))
                self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
                self.assertEqual(self.values('被ダメージ', '%'), ('-25%', '-25%', '±0'))
                summary = view.equipment_summary
                button = next(w for w in summary.frame.winfo_children()[0].winfo_children()
                              if w.cget('text') == '全項目・内訳')
                button.invoke(); self.app.update()
                window = next(w for w in summary.frame.winfo_children() if isinstance(w, tk.Toplevel))
                text = next(w for w in window.winfo_children() if isinstance(w, tk.Text))
                displayed = text.get('1.0', 'end')
                current, proposed = displayed.split('候補 —', 1)
                self.assertIn('main / 試作の短剣: ' + source_text, current)
                self.assertIn('雨天のとき被ダメージ-5%', current)
                self.assertNotIn(candidate_text, current)
                self.assertIn('main / 試作の短剣 / オグメ: ' + candidate_text, proposed)
                self.assertTrue(text.winfo_viewable())
                window.destroy(); self.app.update()
                view.slot_editor.cancel(); self.app.update()
                self.assertEqual(self.values('魔命'), ('320', '—', '—'))
                self.assertNotIn(candidate_text, summary.details_text())
                self.assertEqual(self.editor.edit_status(), before)

    def test_new_apply_path_uses_worker_and_recovers_after_failure(self):
        view = self.open_dense_view()
        owner = get_ident(); seen = []
        original = self.editor.prepare_equipment_slot_edit
        def prepare(*args):
            self.assertNotEqual(owner, get_ident()); seen.append('prepare')
            return original(*args)
        self.choose(2)
        with patch.object(self.editor, 'prepare_equipment_slot_edit', side_effect=prepare):
            view.slot_editor.preview_button.invoke()
        preview = self.preview_window(); ticks = []
        self.app.after(10, lambda: ticks.append(tasks(self.app).running))
        def fail(edit):
            self.assertNotEqual(owner, get_ident()); seen.append('apply')
            time.sleep(.08); raise OSError('synthetic draft failure')
        with patch.object(self.editor, 'apply', side_effect=fail), patch('ff11reader.ui.dialogs.showerror') as error:
            preview.accept_button.invoke(); self.app.update(); error.assert_called_once()
        self.assertEqual(seen, ['prepare', 'apply']); self.assertIn(True, ticks)
        self.assertFalse(tasks(self.app).running)
        self.assertEqual(self.values('魔命'), ('320', '335', '+15'))
        self.assertIs(self.app.grab_current(), preview)
        preview.accept_button.invoke(); self.app.update()
        self.assertEqual(self.values('魔命')[0], '335')
        self.assertIsNone(self.app.grab_current())
