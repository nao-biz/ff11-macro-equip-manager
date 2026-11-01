"""Movement/cascade tests with generated files only."""
from dataclasses import replace
from pathlib import Path
import os
import struct
import tempfile
import unittest
from unittest.mock import patch
from ff11reader import codecs, combined_saving as saving
from ff11reader.domain import Character, Snapshot
from ff11reader.edit_application import Editor
from ff11reader.edit_values import value
from ff11reader.equipment_moves import vacant
from ff11reader.elevation import encode, decode
from tests.test_saving import checksum


class MoveFixture(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'work'/'move-tests';work.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=work);self.addCleanup(temp.cleanup)
        self.base=Path(temp.name);self.folder=self.base/'game'/'USER'/'abc';self.folder.mkdir(parents=True)
        for page in (0,1,2):
            raw=bytearray(1624);raw[:8]=b'HEADER!!'
            if page==0:
                raw[24:29]=b'Set A';struct.pack_into('<BBH',raw,40,33,2,100)
                raw[24+16+4]=0xA0 # ignored bits of a keep slot must travel
            (self.folder/f'es{page}.dat').write_bytes(checksum(raw))
        for page in (0,1):
            raw=bytearray(7624);raw[:8]=b'HEADER!!'
            lines=[b'/equipset 001 <wait.1>',b'/lockstyleset 1',b'/echo /equipset 1',b'\xfd\x02\x01\x02\x01\xfd 1 <wait.2>']
            for n,line in enumerate(lines):raw[28+n*61:28+n*61+len(line)]=line
            raw[394:398]=b'Test'
            (self.folder/('mcr'+(str(page) if page else '')+'.dat')).write_bytes(checksum(raw))
        for module in ('saving','equipment_saving','macro_saving','combined_saving'):
            handle=patch(f'ff11reader.{module}.require_game_closed');handle.start();self.addCleanup(handle.stop)
        handle=patch('ff11reader.application.load_snapshot',side_effect=lambda root:self.load());handle.start();self.addCleanup(handle.stop)
        handle=patch('ff11reader.adapters.LocalReader.load_phrases',return_value={0x201:'/equipset'});handle.start();self.addCleanup(handle.stop)
        self.source=self.load();self.editor=Editor(self.source,self.base/'draft.json')
        self.original={p:p.read_bytes() for p in self.folder.iterdir()}

    def load(self):
        c=Character('abc')
        for page in (0,1,2):c.equipsets.extend(codecs.equipsets((self.folder/f'es{page}.dat').read_bytes(),page))
        for page in (0,1):c.macros.extend(codecs.macros((self.folder/('mcr'+(str(page) if page else '')+'.dat')).read_bytes(),page))
        c.macros=[replace(m,lines=tuple(codecs.text(bytes.fromhex(t.raw_hex),lambda p:'/equipset' if p==bytes.fromhex('02010201') else None) for t in m.lines)) for m in c.macros]
        sources=[{'path':str(p.resolve()),'sha256':saving.digest(p.read_bytes())} for p in self.folder.iterdir()]
        return Snapshot('test','now',[c],{},sources,[],'move',phrases={0x201:'/equipset'})

    def move(self,source=1,target=45):
        edit=self.editor.prepare_equipment_move('abc',source,target);self.editor.apply(edit);return edit

    def save(self):
        plan=self.editor.prepare_combined_save('abc')
        folder=self.editor.save_combined(plan,self.base/'backups')
        return plan,folder


