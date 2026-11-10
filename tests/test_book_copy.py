"""Cross-character copies against synthetic values and isolated game files."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from ff11reader import codecs
from ff11reader.book_copy import plan_book_copy
from ff11reader.domain import InventoryRow, Slot
from ff11reader.edit_application import Editor
from ff11reader.edit_values import value
from ff11reader.elevation import encode, decode
from ff11reader.combined_saving import execute_combined_save, restore_combined_backup
from prototypes.book_copy import snapshot, raw_file


class BookCopyTests(unittest.TestCase):
    def setUp(self):
        self.source = snapshot()
        self.editor = Editor(self.source, 'work/book-copy-tests/draft.json')

    def plan(self):return self.editor.prepare_book_copy('abc', 'def', 1, 1)

    def test_copy_name_sets_tokens_and_atomic_undo(self):
        source, target = self.source.characters
        equipment = source.equipsets[0]
        source.equipsets[0] = replace(equipment, slots=(replace(equipment.slots[0], action='remove'), *equipment.slots[1:]))
        self.editor = Editor(self.source, 'work/book-copy-tests/draft.json')
        original = deepcopy(self.editor.snapshot())
        plan = self.plan()
        self.assertEqual(plan.equipment_numbers, (1,))
        self.editor.copy_book(plan)
        copied = self.editor.snapshot()
        self.assertEqual(copied.characters[0], original.characters[0])
        self.assertEqual(copied.characters[1].books[1], source.books[1])
        self.assertEqual(value(copied.characters[1].equipsets[0]), value(source.equipsets[0]))
        self.assertTrue(self.editor.has_pending_move('def'))
        self.editor.undo();self.assertFalse(self.editor.edit_status()[2])
        self.assertEqual(self.editor.snapshot(), original)
        self.editor.redo();self.assertEqual(self.editor.snapshot(), copied)

    def test_incomplete_book_missing_set_same_character_and_dynamic_reference(self):
        source, target = self.source.characters
        with self.assertRaises(ValueError):plan_book_copy(source, source, 1, 1)
        with self.assertRaises(ValueError):plan_book_copy(source, replace(target, macros=target.macros[:-1]), 1, 1)
        with self.assertRaises(ValueError):plan_book_copy(source, replace(target, equipsets=[]), 1, 1)
        first = source.macros[0]
        source.macros[0] = replace(first, lines=(replace(first.lines[0], display='/equipset 201'), *first.lines[1:]))
        with self.assertRaises(ValueError):plan_book_copy(source, target, 1, 1)

    def test_overwrite_external_references_and_target_inventory(self):
        source, target = self.source.characters
        equipment = source.equipsets[0]
        source.equipsets[0] = replace(equipment, slots=(Slot('main', 'equip', 100, 8, 1, ''), *equipment.slots[1:]))
        source.inventory = [InventoryRow(8, 1, 100)]
        target.inventory_coverage = {n:'loaded' for n in range(17)}
        target.macros[0] = replace(target.macros[0], title=replace(target.macros[0].title, display='Old'))
        target.macros.append(replace(source.macros[0], book=2))
        plan = plan_book_copy(source, target, 1, 1)
        self.assertEqual(plan.overwritten_macros, 1)
        self.assertEqual(len(plan.affected_references), 1)
        self.assertTrue(plan.warnings)
        slot = next(c.after.slots[0] for c in plan.edit.changes if c.kind == 'equipsets')
        self.assertEqual(slot.item_reference.state, 'not_observed')

    def test_stale_preview_rejected_without_changes(self):
        plan = self.plan()
        self.editor.apply(self.editor.prepare_macro_edit('abc', (1,1,'ctrl',1), 'Changed', ['', '', '', '', '', '']))
        before = self.editor.snapshot()
        with self.assertRaisesRegex(ValueError, '変わりました'):self.editor.copy_book(plan)
        self.assertEqual(self.editor.snapshot(), before)

    def test_other_book_self_navigation_tokens_and_shared_set_deduplication(self):
        source, target = self.source.characters
        target.macros = [replace(m, book=21) for m in target.macros]
        target.books = {n+20:t for n,t in target.books.items()}
        first = source.macros[0]
        token_line = codecs.text(b'\xfd\x02\x01\x02\x01\xfd 1 <wait.1>'+b'\0'*39,
                                 lambda payload:'/equipset')
        source.macros[0] = replace(first, lines=(token_line,
            replace(first.lines[1], display='/lockstyleset 001'),
            replace(first.lines[2], display='/macro book 1'),
            replace(first.lines[3], display='/macro book 2'),
            *first.lines[4:]))
        plan = plan_book_copy(source, target, 1, 21)
        copied = next(c.after for c in plan.edit.changes if c.kind == 'macros')
        self.assertEqual(copied.lines[0], token_line)
        self.assertEqual(copied.lines[2].display, '/macro book 21')
        self.assertEqual(copied.lines[3].display, '/macro book 2')
        self.assertEqual(plan.equipment_numbers, (1,))
        self.assertTrue(any('別ブック' in warning for warning in plan.warnings))


class BookSaveTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1]/'work'/'book-save-tests'
        work.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=work);self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base/'game'
        for folder in ('abc', 'def'):
            parent = self.root/'USER'/folder;parent.mkdir(parents=True)
            title = bytearray(raw_file(344))
            title[24:28] = b'Test' if folder == 'abc' else b'Old!'
            title[8:24] = hashlib.md5(title[24:]).digest()
            (parent/'mcr.ttl').write_bytes(title)
            equipment = bytearray(raw_file(1624))
            if folder == 'abc':
                equipment[40] = 2
                equipment[8:24] = hashlib.md5(equipment[24:]).digest()
            (parent/'es0.dat').write_bytes(equipment)
            for page in range(10):
                raw = bytearray(raw_file(7624))
                if folder == 'abc' and page == 0:
                    line = b'/equipset 1';raw[28:28+len(line)] = line
                    raw[89:95] = b'\xfd\x02\x01\x00\x01\xfd'
                    raw[394:398] = b'Main'
                    raw[8:24] = hashlib.md5(raw[24:]).digest()
                (parent/('mcr'+(str(page) if page else '')+'.dat')).write_bytes(raw)
        self.editor = Editor(self.load(), self.base/'draft.json')
        self.original = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for module in ('saving', 'combined_saving', 'macro_saving', 'equipment_saving'):
            handle = patch(f'ff11reader.{module}.require_game_closed');handle.start();self.addCleanup(handle.stop)
        handle = patch('ff11reader.snapshot_loading.load_macro_validation_snapshot', side_effect=lambda *a:self.load())
        handle.start();self.addCleanup(handle.stop)

    def load(self):
        result = snapshot()
        result.sources = []
        for character in result.characters:
            parent = self.root/'USER'/character.folder_id
            character.books = codecs.book_titles((parent/'mcr.ttl').read_bytes())
            character.equipsets = codecs.equipsets((parent/'es0.dat').read_bytes(), 0)
            character.macros = [m for page in range(10) for m in codecs.macros(
                (parent/('mcr'+(str(page) if page else '')+'.dat')).read_bytes(), page)]
            result.sources.extend({'path':str(p.resolve()), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in parent.iterdir())
        return result

    def prepare(self):
        self.editor.copy_book(self.editor.prepare_book_copy('abc', 'def', 1, 1))
        return self.editor.prepare_combined_save('def')

    def test_save_reopen_backup_restore_and_name_only(self):
        plan = self.prepare()
        self.assertEqual(decode(encode(plan)), plan)
        backup = self.editor.save_combined(plan, self.base/'backups')
        self.assertFalse(self.editor.edit_status()[2])
        loaded = self.load()
        self.assertEqual(loaded.characters[1].books[1], loaded.characters[0].books[1])
        self.assertEqual(value(loaded.characters[1].macros[0]), value(loaded.characters[0].macros[0]))
        self.assertEqual(value(loaded.characters[1].equipsets[0]), value(loaded.characters[0].equipsets[0]))
        self.assertEqual(len(plan.files), 3)
        for path, raw in self.original.items():
            if path.parent.name == 'abc':self.assertEqual(path.read_bytes(), raw)
        restore_combined_backup(backup, apply=True)
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)

    def test_name_only_second_title_file_and_undo_after_save(self):
        target = self.root/'USER'/'def'
        (target/'mcr_2.ttl').write_bytes(raw_file(344))
        source = self.load()
        source.characters[1].books.update(codecs.book_titles((target/'mcr_2.ttl').read_bytes(), True))
        source.sources.append({'path':str((target/'mcr_2.ttl').resolve()),
                               'sha256':hashlib.sha256(raw_file(344)).hexdigest()})
        from ff11reader.domain import BookName
        from ff11reader.editing import Change, Edit
        editor = Editor(source, self.base/'name-only.json')
        before = BookName(21, source.characters[1].books[21])
        after = BookName(21, source.characters[0].books[1])
        editor.apply(Edit('book name', (Change('def', 'books', (21,), before, after),), atomic=True))
        plan = editor.prepare_writeback()[0]
        self.assertIsNone(plan.macro);self.assertIsNone(plan.equipment)
        editor.save_combined(plan, self.base/'backups')
        self.assertEqual(codecs.book_titles((target/'mcr_2.ttl').read_bytes(), True)[21].display, 'Test')
        editor.undo()
        editor.save_combined(editor.prepare_writeback()[0], self.base/'backups')
        self.assertEqual((target/'mcr_2.ttl').read_bytes(), raw_file(344))

    def test_failure_rolls_back_macro_and_name(self):
        plan = self.prepare()
        replace_file = os.replace
        def fail(source, destination):
            if Path(destination).name == 'mcr.ttl' and str(source).endswith('.tmp'):
                raise OSError('synthetic failure')
            return replace_file(source, destination)
        with patch('ff11reader.file_transaction.os.replace', side_effect=fail):
            with self.assertRaises(RuntimeError):self.editor.save_combined(plan, self.base/'backups')
        for path, raw in self.original.items():self.assertEqual(path.read_bytes(), raw)
        self.assertTrue(self.editor.edit_status()[2])

    def test_tampered_title_and_external_change_rejected(self):
        plan = self.prepare()
        file = plan.books.files[0]
        bad_file = replace(file, replacement=file.original)
        bad = replace(plan, books=replace(plan.books, files=(bad_file,)))
        with self.assertRaises(ValueError):execute_combined_save(bad, self.base/'backups')
        Path(file.target).write_bytes(raw_file(344))
        with self.assertRaises(ValueError):self.editor.save_combined(plan, self.base/'backups')


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class BookCopyUITests(unittest.TestCase):
    def test_mock_confirmation_cancel_apply_and_worker_boundary(self):
        import gc
        import tkinter as tk
        from threading import get_ident
        from ff11reader.ui import ReaderWindow
        from ff11reader.book_copy_ui import open_book_copy
        from tests.test_ui_tasks import TkThreadGuard
        app = tk.Tk();app.tk = TkThreadGuard(app.tk)
        errors = [];app.report_callback_exception = lambda *e:errors.append(e)
        source = snapshot();editor = Editor(source, 'work/book-copy-ui/draft.json')
        owner = get_ident()
        try:
            view = ReaderWindow(app, source, editor=editor);app.update()
            view.common_menus['編集'].invoke('別キャラへブックをコピー…');app.update()
            window = next(w for w in app.winfo_children() if hasattr(w, 'copy_choices'))
            for choice in window.copy_choices.values():
                self.assertLessEqual(choice.winfo_rootx()+choice.winfo_width(), window.winfo_rootx()+window.winfo_width())
                self.assertLessEqual(choice.winfo_rooty()+choice.winfo_height(), window.winfo_rooty()+window.winfo_height())
            prepare = editor.prepare_book_copy
            def checked(*args):
                self.assertNotEqual(get_ident(), owner)
                return prepare(*args)
            with patch.object(editor, 'prepare_book_copy', side_effect=checked):
                window.preview_copy();app.update()
                confirmation = app.grab_current()
                self.assertIs(app.focus_get(), confirmation.cancel_button)
                confirmation.cancel_button.invoke();app.update()
                self.assertFalse(editor.edit_status()[2])
                window.preview_copy();app.update()
                app.grab_current().accept_button.invoke();app.update()
            self.assertTrue(editor.edit_status()[2])
            view.undo_fix();self.assertFalse(editor.edit_status()[2])
            self.assertFalse(errors)
        finally:
            app.destroy();gc.collect()
