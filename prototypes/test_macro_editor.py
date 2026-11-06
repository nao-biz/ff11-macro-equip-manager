"""Synthetic GUI checks for the isolated prototype."""
import threading
import tkinter as tk
import unittest
from unittest.mock import patch

from .macro_editor import MacroEditorMock


class MacroMockTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.ui = MacroEditorMock(self.root)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_edit_survives_macro_and_palette_navigation(self):
        self.ui.lines[2].set('/echo 合成テスト')
        self.ui.buttons['Alt', 9].invoke()
        self.ui.name.set('別マクロ')
        self.ui.tree.selection_set('2:2')
        self.root.update()
        self.assertEqual(self.ui.key[:2], (2, 2))
        self.assertEqual(self.ui.lines[2].get(), '')
        self.ui.tree.selection_set('1:1')
        self.root.update()
        self.assertEqual(self.ui.lines[2].get(), '/echo 合成テスト')
        self.ui.buttons['Alt', 9].invoke()
        self.assertEqual(self.ui.name.get(), '別マクロ')

    def test_arrow_moves_caret_without_moving_content(self):
        self.root.focus_force()
        self.ui.entries[0].focus_set()
        self.ui.entries[0].icursor(3)
        before = [v.get() for v in self.ui.lines]
        self.ui.entries[0].event_generate('<Down>')
        self.root.update()
        self.assertEqual(self.root.focus_get(), self.ui.entries[1])
        self.assertEqual(self.ui.entries[1].index('insert'), 3)
        self.assertEqual(before, [v.get() for v in self.ui.lines])

    def test_save_cancel_and_confirm_run_on_ui_thread(self):
        self.ui.lines[3].set('/echo changed')
        main_thread = threading.get_ident()
        def answer(*args, **kwargs):
            self.assertEqual(threading.get_ident(), main_thread)
            return False
        with patch('prototypes.macro_editor.dialogs.askyesno', side_effect=answer):
            self.ui.preview()
        self.assertTrue(self.ui.differences())
        with patch('prototypes.macro_editor.dialogs.askyesno', return_value=True):
            self.ui.preview()
        self.assertFalse(self.ui.differences())
        self.assertEqual(self.root.grab_current(), None)

    def test_tab_opens_production_phrase_picker_and_escape_returns(self):
        self.root.focus_force()
        entry = self.ui.entries[2]
        entry.focus_set()
        self.root.update()
        entry.event_generate('<Tab>')
        self.root.update()
        popup = self.ui.phrase_entries[2].popup
        self.assertIsNotNone(popup)
        self.assertTrue(popup.winfo_exists())
        self.assertIsInstance(self.root.focus_get(), __import__('tkinter').ttk.Combobox)
        popup.event_generate('<Escape>')
        self.root.update()
        self.assertEqual(self.root.focus_get(), entry)
        self.assertFalse(self.ui.differences())

    def test_phrase_insert_retains_identity_across_macro_switch(self):
        adapter = self.ui.phrase_entries[2]
        from ff11reader.text_editing import replace_range
        phrase = self.ui.catalog.search('ケアル')[0]
        adapter.set_value(replace_range(adapter.value, 0, 0, phrase.label, phrase.identity), len(phrase.label))
        self.ui.select_macro('Alt', 0)
        self.ui.select_macro('Ctrl', 0)
        self.assertEqual(self.ui.lines[2].get(), phrase.label)
        self.assertEqual(adapter.value.tokens[0].identity, phrase.identity)

    def test_equipment_candidates_apply_cancel_and_inventory_filter(self):
        ui = self.ui.equipment
        ui.edit_slot(0)
        ui.candidates.selection_set('16')
        ui.apply_candidate()
        self.assertEqual(ui.sets[0][0], 16)
        self.assertFalse(ui.editing)
        ui.edit_slot(0)
        ui.candidates.selection_set('remove')
        ui.show_summary()
        self.assertEqual(ui.sets[0][0], 16)
        ui.query.set('ロスタム')
        self.assertEqual(len(ui.inventory.get_children()), 2)
        ui.bag.set('ワードローブ2')
        ui.refresh_inventory()
        self.assertEqual(ui.inventory.get_children(), ('16',))


if __name__ == '__main__':
    unittest.main()
