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
    def test_palette_overwrite_is_explicit_atomic_and_reversible(self):
        from ff11reader.domain import Snapshot
        from ff11reader.transfer_editing import MacroOverwriteRequired
        for cut in (False,True):
            c=self.character()
            c.macros[20]=replace(c.macros[20],title=text('Old destination'))
            original=deepcopy(c)
            transfer=capture(c,'palette',((1,1),),cut)
            with self.assertRaises(MacroOverwriteRequired):plan_paste(c,transfer,(1,2))
            edit=plan_paste(c,transfer,(1,2),overwrite=True)
            session=EditSession(Snapshot('synthetic','',[c],{},[],[]));session.apply(edit)
            self.assertEqual(session.character('a').macros[20].title.display,'Source')
            session.undo();self.assertEqual(session.character('a'),original)
            session.redo();self.assertEqual(session.character('a').macros[20].title.display,'Source')
            c.macros.pop()
            with self.assertRaisesRegex(ValueError,'読込不足'):
                plan_paste(c,transfer,(2,3),overwrite=True)

    def test_macro_overwrite_is_explicit_atomic_and_reversible(self):
        from ff11reader.domain import Snapshot
        from ff11reader.transfer_editing import MacroOverwriteRequired
        for cut in (False,True):
            c=self.character()
            c.macros[20]=replace(c.macros[20],title=text('Old destination'))
            original=deepcopy(c)
            transfer=capture(c,'macro',((1,1,'ctrl',1),),cut)
            with self.assertRaises(MacroOverwriteRequired):plan_paste(c,transfer,(1,2,'ctrl',1))
            edit=plan_paste(c,transfer,(1,2,'ctrl',1),overwrite=True)
            session=EditSession(Snapshot('synthetic','',[c],{},[],[]));session.apply(edit)
            self.assertEqual(session.character('a').macros[20].title.display,'Source')
            session.undo();self.assertEqual(session.character('a'),original)
            session.redo();self.assertEqual(session.character('a').macros[20].title.display,'Source')
            c.macros.pop()
            with self.assertRaisesRegex(ValueError,'読込不足'):
                plan_paste(c,transfer,(2,3,'alt',10),overwrite=True)

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
                plan_paste(c,capture(c,'equipment',((10,),)),(13,),overwrite=True)

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
    def test_token_copy_save_matrix(self):
        from ff11reader import codecs
        from ff11reader.edit_application import Editor
        from tests.test_saving import checksum
        known=bytes.fromhex('fd02010201fd')
        unknown=bytes.fromhex('fd00000001fd')
        load_original=self.load
        names={0x201:'/equipset',0x301:'/equipset'}
        def load():
            snapshot=load_original()
            snapshot.characters[0].macros=[]
            for page in (0,1):
                path=self.folder/('mcr'+(str(page) if page else '')+'.dat')
                snapshot.characters[0].macros.extend(codecs.macros(path.read_bytes(),page,
                    lambda p:'/equipset' if p in (bytes.fromhex('02010201'),bytes.fromhex('02010301')) else None))
            snapshot.phrases=names
            return snapshot
        self.load=load
        with patch('ff11reader.adapters.LocalReader.load_phrases',return_value=names):
            from itertools import product
            for token,kind,overwrite,cut,edit_before in product((known,unknown),('macro','palette'),(False,True),(False,True),(False,True)):
                with self.subTest(token=token.hex(),kind=kind,overwrite=overwrite,cut=cut,edit_before=edit_before):
                    for filename,raw in self.original.items():filename.write_bytes(raw)
                    path=self.folder/'mcr.dat';raw=bytearray(path.read_bytes())
                    raw[28:89]=(b'/echo '+token+b' <t>').ljust(61,b'\0')
                    path.write_bytes(checksum(raw))
                    target_path=self.folder/'mcr1.dat';raw=bytearray(target_path.read_bytes())
                    if not overwrite:raw[24:7624]=bytes(7600)
                    else:raw[28:89]=(b'/echo '+bytes.fromhex('fd02010301fd')+b' <t>').ljust(61,b'\0')
                    target_path.write_bytes(checksum(raw))
                    self.editor=Editor(load(),self.base/'draft.json')
                    source=((1,1),) if kind=='palette' else ((1,1,'ctrl',1),)
                    target=(1,2) if kind=='palette' else (1,2,'ctrl',1)
                    if edit_before:
                        original=self.editor.snapshot().characters[0].macros[0]
                        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Edited',list(original.lines)))
                    self.editor.capture_transfer('abc',kind,source,cut)
                    edit=self.editor.prepare_paste('abc',target,overwrite=overwrite)
                    self.editor.paste('abc',target,edit,overwrite=overwrite)
                    plan=self.editor.prepare_combined_save('abc')
                    self.editor.save_combined(plan,self.base/'backups')
                    macro=next(m for m in load().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
                    self.assertIn(token,bytes.fromhex(macro.lines[0].raw_hex))
                    lines=list(macro.lines);lines[0]=lines[0].display+' test'
                    # Existing IDs survive a subsequent edit and second save.
                    from ff11reader.text_editing import remap_text
                    lines[0]=remap_text(macro.lines[0],lines[0])
                    self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),macro.title.display,lines))
                    self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'backups')


    def test_unsaved_inserted_or_replaced_token_copy_save_matrix(self):
        from ff11reader import codecs
        from ff11reader.edit_application import Editor
        from tests.test_saving import checksum
        known=bytes.fromhex('fd02010201fd')
        unknown=bytes.fromhex('fd00000001fd')
        load_original=self.load
        names={0x201:'/equipset',0x301:'/equipset'}
        def load():
            snapshot=load_original()
            snapshot.characters[0].macros=[]
            for page in (0,1):
                path=self.folder/('mcr'+(str(page) if page else '')+'.dat')
                snapshot.characters[0].macros.extend(codecs.macros(path.read_bytes(),page,
                    lambda p:'/equipset' if p in (bytes.fromhex('02010201'),bytes.fromhex('02010301')) else None))
            snapshot.phrases=names
            return snapshot
        self.load=load
        with patch('ff11reader.adapters.LocalReader.load_phrases',return_value=names):
            from itertools import product
            for kind,overwrite,cut,mode in product(('macro','palette'),(False,True),(False,True),('insert','replace')):
                token=known
                with self.subTest(kind=kind,overwrite=overwrite,cut=cut,mode=mode):
                    for filename,raw in self.original.items():filename.write_bytes(raw)
                    path=self.folder/'mcr.dat';raw=bytearray(path.read_bytes())
                    raw[28:89]=(b'/echo '+token+b' <t>').ljust(61,b'\0')
                    path.write_bytes(checksum(raw))
                    target_path=self.folder/'mcr1.dat';raw=bytearray(target_path.read_bytes())
                    if not overwrite:raw[24:7624]=bytes(7600)
                    else:raw[28:89]=(b'/echo '+bytes.fromhex('fd02010301fd')+b' <t>').ljust(61,b'\0')
                    target_path.write_bytes(checksum(raw))
                    self.editor=Editor(load(),self.base/'draft.json')
                    source=((1,1),) if kind=='palette' else ((1,1,'ctrl',1),)
                    target=(1,2) if kind=='palette' else (1,2,'ctrl',1)
                    from ff11reader.text_editing import replace_range
                    original=self.editor.snapshot().characters[0].macros[0]
                    line=original.lines[0]
                    start,end=(len(line.display),len(line.display)) if mode=='insert' else (line.tokens[0].start,line.tokens[0].end)
                    changed=replace_range(line,start,end,'【/equipset】','02010301')
                    lines=list(original.lines);lines[0]=changed
                    self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),original.title.display,lines))
                    # The new token exists only in edit state, not in the game file.
                    self.assertNotIn(bytes.fromhex('fd02010301fd'),(self.folder/'mcr.dat').read_bytes())
                    expected=changed.tokens
                    self.editor.capture_transfer('abc',kind,source,cut)
                    edit=self.editor.prepare_paste('abc',target,overwrite=overwrite)
                    self.editor.paste('abc',target,edit,overwrite=overwrite)
                    plan=self.editor.prepare_combined_save('abc')
                    self.editor.save_combined(plan,self.base/'backups')
                    macro=next(m for m in load().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
                    self.assertEqual(macro.lines[0].tokens,expected)
                    self.assertIn(bytes.fromhex('fd02010301fd'),bytes.fromhex(macro.lines[0].raw_hex))
                    lines=list(macro.lines);lines[0]=lines[0].display+' test'
                    # Existing IDs survive a subsequent edit and second save.
                    from ff11reader.text_editing import remap_text
                    lines[0]=remap_text(macro.lines[0],lines[0])
                    self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),macro.title.display,lines))
                    self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'backups')


    def test_reported_japanese_phrases_unsaved_copy_save(self):
        from ff11reader import codecs
        from ff11reader.edit_application import Editor
        from tests.test_saving import checksum
        known=bytes.fromhex('fd02011b70fd')
        unknown=bytes.fromhex('fd00000001fd')
        load_original=self.load
        names={0x201:'/equipset',0x1B70:'イレース',0x1BC0:'オーラ',0x1FAB:'簡素清貧の章'}
        def load():
            snapshot=load_original()
            snapshot.characters[0].macros=[]
            for page in (0,1):
                path=self.folder/('mcr'+(str(page) if page else '')+'.dat')
                snapshot.characters[0].macros.extend(codecs.macros(path.read_bytes(),page,
                    lambda p:names.get(int.from_bytes(p[2:],'big')) if p[:2]==b'\x02\x01' else None))
            snapshot.phrases=names
            return snapshot
        self.load=load
        with patch('ff11reader.adapters.LocalReader.load_phrases',return_value=names):
            from itertools import product
            for kind,overwrite,cut,mode in product(('macro','palette'),(False,True),(False,True),('insert','replace')):
                token=known
                with self.subTest(kind=kind,overwrite=overwrite,cut=cut,mode=mode):
                    for filename,raw in self.original.items():filename.write_bytes(raw)
                    path=self.folder/'mcr.dat';raw=bytearray(path.read_bytes())
                    raw[28:89]=(b'/echo '+token+b' <t>').ljust(61,b'\0')
                    path.write_bytes(checksum(raw))
                    target_path=self.folder/'mcr1.dat';raw=bytearray(target_path.read_bytes())
                    if not overwrite:raw[24:7624]=bytes(7600)
                    else:raw[28:89]=(b'/echo '+bytes.fromhex('fd02011bc0fd')+b' <t>').ljust(61,b'\0')
                    target_path.write_bytes(checksum(raw))
                    self.editor=Editor(load(),self.base/'draft.json')
                    source=((1,1),) if kind=='palette' else ((1,1,'ctrl',1),)
                    target=(1,2) if kind=='palette' else (1,2,'ctrl',1)
                    from ff11reader.text_editing import replace_range
                    original=self.editor.snapshot().characters[0].macros[0]
                    line=original.lines[0]
                    start,end=(len(line.display),len(line.display)) if mode=='insert' else (line.tokens[0].start,line.tokens[0].end)
                    changed=replace_range(line,start,end,'【簡素清貧の章】','02011FAB')
                    lines=list(original.lines);lines[0]=changed
                    self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),original.title.display,lines))
                    # The new token exists only in edit state, not in the game file.
                    self.assertNotIn(bytes.fromhex('fd02011fabfd'),(self.folder/'mcr.dat').read_bytes())
                    expected=changed.tokens
                    self.editor.capture_transfer('abc',kind,source,cut)
                    edit=self.editor.prepare_paste('abc',target,overwrite=overwrite)
                    self.editor.paste('abc',target,edit,overwrite=overwrite)
                    plan=self.editor.prepare_combined_save('abc')
                    self.editor.save_combined(plan,self.base/'backups')
                    macro=next(m for m in load().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
                    self.assertEqual(macro.lines[0].tokens,expected)
                    self.assertIn(bytes.fromhex('fd02011fabfd'),bytes.fromhex(macro.lines[0].raw_hex))
                    lines=list(macro.lines);lines[0]=lines[0].display+' test'
                    # Existing IDs survive a subsequent edit and second save.
                    from ff11reader.text_editing import remap_text
                    lines[0]=remap_text(macro.lines[0],lines[0])
                    self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),macro.title.display,lines))
                    self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'backups')


    def test_unchanged_copied_token_macro_does_not_change_save_dependencies(self):
        from ff11reader import macro_saving
        source=deepcopy(self.source)
        resource=self.base/'game'/'dictionary.dat';resource.write_bytes(b'synthetic dictionary')
        from ff11reader.saving import digest
        source.sources.append(dict(path=str(resource.resolve()),sha256=digest(resource.read_bytes())))
        working=deepcopy(source)
        original=working.characters[0].macros[0]
        raw=bytearray.fromhex(original.raw_hex);raw[0]^=1
        working.characters[0].macros[0]=replace(original,raw_hex=raw.hex())
        other=working.characters[0].macros[1]
        working.characters[0].macros[1]=replace(other,title=text('Changed'))
        plan=macro_saving.prepare_macro_save(source,working,'abc','all')
        with patch('ff11reader.application.load_snapshot',return_value=source):
            _,validate=macro_saving.validate_macro_plan(plan)
            validate({})
        self.assertNotIn(str(resource.resolve()),dict(plan.dependencies))


    def test_overwrite_different_named_palette_save_and_undo(self):
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'alt',8),'Source',['/echo source']+['']*5))
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'alt',8),'Target',['/echo target']+['']*5))
        self.editor.capture_transfer('abc','palette',((1,1),))
        edit=self.editor.prepare_paste('abc',(1,2),overwrite=True)
        self.editor.paste('abc',(1,2),edit,overwrite=True)
        plan=self.editor.prepare_combined_save('abc')
        self.editor.save_combined(plan,self.base/'backups')
        self.editor.undo()
        self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'undo-backups')


    def test_legacy_draft_reconstructs_record_and_partial_save_is_blocked(self):
        import json
        from ff11reader.edit_application import Editor
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Renamed',
            [t.display for t in self.source.characters[0].macros[0].lines]))
        path=self.base/'draft.json';path.write_text('legacy draft',encoding='utf-8')
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
        # In-session Undo retains the original destination record, including its prefix.
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
    def test_palette_overwrite_immediate_apply_and_stale(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),'Old',['/echo old']+['']*5))
        app=tk.Tk()
        try:
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            view.commands.select('palette',(1,1));view.commands.run('copy')
            view.commands.select('palette',(1,2))
            before=self.editor.edit_status()
            view.commands.run('paste');app.update()
            self.assertIsNone(app.grab_current())
            self.assertEqual(self.editor.edit_status()[0],before[0]+1)
            self.editor.undo()
            target=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            self.assertEqual(target.title.display,'Old')
            edit=self.editor.prepare_paste('abc',(1,2),overwrite=True)
            self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),'Changed',['']*6))
            with self.assertRaises(ValueError):self.editor.paste('abc',(1,2),edit,overwrite=True)
        finally:app.destroy()

    def test_macro_overwrite_immediate_apply_and_stale(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),'Old',['/echo old']+['']*5))
        app=tk.Tk()
        try:
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            view.commands.select('macro',(1,1,'ctrl',1));view.commands.run('copy')
            view.commands.select('macro',(1,2,'ctrl',1))
            before=self.editor.edit_status()
            view.commands.run('paste');app.update()
            self.assertIsNone(app.grab_current())
            self.assertEqual(self.editor.edit_status()[0],before[0]+1)
            self.editor.undo()
            target=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            self.assertEqual(target.title.display,'Old')
            edit=self.editor.prepare_paste('abc',(1,2,'ctrl',1),overwrite=True)
            self.editor.apply(self.editor.prepare_macro_edit('abc',(1,2,'ctrl',1),'Changed',['']*6))
            with self.assertRaises(ValueError):self.editor.paste('abc',(1,2,'ctrl',1),edit,overwrite=True)
        finally:app.destroy()

    def test_palette_mouse_selection_and_keyboard_copy_paste(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Unique',['/echo source']+['']*5))
        app=tk.Tk();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
        try:
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            tree=view.macro_tree
            def click(number):
                item=f'palette-1-{number}'
                tree.see(item);app.update()
                x,y,w,h=tree.bbox(item)
                tree.event_generate('<Button-1>',x=x+40,y=y+h//2)
                tree.event_generate('<ButtonRelease-1>',x=x+40,y=y+h//2)
                app.update()
            click(1);tree.focus_force();app.update()
            tree.event_generate('<Control-c>');app.update()
            self.assertIsNotNone(self.editor.transfer)
            self.assertEqual(self.editor.transfer.kind,'palette')
            click(2)
            self.assertEqual(view.commands.selection,{(1,2)})
            self.assertEqual(app.focus_get(),tree)
            tree.event_generate('<Control-v>');app.update()
            preview=app.grab_current()
            if preview:preview.accept_button.invoke();app.update()
            target=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            self.assertEqual(target.title.display,'Unique')
            self.assertFalse(errors,errors)
        finally:app.destroy()

    def test_palette_restored_selection_and_keyboard_copy_paste(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Unique',['/echo source']+['']*5))
        app=tk.Tk();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
        try:
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            tree=view.macro_tree
            def click(number):
                item=f'palette-1-{number}'
                tree.selection_set(item);tree.focus(item);tree.see(item);app.update()
            click(1);tree.focus_force();app.update()
            tree.event_generate('<Control-c>');app.update()
            self.assertIsNotNone(self.editor.transfer)
            self.assertEqual(self.editor.transfer.kind,'palette')
            click(2)
            self.assertEqual(app.focus_get(),tree)
            tree.event_generate('<Control-v>');app.update()
            preview=app.grab_current()
            if preview:preview.accept_button.invoke();app.update()
            target=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            self.assertEqual(target.title.display,'Unique')
            self.assertFalse(errors,errors)
        finally:app.destroy()

    def test_palette_context_menu_copy_paste(self):
        import tkinter as tk
        from ff11reader.ui import ReaderWindow
        self.editor.apply(self.editor.prepare_macro_edit('abc',(1,1,'ctrl',1),'Unique',['/echo source']+['']*5))
        app=tk.Tk();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
        try:
            view=ReaderWindow(app,self.editor.snapshot(),editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            tree=view.macro_tree
            popup=patch.object(view.commands.menu,'tk_popup');popup.start();self.addCleanup(popup.stop)
            def click(number):
                item=f'palette-1-{number}'
                tree.see(item);app.update()
                x,y,w,h=tree.bbox(item)
                tree.event_generate('<Button-1>',x=x+40,y=y+h//2)
                tree.event_generate('<ButtonRelease-1>',x=x+40,y=y+h//2)
                app.update()
            click(1);tree.focus_force();app.update()
            x,y,w,h=tree.bbox('palette-1-1')
            view.commands.context(SimpleNamespace(widget=tree,y=y+h//2,x_root=tree.winfo_rootx()+40,y_root=tree.winfo_rooty()+y),('palette',(1,1)))
            view.commands.menu.invoke(1);view.commands.menu.unpost();app.update()
            self.assertIsNotNone(self.editor.transfer)
            self.assertEqual(self.editor.transfer.kind,'palette')
            click(2)
            self.assertEqual(view.commands.selection,{(1,2)})
            self.assertEqual(app.focus_get(),tree)
            x,y,w,h=tree.bbox('palette-1-2')
            view.commands.context(SimpleNamespace(widget=tree,y=y+h//2,x_root=tree.winfo_rootx()+40,y_root=tree.winfo_rooty()+y),('palette',(1,2)))
            view.commands.menu.invoke(2);view.commands.menu.unpost();app.update()
            preview=app.grab_current()
            if preview:preview.accept_button.invoke();app.update()
            target=next(m for m in self.editor.snapshot().characters[0].macros if (m.book,m.palette,m.bank,m.key)==(1,2,'ctrl',1))
            self.assertEqual(target.title.display,'Unique')
            self.assertFalse(errors,errors)
        finally:app.destroy()

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
            self.assertIsNone(app.grab_current())
            self.assertTrue(self.editor.session.dirty)
            target=view.commands.cards[(1,1,'alt',5)]
            self.assertEqual(app.focus_get(),target)
            target.event_generate('<Control-z>');app.update();self.assertFalse(self.editor.session.dirty)
            self.assertEqual(app.focus_get(),view.commands.cards[(1,1,'alt',5)])
            input_window=tk.Toplevel(app);entry=tk.Entry(input_window);entry.pack();entry.insert(0,'sample');app.update()
            entry.focus_force();app.update();entry.selection_range(0,'end');entry.event_generate('<Delete>');app.update()
            self.assertEqual(entry.get(),'');self.assertFalse(self.editor.session.dirty)
        finally:app.destroy()

    def test_select_copy_immediate_paste_undo_delete_and_common_save_button(self):
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
            self.assertIsNone(app.grab_current())
            self.assertTrue(self.editor.session.dirty)
            cmd.run('undo');self.assertFalse(self.editor.session.dirty)
            cmd.run('redo');self.assertTrue(self.editor.session.dirty)
            cmd.select('macro',(1,1,'alt',5));cmd.run('cut');self.assertTrue(self.editor.transfer.cut)
            cmd.run('cancel');self.assertIsNone(self.editor.transfer)
            before_delete=self.editor.snapshot()
            cmd.run('delete');app.update()
            self.assertIsNone(app.grab_current())
            cmd.run('undo');app.update()
            self.assertEqual(self.editor.snapshot().characters,before_delete.characters)
            cmd.select('palette',(1,1));cmd.select('palette',(1,2),shift=True)
            self.assertEqual(len(cmd.selection),2)
            self.editor.apply(self.editor.prepare_equipment_name_edit('abc',1,'New'));view.refresh_edits()
            view.save_button.invoke();app.update()
            self.assertTrue(any('ゲームへ書き戻す' in w.title() for w in app.winfo_children() if isinstance(w,tk.Toplevel)))
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
