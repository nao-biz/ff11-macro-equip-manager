"""Synthetic selection, transfer, and common-save integration tests."""
from copy import deepcopy
from dataclasses import replace
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from ff11reader.domain import Character
from ff11reader.transfer_editing import capture, plan_paste, plan_delete
from ff11reader.editing import EditSession
from tests.test_paste_placement import macro, palette, equipment, text
from tests.test_equipment_moves import MoveFixture


class TransferTests(unittest.TestCase):
    def test_default_named_equipment_destination(self):
        from ff11reader.equipment_moves import plan_move
        c=Character('a',equipsets=[equipment(10,'CorTriple'),equipment(13,'Set013')])
        original=deepcopy(c)
        for cut in (False,True):
            edit=plan_paste(c,capture(c,'equipment',((10,),),cut),(13,))
            target=next(change.after for change in edit.changes if change.key==(13,))
            self.assertEqual(target.title.display,'CorTriple')
            self.assertEqual(c,original)
        self.assertTrue(plan_move(c,10,13).changes)
        for title,action in (('Reserved','keep'),('Set010','keep'),('Set013','remove'),('Set013','equip'),('Set013','unknown')):
            c.equipsets[1]=equipment(13,title,action)
            with self.subTest(title=title,action=action),self.assertRaisesRegex(ValueError,'内容があります'):
                plan_paste(c,capture(c,'equipment',((10,),)),(13,))

    def character(self):
        c=Character('a',macros=palette(1,1)+palette(1,2)+palette(2,3),equipsets=[equipment(n) for n in range(1,10)])
        c.macros[0]=replace(c.macros[0],title=text('Source'),lines=(text('/macro set 2'),)+(text(),)*5)
        return c

    def test_copy_cross_book_preserves_destination_and_snapshot(self):
        c=self.character();transfer=capture(c,'macro',((1,1,'ctrl',1),))
        c.macros[0]=replace(c.macros[0],title=text('Changed'))
        before=deepcopy(c)
        edit=plan_paste(c,transfer,(2,3,'alt',2))
        self.assertEqual(len(edit.changes),1)
        moved=edit.changes[0].after
        self.assertEqual(moved.title.display,'Source')
        self.assertEqual([t.display for t in moved.lines[:2]],['/macro book 1','/macro set 2'])
        self.assertEqual(c,before)

    def test_cut_is_stale_checked_and_overflow_rejected(self):
        c=self.character();transfer=capture(c,'macro',((1,1,'ctrl',1),),True)
        c.macros[0]=replace(c.macros[0],title=text('Changed'))
        with self.assertRaisesRegex(ValueError,'切り取り元'):plan_paste(c,transfer,(2,3,'alt',2))
        c.macros[0]=replace(c.macros[0],lines=(text('/macro set 2'),)+(text('/echo keep'),)*5)
        transfer=capture(c,'macro',((1,1,'ctrl',1),))
        with self.assertRaisesRegex(ValueError,'7行'):plan_paste(c,transfer,(2,3,'alt',2))

    def test_palette_cascade_updates_external_and_preserves_later_context(self):
        c=self.character()
        c.macros[20]=replace(c.macros[20],lines=(text('/macro set 1'),text('/macro set 2'))+(text(),)*4)
        edit=plan_paste(c,capture(c,'palette',((1,1),),True),(2,3))
        external=next(x.after for x in edit.changes if x.key==(1,2,'ctrl',1))
        self.assertEqual([t.display for t in external.lines[:4]],['/macro book 2','/macro set 3','/macro book 1','/macro set 2'])
        source=next(x.after for x in edit.changes if x.key==(1,1,'ctrl',1))
        self.assertFalse(source.title.display)

    def test_delete_and_equipment_multi_move_one_undo(self):
        from ff11reader.domain import Snapshot
        c=self.character();c.equipsets[0]=equipment(1,'One');c.equipsets[2]=equipment(3,'Three')
        session=EditSession(Snapshot('synthetic','',[c],{},[],[]))
        edit=plan_paste(c,capture(c,'equipment',((1,),(3,)),True),(5,))
        session.apply(edit)
        self.assertEqual(session.character('a').equipsets[4].title.display,'One')
        self.assertEqual(session.character('a').equipsets[6].title.display,'Three')
        session.undo();self.assertFalse(session.dirty);session.redo()
        session.apply(plan_delete(session.character('a'),'equipment',((5,),(7,))))
        self.assertFalse(session.character('a').equipsets[4].title.display)
        session.undo();self.assertEqual(session.character('a').equipsets[4].title.display,'One')