class MoveTests(MoveFixture):
    def test_move_all_refs_tokens_history_and_reopen(self):
        edit=self.move();self.assertEqual(len(edit.changes),4)
        c=self.editor.session.working.characters[0]
        self.assertTrue(vacant(c.equipsets[0]));self.assertEqual(c.equipsets[44].title.display,'Set A')
        self.assertEqual(c.macros[0].lines[0].display,'/equipset 045 <wait.1>')
        self.assertEqual(c.macros[0].lines[2].display,'/echo /equipset 1')
        self.assertEqual(c.macros[0].lines[3].display,'【/equipset】 45 <wait.2>')
        self.assertEqual(c.macros[0].lines[3].tokens,self.source.characters[0].macros[0].lines[3].tokens)
        self.editor.undo();self.assertFalse(self.editor.session.dirty);self.assertFalse(self.editor.has_pending_move('abc'))
        self.editor.redo();self.editor=Editor(self.source,self.base/'draft.json');self.assertIsNone(self.editor.blocked)
        self.assertTrue(self.editor.has_pending_move('abc'))
        for method in (self.editor.prepare_macro_save,self.editor.prepare_equipment_save):
            with self.assertRaisesRegex(ValueError,'一括'):method('abc')
        for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)

    def test_save_and_undo_save_restores_bytes(self):
        self.move();plan,backup=self.save()
        self.assertEqual(decode(encode(plan)),plan)
        self.assertEqual(len(plan.files),4)
        for i,f in enumerate(plan.files):self.assertEqual((backup/f'{i:03}.original.dat').read_bytes(),f.original)
        self.assertFalse(self.editor.session.dirty)
        self.editor=Editor(self.load(),self.base/'draft.json');self.assertIsNone(self.editor.blocked);self.assertFalse(self.editor.session.dirty)
        self.editor.undo();self.assertTrue(self.editor.has_pending_move('abc'))
        self.save();self.assertFalse(self.editor.session.dirty)
        for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)

    def test_rejects_nonvacant_same_and_empty_source(self):
        for source,target in ((1,1),(2,45),(1,201)):
            with self.assertRaises(ValueError):self.editor.prepare_equipment_move('abc',source,target)
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc',45,'Reserved'))
        with self.assertRaises(ValueError):self.editor.prepare_equipment_move('abc',1,45)
        self.editor.undo()
        self.editor.apply(self.editor.prepare_equipment_slot_edit('abc',45,'main','remove'))
        with self.assertRaises(ValueError):self.editor.prepare_equipment_move('abc',1,45)

    def test_chain_edit_and_branch_after_save(self):
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc',1,'Edited'))
        self.move();self.move(45,22)
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc',22,'Final'))
        self.save();self.assertEqual(self.load().characters[0].equipsets[21].title.display,'Final')
        self.editor.undo();self.editor.undo() # back to 45 with the earlier name
        self.editor.apply(self.editor.prepare_equipment_name_edit('abc',45,'Branch'))
        self.editor=Editor(self.load(),self.base/'draft.json');self.assertIsNone(self.editor.blocked)
        self.save();c=self.load().characters[0]
        self.assertEqual(c.equipsets[44].title.display,'Branch');self.assertTrue(vacant(c.equipsets[21]))
        self.assertIn('045',c.macros[0].lines[0].display)

    def test_omitted_cascade_changes_are_rejected(self):
        edit=self.editor.prepare_equipment_move('abc',1,45)
        with self.assertRaises(ValueError):self.editor.apply(replace(edit,changes=edit.changes[:2]))
        self.assertFalse(self.editor.session.dirty)

    def test_stale_untouched_macro_and_partial_plan_rejected(self):
        self.move();plan=self.editor.prepare_combined_save('abc')
        f=plan.equipment.files[0]
        for bad in (replace(plan,macro=None),replace(plan,dependencies=()),replace(plan,equipment=replace(plan.equipment,files=(f,)))):
            with self.assertRaises(ValueError):saving.execute_combined_save(bad,self.base/'backups')
        path=self.folder/'mcr1.dat';path.write_bytes(path.read_bytes()+b'x')
        with self.assertRaises(ValueError):self.editor.save_combined(plan,self.base/'backups')

    def test_checkpoint_failure_recovers_origin_mapping(self):
        self.move();plan=self.editor.prepare_combined_save('abc');original=self.editor.store.save;calls=0
        def fail(session):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('synthetic checkpoint failure')
            return original(session)
        with patch.object(self.editor.store,'save',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'同期'):self.editor.save_combined(plan,self.base/'backups')
        self.editor=Editor(self.load(),self.base/'draft.json');self.assertIsNone(self.editor.blocked);self.assertFalse(self.editor.session.dirty)
        self.editor.undo();self.save()
        for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)

    def test_unknown_slot_bytes_move_unchanged(self):
        path=self.folder/'es0.dat';raw=bytearray(path.read_bytes());raw[44]=0xFF;raw[45:48]=b'XYZ';path.write_bytes(checksum(raw))
        self.source=self.load();self.editor=Editor(self.source,self.base/'draft.json')
        self.move();self.save()
        after=(self.folder/'es2.dat').read_bytes()
        self.assertEqual(after[24+4*80:24+5*80],bytes(raw[24:104]))

    def test_same_page_move_and_no_references(self):
        for path in self.folder.glob('mcr*.dat'):
            raw=bytearray(path.read_bytes());raw[24:]=bytes(len(raw)-24);path.write_bytes(checksum(raw))
        self.source=self.load();self.editor=Editor(self.source,self.base/'draft.json')
        self.move(1,2);plan,_=self.save()
        self.assertIsNone(plan.macro);self.assertEqual(len(plan.files),1)
        self.assertEqual(self.load().characters[0].equipsets[1].title.display,'Set A')

    def test_failure_rolls_back_and_backup_restores(self):
        self.move();plan=self.editor.prepare_combined_save('abc');original=os.replace
        def fail(src,dst):
            if Path(dst).name=='mcr.dat' and Path(src).name.startswith('.ff11-move-'):raise OSError('synthetic failure')
            return original(src,dst)
        with patch('ff11reader.file_transaction.os.replace',side_effect=fail):
            with self.assertRaises(RuntimeError):self.editor.save_combined(plan,self.base/'backups')
        for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)
        self.assertTrue(self.editor.session.dirty)
        _,backup=self.save();saving.restore_combined_backup(backup,True)
        for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Enable Tk checks')
