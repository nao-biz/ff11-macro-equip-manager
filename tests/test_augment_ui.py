from dataclasses import replace
import gc
import os
import tkinter as tk
import unittest
from threading import get_ident
from unittest.mock import patch
from tests.test_equipment_moves import MoveFixture
from tests.test_augment_import import fixture, encoded, character
from tests.test_ui_tasks import TkThreadGuard
from ff11reader.edit_application import Editor
from ff11reader.ui import ReaderWindow
from ff11reader.augment_import import load_observation

@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class AugmentUITests(MoveFixture):
    def tearDown(self):
        gc.collect()

    def test_import_cancel_failure_history_and_reload(self):
        c=character()
        self.source.characters[0].inventory=c.inventory
        self.source.characters[0].inventory_coverage=c.inventory_coverage
        self.editor=Editor(self.source,self.base/'draft.json',root=self.folder.parent.parent)
        path=self.base/'export.json';path.write_bytes(encoded(fixture()))
        app=tk.Tk();app.tk=TkThreadGuard(app.tk)
        owner=get_ident();calls=[]
        from ff11reader.augment_store import AugmentStore
        for method in ('save','restore'):
            original=getattr(AugmentStore,method)
            def checked(store,*args,_original=original,**kwargs):
                self.assertNotEqual(owner,get_ident())
                return _original(store,*args,**kwargs)
            handle=patch.object(AugmentStore,method,checked)
            handle.start();self.addCleanup(handle.stop)
        def read(*args):
            self.assertNotEqual(owner,get_ident());calls.append(1)
            return load_observation(*args)
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            app.update()
            before=self.editor.edit_status()
            with patch('ff11reader.ui.filedialog.askopenfilename',return_value=str(path)),patch('ff11reader.augment_import.load_observation',side_effect=read),patch('ff11reader.ui.dialogs.askyesno',return_value=True),patch('ff11reader.ui.dialogs.showerror') as errors:
                view.import_button.invoke()
                self.assertEqual(len(calls),1)
                observation=view.augment_observations['abc']
                self.assertIn('Path: B',view.augment_text(c.inventory[0]))
                self.assertIn('Path: C',view.augment_text(c.inventory[1]))
                from ff11reader.equipment_ui import SlotEditor
                slot=view.character.equipsets[0].slots[0]
                picker=SlotEditor(app,'Synthetic',slot,c.inventory,{}, {12:'Wardrobe4'},lambda *args:None,augment_text=view.augment_text)
                picker.listing.selection_set('1');picker.show_augment()
                self.assertIn('Path: C',picker.augment_detail.cget('text'))
                picker.window.destroy()
                equipset=view.character.equipsets[0]
                slot=replace(equipset.slots[0],action='equip',item_id=21581,container=12,index=1)
                equipment=replace(equipset,slots=(slot,)+equipset.slots[1:])
                view.clear_cards();view.render_equipment(equipment)
                card=view.card_widgets[slot.name]
                texts=[card.itemcget(node,'text') for node in card.find_all() if card.type(node)=='text']
                self.assertTrue(view.equipment_summary.frame.winfo_manager())
                self.assertFalse(view.import_button.winfo_manager())
                self.assertTrue(view.operation_button.winfo_manager())
                self.assertIn('集計できた加算値',view.equipment_summary.note.cget('text'))
                self.assertIn('Path B',texts)
                self.assertFalse(set(texts) & {'一致','Fix可能','候補が複数','候補なし'})
                self.assertEqual({int(float(w.cget('height'))) for w in view.card_widgets.values()},{104})
                node=next(n for n in card.find_all() if card.type(n)=='text' and card.itemcget(n,'text')=='Path B')
                self.assertEqual(card.coords(node)[1],96)
                self.assertEqual(view.augment_path(replace(slot,index=80)),'')
                view.open_inventory(12,62)
                view.inventory_layout.set('リスト');view.switch_inventory_layout();app.update()
                card=view.card_widgets[62]
                texts=[card.itemcget(node,'text') for node in card.find_all() if card.type(node)=='text']
                self.assertIn('Path C',texts)
                self.assertEqual(int(float(card.cget('height'))),44)
                card.event_generate('<Button-1>',x=100,y=20);app.update()
                self.assertIn('Path: C',view.detail.get('1.0','end'))
                view.inventory_layout.set('パネル');view.switch_inventory_layout()
                self.assertEqual(int(float(view.card_widgets[62].cget('height'))),104)
                view.inventory_layout.set('リスト');view.switch_inventory_layout()
                view.mode.set('装備セット');view.change_mode();app.update()
                self.assertFalse(view.inventory_switch.winfo_ismapped())
                view.open_inventory(12,1)
                self.assertEqual(view.inventory_layout.get(),'リスト')
                view.inspect_inventory(c.inventory[0])
                self.assertIn('Path: B',view.detail.get('1.0','end'))
                with patch('ff11reader.ui.dialogs.askyesno',return_value=False):view.import_button.invoke()
                self.assertIs(view.augment_observations['abc'],observation)
                with patch.object(view.augment_store,'save',side_effect=OSError('synthetic failure')):
                    view.import_button.invoke()
                self.assertIs(view.augment_observations['abc'],observation)
                errors.assert_called_once();errors.reset_mock()
                path.write_bytes(b'broken');view.import_button.invoke()
                errors.assert_called_once()
                self.assertIs(view.augment_observations['abc'],observation)
                self.assertEqual(self.editor.edit_status(),before)
                view.reload_data()
                self.assertEqual(view.augment_observations['abc'].export,observation.export)
                self.assertNotIn(12,view.augment_observations['abc'].accepted_bags)
            # A new view reconstructs the saved observation without the source JSON.
            path.unlink()
            app.destroy();del view,app
            gc.collect()
            app=tk.Tk();app.tk=TkThreadGuard(app.tk)
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            self.assertEqual(view.augment_observations['abc'].export,observation.export)
            self.assertEqual(self.original,{p:p.read_bytes() for p in self.folder.iterdir()})
        finally:
            app.destroy()
            del view, app
            if "picker" in locals(): del picker
            gc.collect()