class CommonSaveTests(MoveFixture):
    def test_legacy_draft_reconstructs_record_and_partial_save_is_blocked(self):
        import json
        from ff11reader.edit_application import Editor
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Renamed',
            [t.display for t in self.source.characters[0].macros[0].lines]))
        path=self.base/'draft.json';data=json.loads(path.read_text(encoding='utf-8'))
        def strip_record(node):
            if isinstance(node,dict):
                if node.get('type')=='Macro':node['fields'].pop('raw_hex',None)
                for v in node.values():strip_record(v)
            elif isinstance(node,list):
                for v in node:strip_record(v)
        strip_record(data);path.write_text(json.dumps(data),encoding='utf-8')
        self.editor=Editor(self.load(),path);self.assertIsNone(self.editor.blocked)
        self.editor.capture_transfer('abc','macro',((1,1,'ctrl',1),))
        self.assertEqual(len(self.editor.transfer.items[0].raw_hex),760)
        edit=self.editor.prepare_paste('abc',(1,2,'alt',5));self.editor.paste('abc',(1,2,'alt',5),edit)
        with self.assertRaisesRegex(ValueError,'一括'):self.editor.prepare_macro_save('abc','storage-fix')
        plan=self.editor.prepare_combined_save('abc');self.editor.save_combined(plan,self.base/'backups')
        self.assertFalse(self.editor.session.dirty)

    def test_copy_raw_record_and_undo_save_restore_unknown_bytes(self):
        from tests.test_saving import checksum
        from ff11reader.edit_application import Editor
        source=self.folder/'mcr.dat';target=self.folder/'mcr1.dat'
        raw=bytearray(source.read_bytes());raw[24:28]=b'META';raw[403]=87
        source.write_bytes(checksum(raw))
        raw=bytearray(target.read_bytes());offset=24+14*380
        raw[offset:offset+4]=b'TARG';raw[offset+379]=81
        target.write_bytes(checksum(raw))
        original={p:p.read_bytes() for p in self.folder.iterdir()}
        self.editor=Editor(self.load(),self.base/'draft.json')
        self.editor.capture_transfer('abc','macro',((1,1,'ctrl',1),))
        edit=self.editor.prepare_paste('abc',(1,2,'alt',5));self.editor.paste('abc',(1,2,'alt',5),edit)
        plan=self.editor.prepare_combined_save('abc');self.editor.save_combined(plan,self.base/'backups')
        self.assertEqual(target.read_bytes()[offset:offset+380],original[source][24:404])
        # Restart retains the original destination record for undo, including its prefix.
        self.editor=Editor(self.load(),self.base/'draft.json');self.assertIsNone(self.editor.blocked)
        current=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'alt',5))
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'alt',5),'Again',list(current.lines)))
        self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'backups')
        self.editor.undo();self.editor.undo();plan=self.editor.prepare_combined_save('abc');self.editor.save_combined(plan,self.base/'backups')
        for p,raw in original.items():self.assertEqual(p.read_bytes(),raw)

    def test_macro_copy_undo_redo_and_common_save(self):
        self.editor.capture_transfer('abc','macro',((1,1,'ctrl',1),))
        edit=self.editor.prepare_paste('abc',(1,2,'alt',5))
        self.editor.paste('abc',(1,2,'alt',5),edit)
        self.assertIsNotNone(self.editor.transfer)
        self.editor.undo();self.assertFalse(self.editor.session.dirty);self.editor.redo()
        plan=self.editor.prepare_combined_save('abc')
        self.assertIsNone(plan.equipment)
        self.editor.save_combined(plan,self.base/'backups')
        self.assertFalse(self.editor.session.dirty)
        target=next(m for m in self.load().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'alt',5))
        self.assertEqual(target.title.display,'Test')
        self.assertEqual(target.lines[3].tokens,self.source.characters[0].macros[0].lines[3].tokens)

    def test_plain_mixed_edit_common_save(self):
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc',1,'New'))
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'New',['/echo new']+['']*5))
        plan=self.editor.prepare_combined_save('abc')
        self.assertIsNotNone(plan.equipment);self.assertIsNotNone(plan.macro)
        self.editor.save_combined(plan,self.base/'backups')
        self.assertFalse(self.editor.session.dirty)

    def test_preview_staleness_and_reset_clipboard(self):
        self.editor.capture_transfer('abc','macro',((1,1,'ctrl',1),),True)
        edit=self.editor.prepare_paste('abc',(1,2,'alt',5))
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'alt',5),'Busy',['']*6))
        with self.assertRaises(ValueError):self.editor.paste('abc',(1,2,'alt',5),edit)
        self.assertIsNotNone(self.editor.transfer)
        self.editor.start_fresh();self.assertIsNone(self.editor.transfer)


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Enable synthetic Tk tests')
class SelectionUITests(MoveFixture):
    def test_real_key_bindings_and_entry_delete(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        app=tk.Tk()
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            source=view.commands.cards[(1,1,'ctrl',1)]
            source.event_generate('<Button-1>',x=5,y=5);source.focus_force();app.update()
            source.event_generate('<Control-c>');app.update()
            self.assertIsNotNone(self.editor.transfer)
            target=view.commands.cards[(1,1,'alt',5)]
            target.event_generate('<Button-1>',x=5,y=5);target.focus_force();app.update()
            target.event_generate('<Control-v>');app.update()
            preview=app.grab_current();self.assertIsNotNone(preview)
            preview.focus_force();app.update();preview.event_generate('<Escape>');app.update();self.assertFalse(self.editor.session.dirty)
            self.assertIsNone(app.grab_current())
            target=view.commands.cards[(1,1,'alt',5)];target.focus_force();app.update()
            target.event_generate('<Control-v>');app.update();preview=app.grab_current()
            from tkinter import ttk
            next(w for w in preview.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
            self.assertTrue(self.editor.session.dirty)
            target=view.commands.cards[(1,1,'alt',5)]
            self.assertEqual(app.focus_get(),target)
            target.event_generate('<Control-z>');app.update();self.assertFalse(self.editor.session.dirty)
            self.assertEqual(app.focus_get(),view.commands.cards[(1,1,'alt',5)])
            input_window=tk.Toplevel(app);entry=tk.Entry(input_window);entry.pack();entry.insert(0,'sample');app.update()
            entry.focus_force();app.update();entry.selection_range(0,'end');entry.event_generate('<Delete>');app.update()
            self.assertEqual(entry.get(),'');self.assertFalse(self.editor.session.dirty)
        finally:app.destroy()

    def test_select_copy_preview_undo_delete_and_common_save_button(self):
        import tkinter as tk
        from tkinter import ttk
        from ff11reader.ui import ReaderWindow
        app=tk.Tk();app.withdraw();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
        guard=patch('ff11reader.dialogs.showerror',side_effect=AssertionError('unexpected error dialog'));guard.start();self.addCleanup(guard.stop)
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            cmd=view.commands
            cmd.select('macro',(1,1,'ctrl',1));cmd.select('macro',(1,1,'ctrl',3),control=True)
            self.assertEqual(len(cmd.selection),2)
            cmd.run('copy')
            cmd.select('macro',(1,1,'alt',5));cmd.run('paste');app.update()
            preview=app.grab_current();self.assertIsNotNone(preview)
            detail=next(w for w in preview.winfo_children() if isinstance(w,tk.Text)).get('1.0','end')
            self.assertIn('ALT 5',detail)
            next(w for w in preview.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
            self.assertTrue(self.editor.session.dirty)
            cmd.run('undo');self.assertFalse(self.editor.session.dirty)
            cmd.run('redo');self.assertTrue(self.editor.session.dirty)
            cmd.select('macro',(1,1,'alt',5));cmd.run('cut');self.assertTrue(self.editor.transfer.cut)
            cmd.run('cancel');self.assertIsNone(self.editor.transfer)
            cmd.run('delete');app.update();preview=app.grab_current()
            next(w for w in preview.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
            cmd.select('palette',(1,1));cmd.select('palette',(1,2),shift=True)
            self.assertEqual(len(cmd.selection),2)
            self.editor.apply(self.editor.prepare_equipment_name_edit('abc',1,'New'));view.refresh_edits()
            view.save_button.invoke();app.update()
            self.assertTrue(any('一括保存' in w.title() for w in app.winfo_children() if isinstance(w,tk.Toplevel)))
            self.assertFalse(errors,errors)
            for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)
        finally:app.destroy()

    def test_right_click_and_text_shortcuts_do_not_delete_objects(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        app=tk.Tk();app.withdraw()
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            cmd=view.commands;cmd.select('equipment',(1,))
            with patch.object(cmd.menu,'tk_popup') as popup:
                cmd.context(SimpleNamespace(widget=view.nav,x_root=10,y_root=10),('equipment',(1,)))
                popup.assert_called_once()
            self.assertEqual(cmd.menu.entrycget(0,'accelerator'),'Ctrl+X')
            entry=tk.Entry(app)
            self.assertNotIn('keypress',entry.bind('<Control-KeyPress>'))
            # Clipboard keys are bound to target views, not root or Entry classes.
            self.assertTrue(view.nav.bind('<Control-KeyPress>'))
            self.assertFalse(app.bind('<Control-KeyPress>'))
            self.assertFalse(self.editor.session.dirty)
        finally:app.destroy()