class MoveUITests(MoveFixture):
    def test_move_preview_undo_and_joint_save(self):
        import tkinter as tk
        from tkinter import ttk
        from ff11reader.ui import ReaderWindow
        app=tk.Tk();app.withdraw();errors=[];app.report_callback_exception=lambda *e:errors.append(e)
        def windows():return [w for w in app.winfo_children() if isinstance(w,tk.Toplevel)]
        try:
            with patch('ff11reader.ui.Editor',return_value=self.editor):view=ReaderWindow(app,self.source)
            view.nav.selection_set(0);view.select_navigation();view.move_button.invoke();app.update()
            window,choice=view.move_dialog;choice.set('045')
            next(w for w in window.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
            preview=windows()[-1];detail=next(w for w in preview.winfo_children() if isinstance(w,tk.Text)).get('1.0','end')
            self.assertIn('045',detail);self.assertIn('/equipset 045',detail)
            next(w for w in preview.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
            view.undo_fix();app.update();self.assertFalse(self.editor.has_pending_move('abc'))
            view.redo_edit();view.preview_equipment_save();app.update()
            joint=windows()[-1];self.assertIn('一括保存',joint.title())
            for p,raw in self.original.items():self.assertEqual(p.read_bytes(),raw)
            save=self.editor.save_combined
            with patch.object(self.editor,'save_combined',side_effect=lambda plan,root:save(plan,self.base/'backups')):
                next(w for w in joint.winfo_children() if isinstance(w,ttk.Button)).invoke()
            app.update();self.assertFalse(errors,errors);self.assertFalse(self.editor.session.dirty)
        finally:app.destroy()


class MoveProperties(unittest.TestCase):
    def test_generated_chains_undo_and_branch_preserve_content(self):
        import random
        from ff11reader.domain import Equipset, Slot, Text, Macro
        from ff11reader.edit_values import SLOT_NAMES
        from ff11reader.editing import EditSession
        from ff11reader.equipment_moves import plan_move
        for seed in range(40):
            with self.subTest(seed=seed):
                rng=random.Random(seed);c=Character('abc')
                slots=tuple(Slot(s,'keep',None,None,None,'00000000') for s in SLOT_NAMES)
                c.equipsets=[Equipset(i,Text('Named' if i==1 else '','','draft'),slots) for i in range(1,21)]
                c.macros=[Macro(1,1,'ctrl',1,Text('Ref','','draft'),tuple(Text('/equipset 1' if n==0 else '','','draft') for n in range(6)))]
                session=EditSession(Snapshot('x','now',[c],{},[],[]));current=1
                for _ in range(8):
                    target=rng.choice([n for n in range(1,21) if n!=current]);session.apply(plan_move(session.character('abc'),current,target));current=target
                    actual=session.character('abc');self.assertEqual(actual.equipsets[current-1].title.display,'Named')
                    from ff11reader.macro_links import parse_reference
                    self.assertEqual(parse_reference(actual.macros[0].lines[0].display),('equipset',current))
                for _ in range(8):session.undo()
                self.assertFalse(session.dirty);self.assertEqual(session.movement_origins('abc'),())
