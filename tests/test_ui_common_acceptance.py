"""VIEW-008 / D-19 acceptance probes using synthetic files.

Expected failures track confirmed gaps, not accepted exceptions.
Remove each marker when its implementation satisfies the assertion.
"""
import gc
import os
import tkinter as tk
import unittest
from unittest.mock import patch
from ff11reader.ui import ReaderWindow
from tests.test_equipment_moves import MoveFixture


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class CommonUIAcceptanceTests(MoveFixture):
    def open_view(self, mode='マクロ'):
        self.app = tk.Tk()
        self.errors = []
        self.app.report_callback_exception = lambda *e: self.errors.append(e)
        self.addCleanup(self.close_view)
        self.view = ReaderWindow(self.app, self.source, editor=self.editor)
        self.view.tabs.select(mode)
        self.app.update()
        self.app.focus_force()
        return self.view

    def close_view(self):
        self.app.destroy()
        gc.collect()
        self.assertFalse(self.errors, self.errors)

    def key(self, widget, key):
        widget.focus_force()
        self.app.update()
        widget.event_generate('<' + key + '>')
        self.app.update()

    def test_enter_escape_restores_line_and_tokens(self):
        panel = self.open_view().macro_panel
        entry = panel.entries[1]
        before = panel.controllers[0].value
        with patch('ff11reader.macro_editor_ui.ime_composing', return_value=False):
            self.key(entry, 'Return')
            self.assertEqual(panel.editing_line, 1)
            entry.insert('end', ' changed')
            self.key(entry, 'Escape')
        self.assertIsNone(panel.editing_line)
        self.assertEqual(panel.controllers[0].value, before)
        self.assertIs(self.app.focus_get(), entry)

    def test_nested_phrase_escape_keeps_parent_edit(self):
        panel = self.open_view().macro_panel
        entry = panel.entries[1]
        with patch('ff11reader.macro_editor_ui.ime_composing', return_value=False):
            self.key(entry, 'Return')
        entry.insert('end', ' retained')
        before = panel.controllers[0].value
        self.key(entry, 'Tab')
        popup = panel.controllers[0].popup
        self.assertIsNotNone(popup)
        self.key(popup, 'Escape')
        self.assertEqual(panel.editing_line, 1)
        self.assertEqual(panel.controllers[0].value, before)
        self.assertIs(self.app.focus_get(), entry)

    def test_macro_name_requires_decision_before_typing(self):
        panel = self.open_view().macro_panel
        name = panel.entries[0]
        before = name.get()
        name.insert('end', 'x')
        self.assertEqual(name.get(), before, 'UI-G01: name is directly editable in selection stage')

    def test_enter_commits_line_to_undo_history(self):
        panel = self.open_view().macro_panel
        entry = panel.entries[1]
        before = panel.controllers[0].value
        cursor = self.editor.edit_status()[0]
        with patch('ff11reader.macro_editor_ui.ime_composing', return_value=False):
            self.key(entry, 'Return')
            entry.insert('end', ' changed')
            self.key(entry, 'Return')
        self.assertEqual(self.editor.edit_status()[0], cursor + 1,
                         'UI-G02: Enter leaves a pending buffer outside Undo history')
        self.assertIs(self.app.focus_get(),entry)
        self.key(entry,'Control-z')
        self.assertEqual(panel.controllers[0].value.display,before.display)
        self.key(entry,'Control-y')
        self.assertEqual(panel.controllers[0].value.display,before.display+' changed')
        self.assertIs(self.app.focus_get(),entry)

    def test_equipment_arrow_moves_slot_and_focus(self):
        view = self.open_view('装備セット')
        self.assertEqual(view.active_slot, 'main')
        self.key(view.card_widgets['main'], 'Right')
        self.assertEqual(view.active_slot, 'sub', 'UI-G03: equipment cards lack arrow navigation')
        self.assertIs(self.app.focus_get(), view.card_widgets['sub'])

    def test_equipment_candidate_escape_returns_to_slot(self):
        view = self.open_view('装備セット')
        picker = view.slot_editor
        self.assertIsNotNone(picker)
        picker.listing.selection_set('remove')
        picker.select()
        self.key(picker.listing, 'Escape')
        self.assertFalse(picker.listing.selection(), 'UI-G04: child tree does not receive parent Frame Escape binding')
        self.assertIs(self.app.focus_get(), view.card_widgets[view.active_slot])
    def test_inventory_arrows_move_item_and_focus(self):
        from ff11reader.domain import InventoryRow
        from ff11reader.edit_application import Editor
        self.source.characters[0].inventory = [InventoryRow(0, 1, 100, 1), InventoryRow(0, 2, 101, 1)]
        self.source.characters[0].inventory_coverage[0] = 'loaded'
        self.editor = Editor(self.source, self.base / 'inventory-audit.json')
        view = self.open_view('インベントリ')
        view.open_inventory(0, 1)
        self.app.update()
        self.assertEqual(view.active_inventory, 1)
        self.key(view.card_widgets[1], 'Down')
        self.assertEqual(view.active_inventory, 2, 'UI-G05: inventory rows lack arrow navigation')
        self.assertIs(self.app.focus_get(), view.card_widgets[2])

    def test_failed_commit_keeps_edit_for_retry(self):
        panel=self.open_view().macro_panel;entry=panel.entries[1]
        with patch('ff11reader.macro_editor_ui.ime_composing',return_value=False):
            self.key(entry,'Return');entry.insert('end',' retry')
            with patch.object(self.editor,'apply',side_effect=OSError('synthetic failure')):
                self.key(entry,'Return')
            self.assertEqual(panel.flow.stage,'edit')
            self.assertEqual(panel.editing_line,1)
            self.assertTrue(entry.get().endswith(' retry'))
            self.assertEqual(self.editor.edit_status()[0],0)
            self.key(entry,'Return')
        self.assertEqual(panel.flow.stage,'select')
        self.assertEqual(self.editor.edit_status()[0],1)
    def test_equipment_navigation_decision_and_return(self):
        view=self.open_view('装備セット')
        self.key(view.nav,'Return')
        self.assertIs(self.app.focus_get(),view.card_widgets['main'])
        self.key(view.card_widgets['main'],'Return')
        self.assertIs(self.app.focus_get(),view.slot_editor.listing)
        self.key(view.slot_editor.listing,'Escape')
        self.assertIs(self.app.focus_get(),view.card_widgets['main'])
        self.key(view.card_widgets['main'],'Escape')
        self.assertIs(self.app.focus_get(),view.nav)

    def test_macro_enter_and_escape_follow_hierarchy(self):
        view=self.open_view()
        address=view.active_macro
        card=view.commands.cards[address]
        self.key(card,'Return')
        self.assertIs(self.app.focus_get(),view.macro_panel.entries[1])
        self.key(view.macro_panel.entries[1],'Escape')
        self.assertIs(self.app.focus_get(),card)
        self.key(card,'Escape')
        self.assertIs(self.app.focus_get(),view.macro_tree)

    def test_inventory_panel_edges_and_detail_return(self):
        from ff11reader.domain import InventoryRow
        from ff11reader.edit_application import Editor
        self.source.characters[0].inventory=[InventoryRow(0,n,100+n,1) for n in range(1,7)]
        self.source.characters[0].inventory_coverage[0]='loaded'
        self.editor=Editor(self.source,self.base/'panel-audit.json')
        view=self.open_view('インベントリ');view.inventory_layout.set('パネル');view.open_inventory(0,1);self.app.update()
        self.key(view.card_widgets[1],'Down');self.assertEqual(view.active_inventory,5)
        self.key(view.card_widgets[5],'Right');self.assertEqual(view.active_inventory,6)
        self.key(view.card_widgets[6],'Right');self.assertEqual(view.active_inventory,6)
        self.key(view.card_widgets[6],'Up');self.assertEqual(view.active_inventory,2)
        self.key(view.card_widgets[2],'Return')
        windows=[w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel)]
        self.assertEqual(len(windows),1)
        self.key(windows[0],'Escape')
        self.assertIs(self.app.focus_get(),view.card_widgets[2])

    def test_text_undo_is_separate_from_published_history(self):
        panel=self.open_view().macro_panel;entry=panel.entries[1]
        before=panel.controllers[0].value
        with patch('ff11reader.macro_editor_ui.ime_composing',return_value=False):
            self.key(entry,'Return');entry.insert('end',' draft');self.app.update()
            draft=panel.controllers[0].value
            self.key(entry,'Control-z');self.assertEqual(panel.controllers[0].value,before)
            self.key(entry,'Control-y');self.assertEqual(panel.controllers[0].value,draft)
            self.assertEqual(self.editor.edit_status()[0],0)
            self.key(entry,'Return')
        self.assertEqual(self.editor.edit_status()[0],1)
        self.key(entry,'Control-z');self.assertEqual(panel.controllers[0].value.display,before.display)
