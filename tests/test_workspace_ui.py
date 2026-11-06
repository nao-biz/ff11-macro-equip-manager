"""Production workspace contracts with synthetic files and real Tk widgets."""
import gc
import os
import time
import tkinter as tk
from threading import get_ident
import unittest
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from tests.test_equipment_slots import SlotFixture
from tests.test_ui_tasks import TkThreadGuard
from ff11reader.ui import ReaderWindow


class WorkspaceMixin:
    def open_view(self):
        self.app=tk.Tk();self.app.tk=TkThreadGuard(self.app.tk)
        self.callbacks=[]
        self.unraisable=patch('sys.unraisablehook',side_effect=lambda error:self.callbacks.append(error.exc_value))
        self.unraisable.start();self.addCleanup(self.unraisable.stop)
        self.app.report_callback_exception=lambda *e:self.callbacks.append(e)
        self.view=ReaderWindow(self.app,self.source,editor=self.editor)
        self.app.update();self.app.focus_force()
        return self.view

    def tearDown(self):
        if hasattr(self,'app'):
            self.app.destroy();del self.view;del self.app
        gc.collect()
        self.assertFalse(getattr(self,'callbacks',[]))

    def preview_window(self):
        return next(w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel))


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class MacroWorkspaceTests(WorkspaceMixin,MoveFixture):
    def test_minimum_macro_layout_and_default_equipment_layout_fit(self):
        view=self.open_view()
        bottom=view.card_widgets['feet']
        self.assertLessEqual(bottom.winfo_y()+bottom.winfo_height(),view.canvas.winfo_height())
        self.app.geometry('1100x800');view.tabs.select('マクロ');self.app.update()
        for widget in (*view.macro_panel.entries,view.macro_panel.preview_button,view.save_button):
            self.assertTrue(widget.winfo_viewable())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.app.winfo_rooty()+self.app.winfo_height())
        self.assertLessEqual(view.cards.winfo_reqheight(),view.canvas.winfo_height())

    def test_character_switch_keeps_separate_macro_inputs(self):
        from copy import deepcopy
        from ff11reader.edit_application import Editor
        other=deepcopy(self.source.characters[0]);other.folder_id='second'
        self.source.characters.append(other)
        self.editor=Editor(self.source,self.base/'characters.json')
        view=self.open_view();view.tabs.select('マクロ');panel=view.macro_panel
        panel.entries[0].delete(0,'end');panel.entries[0].insert(0,'First')
        view.character_choice.current(1);view.change_character()
        self.assertEqual(panel.entries[0].get(),'Test')
        panel.entries[0].delete(0,'end');panel.entries[0].insert(0,'Second')
        view.character_choice.current(0);view.change_character()
        self.assertEqual(panel.entries[0].get(),'First')
        view.character_choice.current(1);view.change_character()
        self.assertEqual(panel.entries[0].get(),'Second')

    def test_input_tokens_and_selection_survive_navigation_and_apply(self):
        view=self.open_view();view.tabs.select('マクロ');self.app.update()
        panel=view.macro_panel;address=view.active_macro
        original_tokens=panel.controllers[3].value.tokens
        panel.entries[0].delete(0,'end');panel.entries[0].insert(0,'Changed')
        panel.entries[1].insert('end',' ')
        view.inspect_macro(view.character.macros[1]);view.tabs.select('装備セット')
        view.nav.selection_clear(0,'end');view.nav.selection_set(30);view.nav.activate(30);view.select_navigation()
        view.nav.yview_moveto(.6);self.app.update();position=view.nav.yview()[0]
        sizes={n:(w.winfo_width(),w.winfo_height()) for n,w in view.tabs.buttons.items()}
        view.tabs.select('マクロ');view.inspect_macro(view.character.macros[0]);self.app.update()
        self.assertEqual(panel.entries[0].get(),'Changed')
        self.assertEqual(panel.controllers[3].value.tokens,original_tokens)
        self.assertFalse(view.save_button.instate(['disabled']))
        view.tabs.select('装備セット');self.app.update()
        self.assertEqual(view.selected.number,31)
        self.assertAlmostEqual(view.nav.yview()[0],position,places=2)
        self.assertEqual(sizes,{n:(w.winfo_width(),w.winfo_height()) for n,w in view.tabs.buttons.items()})
        view.tabs.select('マクロ');self.assertEqual(view.active_macro,address)
        panel.preview_button.invoke();self.app.update();preview=self.preview_window()
        self.assertEqual(self.app.focus_get(),preview.cancel_button)
        preview.cancel_button.invoke();self.app.update()
        self.assertEqual(panel.entries[0].get(),'Changed');self.assertFalse(self.editor.edit_status()[2])
        panel.preview_button.invoke();self.preview_window().accept_button.invoke();self.app.update()
        self.assertEqual(view.character.macros[0].title.display,'Changed')
        self.assertFalse(panel.has_pending());view.undo_fix()
        self.assertEqual(view.character.macros[0].title.display,'Test')
        for path,raw in self.original.items():self.assertEqual(path.read_bytes(),raw)

    def test_arrow_keys_move_input_and_tab_opens_phrase_picker(self):
        view=self.open_view();view.tabs.select('マクロ');self.app.update()
        fields=view.macro_panel.entries
        fields[1].focus_force();fields[1].icursor(3);fields[1].event_generate('<Down>');self.app.update()
        self.assertIs(self.app.focus_get(),fields[2]);self.assertEqual(fields[2].index('insert'),3)
        fields[2].event_generate('<Up>');self.app.update();self.assertIs(self.app.focus_get(),fields[1])
        fields[1].event_generate('<Tab>');self.app.update()
        popup=view.macro_panel.controllers[0].popup
        self.assertTrue(popup.winfo_exists());popup.event_generate('<Escape>');self.app.update()
        self.assertIs(self.app.focus_get(),fields[1])

    def test_pending_input_precedes_game_save_and_survives_failed_apply(self):
        view=self.open_view();view.tabs.select('マクロ');self.app.update()
        panel=view.macro_panel;panel.entries[0].delete(0,'end');panel.entries[0].insert(0,'Changed')
        with patch.object(self.editor,'prepare_combined_save',wraps=self.editor.prepare_combined_save) as prepare:
            view.preview_combined_save();self.app.update();preview=self.preview_window()
            prepare.assert_not_called();self.assertIn('作業データ',preview.title())
            owner=get_ident();ticks=[]
            def failure(edit):
                self.assertNotEqual(get_ident(),owner);time.sleep(.08);raise OSError('synthetic failure')
            self.app.after(10,lambda:ticks.append(1))
            with patch.object(self.editor,'apply',side_effect=failure),patch('ff11reader.ui.dialogs.showerror') as error:
                preview.accept_button.invoke();self.app.update();error.assert_called_once()
            self.assertTrue(ticks);self.assertEqual(panel.entries[0].get(),'Changed')
            self.assertEqual(self.app.grab_current(),preview)
            preview.accept_button.invoke();self.app.update();prepare.assert_called_once()
            self.assertFalse(panel.has_pending());saving=self.preview_window()
            self.assertEqual(self.app.focus_get(),saving.cancel_button)
            saving.cancel_button.invoke()
        for path,raw in self.original.items():self.assertEqual(path.read_bytes(),raw)

    def test_stale_input_rejected_and_revert_uses_latest_work(self):
        view=self.open_view();view.tabs.select('マクロ');self.app.update();panel=view.macro_panel
        panel.entries[0].delete(0,'end');panel.entries[0].insert(0,'Input')
        macro=view.character.macros[0]
        edit=self.editor.prepare_macro_edit('abc',view.active_macro,'External',macro.lines)
        view.run_edit(lambda:self.editor.apply(edit))
        with patch('ff11reader.ui.dialogs.showerror') as error:
            panel.preview();error.assert_called_once()
        self.assertEqual(panel.entries[0].get(),'Input')
        with patch('ff11reader.ui.dialogs.askyesno',return_value=True):panel.revert()
        self.assertEqual(panel.entries[0].get(),'External');self.assertFalse(panel.has_pending())

    def test_declining_exit_and_reset_keeps_inputs(self):
        view=self.open_view();view.tabs.select('マクロ');self.app.update();panel=view.macro_panel
        panel.entries[0].insert('end','X')
        with patch('ff11reader.ui.dialogs.askyesno',return_value=False) as question:
            view.close();view.reset_edits();self.assertEqual(question.call_count,2)
        self.assertEqual(panel.entries[0].get(),'TestX');self.assertTrue(self.app.winfo_exists())
        with patch('ff11reader.ui.dialogs.askyesno',return_value=True),patch.object(self.editor,'start_fresh',side_effect=OSError('failure')),patch('ff11reader.ui.dialogs.showerror'):
            view.reset_edits()
        self.assertEqual(panel.entries[0].get(),'TestX')


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class EquipmentWorkspaceTests(WorkspaceMixin,SlotFixture):
    def test_right_candidates_keep_filter_and_return_to_summary_after_apply(self):
        view=self.open_view();view.open_slot_editor(view.selected.slots[0]);self.app.update()
        picker=view.slot_editor
        self.assertIs(picker.window.master,view.right_panel);self.assertFalse(view.side_content.winfo_ismapped())
        picker.query.set('剣');picker.filter();picker.action.set('equip');picker.listing.selection_set('1')
        self.app.update()
        self.assertEqual(picker.preview_button.winfo_height(),picker.preview_button.winfo_reqheight())
        self.assertLessEqual(picker.preview_button.winfo_rooty()+picker.preview_button.winfo_height(),view.right_panel.winfo_rooty()+view.right_panel.winfo_height())
        state=picker.input_state();view.tabs.select('インベントリ');view.tabs.select('装備セット');self.app.update()
        self.assertEqual(view.slot_editor.input_state(),state)
        view.slot_editor.cancel();self.app.update();self.assertIsNone(view.slot_editor)
        self.assertTrue(view.equipment_summary.frame.winfo_ismapped())
        view.open_slot_editor(view.selected.slots[0]);picker=view.slot_editor
        picker.action.set('equip');picker.listing.selection_set('0');picker.preview_button.invoke()
        self.preview_window().accept_button.invoke();self.app.update()
        self.assertIsNone(view.slot_editor);self.assertTrue(view.equipment_summary.frame.winfo_ismapped())
        self.assertEqual(view.character.equipsets[0].slots[0].item_id,0x4001)
        view.undo_fix();self.assertEqual(view.character.equipsets[0].slots[0].item_id,100)

    def test_inventory_search_and_explicit_candidate_navigation(self):
        view=self.open_view();view.open_inventory(8,6);self.app.update()
        view.inventory_query.set('胴装備');self.app.update();self.assertEqual(set(view.card_widgets),{7})
        view.tabs.select('装備セット');view.tabs.select('インベントリ');self.app.update()
        self.assertEqual(view.inventory_query.get(),'胴装備');self.assertEqual(set(view.card_widgets),{7})
        view.open_inventory(8,6);self.app.update()
        self.assertEqual(view.inventory_query.get(),'');self.assertIn(6,view.card_widgets)
        self.assertIn('剣',view.detail.get('1.0','end'))
