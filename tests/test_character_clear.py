"""Character clear acceptance tests using isolated synthetic data only."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import os
import hashlib
import unittest
from unittest.mock import patch

from ff11reader import codecs
from ff11reader.character_clear import plan_character_clear
from ff11reader.domain import InventoryRow
from ff11reader.edit_application import Editor
from ff11reader.edit_values import value
from prototypes.book_copy import snapshot, raw_file
from tests import test_book_copy


class CharacterClearTests(unittest.TestCase):
    def test_all_40_books_8000_macros_200_sets_and_atomic_undo(self):
        source = snapshot()
        character = source.characters[0]
        macro, equipment = character.macros[0], character.equipsets[0]
        character.macros = [replace(macro, book=b, palette=p, bank=bank, key=k)
                            for b in range(1,41) for p in range(1,11)
                            for bank in ('ctrl','alt') for k in range(1,11)]
        character.books = {n:character.books[1] for n in range(1,41)}
        character.equipsets = [replace(equipment, number=n, title=character.books[1],
            slots=(replace(equipment.slots[0], action='remove'), *equipment.slots[1:])) for n in range(1,201)]
        character.inventory = [InventoryRow(8,1,123)]
        editor = Editor(source, 'work/clear-tests/draft.json')
        original = editor.snapshot()
        preview = editor.prepare_character_clear('abc')
        self.assertEqual(len(preview.changes), 8240)
        editor.clear_character('abc', preview)
        cleared = editor.snapshot()
        self.assertTrue(all(not m.title.display and all(not t.display and not t.tokens for t in m.lines)
                            for m in cleared.characters[0].macros))
        self.assertTrue(all(not t.display for t in cleared.characters[0].books.values()))
        self.assertTrue(all(not e.title.display and all(s.action=='keep' for s in e.slots)
                            for e in cleared.characters[0].equipsets))
        self.assertEqual(cleared.characters[0].inventory, character.inventory)
        self.assertEqual(cleared.characters[1], original.characters[1])
        self.assertEqual(editor.edit_status()[:2], (1,1))
        self.assertTrue(editor.has_pending_move('abc'))
        editor.undo();self.assertEqual(editor.snapshot(), original)
        editor.redo();self.assertEqual(editor.snapshot(), cleared)
        editor.clear_character('abc', editor.prepare_character_clear('abc'))
        self.assertEqual(editor.edit_status()[:2], (1,1))

    def test_stale_plan_unreadable_file_and_bad_structure_preserve_state(self):
        source = snapshot();editor = Editor(source, 'work/clear-tests/stale.json')
        preview = editor.prepare_character_clear('abc')
        editor.apply(editor.prepare_macro_edit('abc', (1,1,'ctrl',1), 'changed', ['']*6))
        before = editor.snapshot()
        with self.assertRaisesRegex(ValueError, '変わりました'):
            editor.clear_character('abc', preview)
        self.assertEqual(editor.snapshot(), before)
        source.diagnostics = [{'path':str(Path('game/USER/abc/mcr1.dat')), 'code':'source_unreadable'}]
        editor = Editor(source, 'work/clear-tests/error.json')
        with self.assertRaisesRegex(ValueError, '読み取れていません'):
            editor.prepare_character_clear('abc')
        self.assertFalse(editor.edit_status()[2])
        broken = deepcopy(source.characters[0]);broken.macros[0] = replace(broken.macros[0], lines=())
        with self.assertRaises(ValueError):plan_character_clear(broken)


class CharacterClearSaveTests(unittest.TestCase):
    setUp = test_book_copy.BookSaveTests.setUp
    load = test_book_copy.BookSaveTests.load

    def test_second_book_title_file_and_other_settings_are_preserved(self):
        parent=self.root/'USER'/'abc'
        raw=bytearray(raw_file(344));raw[24:28]=b'Last'
        raw[8:24]=hashlib.md5(raw[24:]).digest()
        path=parent/'mcr_2.ttl';path.write_bytes(raw)
        settings=parent/'settings.bin';settings.write_bytes(b'keep character settings')
        source=self.load()
        source.characters[0].books.update(codecs.book_titles(bytes(raw),True))
        editor=Editor(source,self.base/'second-title.json')
        editor.clear_character('abc',editor.prepare_character_clear('abc'))
        editor.save_combined(editor.prepare_writeback()[0],self.base/'backups')
        self.assertFalse(codecs.book_titles(path.read_bytes(),True)[21].display)
        self.assertEqual(path.read_bytes()[25:],bytes(raw)[25:])
        self.assertEqual(settings.read_bytes(),b'keep character settings')
        editor.undo()
        editor.save_combined(editor.prepare_writeback()[0],self.base/'undo-backups')
        self.assertEqual(path.read_bytes(),bytes(raw))

    def test_save_reload_backup_undo_and_restore(self):
        from ff11reader.combined_saving import restore_combined_backup
        before = self.editor.snapshot()
        self.editor.clear_character('abc', self.editor.prepare_character_clear('abc'))
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)
        plan = self.editor.prepare_writeback()[0]
        self.assertEqual({Path(f.target).suffix for f in plan.files}, {'.dat','.ttl'})
        backup = self.editor.save_combined(plan, self.base/'backups')
        loaded = self.load().characters[0]
        self.assertTrue(all(not t.display for t in loaded.books.values()))
        self.assertTrue(all(not m.title.display and all(not t.display for t in m.lines) for m in loaded.macros))
        self.assertTrue(all(not e.title.display and all(s.action=='keep' for s in e.slots) for e in loaded.equipsets))
        for path, raw in self.original.items():
            if path.parent.name=='def':self.assertEqual(path.read_bytes(), raw)
        self.editor.undo()
        self.assertEqual([value(m) for m in self.editor.snapshot().characters[0].macros],
                         [value(m) for m in before.characters[0].macros])
        self.editor.save_combined(self.editor.prepare_writeback()[0], self.base/'undo-backups')
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)
        restore_combined_backup(backup, apply=True)
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)

    def test_write_failure_restores_all_files_and_keeps_edit(self):
        self.editor.clear_character('abc', self.editor.prepare_character_clear('abc'))
        plan = self.editor.prepare_writeback()[0]
        replace_file = os.replace
        def fail(source, destination):
            if Path(destination).name=='mcr.ttl' and str(source).endswith('.tmp'):
                raise OSError('synthetic clear failure')
            return replace_file(source, destination)
        with patch('ff11reader.file_transaction.os.replace', side_effect=fail):
            with self.assertRaises(RuntimeError):self.editor.save_combined(plan, self.base/'backups')
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)
        self.assertTrue(self.editor.edit_status()[2])


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1', 'Synthetic Tk checks')
class CharacterClearUITests(unittest.TestCase):
    def test_confirm_cancel_pending_undo_and_worker(self):
        import gc
        import tkinter as tk
        from threading import get_ident
        from ff11reader.ui import ReaderWindow
        from ff11reader import dialogs
        from tests.test_ui_tasks import TkThreadGuard
        app = tk.Tk();app.tk = TkThreadGuard(app.tk)
        errors=[];app.report_callback_exception=lambda *e:errors.append(e)
        editor=Editor(snapshot(), 'work/clear-ui/draft.json')
        owner=get_ident()
        try:
            view=ReaderWindow(app, editor.snapshot(), editor=editor);app.update()
            before=editor.snapshot()
            a,b=before.characters
            for c in (a,b):
                m=c.macros[0]
                view.macro_panel.pending[(c.folder_id,(1,1,'ctrl',1))]=(m,'Pending',m.lines)
            pending=deepcopy(view.macro_panel.pending)
            prepare=editor.prepare_character_clear
            def checked(*args):
                self.assertNotEqual(get_ident(),owner)
                return prepare(*args)
            def cancel(modal):
                app.update()
                self.assertIs(app.focus_get(),modal.cancel_button)
                self.assertIn('[abc]',modal.message)
                self.assertIn('全40ブック',modal.message)
                self.assertIn('全200件',modal.message)
                modal.layout();app.update()
                for button in (modal.ok_button,modal.cancel_button):
                    self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),
                                         app.winfo_rooty()+app.winfo_height())
                modal.cancel_button.invoke()
                return False
            with patch.object(dialogs.Modal,'wait',cancel):
                view.common_menus['編集'].invoke('現在のキャラのマクロ・装備セットを全消去…')
            self.assertEqual(editor.snapshot(),before)
            self.assertEqual(editor.edit_status()[:2],(0,0))
            self.assertEqual(view.macro_panel.pending,pending)
            # Pending inputs for this character are restored by one Undo;
            # another character's pending inputs remain outside the operation.
            def accept(modal):modal.ok_button.invoke();return True
            with patch.object(editor,'prepare_character_clear',side_effect=checked), patch.object(dialogs.Modal,'wait',accept):
                view.clear_character_data()
            self.assertIn(('def',(1,1,'ctrl',1)),view.macro_panel.pending)
            self.assertFalse(editor.snapshot().characters[0].macros[0].title.display)
            view.undo_fix()
            self.assertEqual(editor.snapshot().characters[0].macros[0].title.display,'Pending')
            self.assertFalse(errors)
        finally:app.destroy();gc.collect()
