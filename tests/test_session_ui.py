"""EDIT-004: fresh sessions and explicit writeback/discard at exit, synthetic only."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
from threading import get_ident
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ff11reader import dialogs
from ff11reader.edit_application import Editor
from ff11reader.ui_tasks import tasks
from tests.test_equipment_moves import MoveFixture
from tests.test_workspace_ui import WorkspaceMixin


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class SessionUITests(WorkspaceMixin, MoveFixture):
    def open_session(self, two=False):
        if two:
            target = self.folder.parent / 'def'
            shutil.copytree(self.folder, target)
            other = deepcopy(self.source.characters[0]); other.folder_id = 'def'
            self.source.characters.append(other)
            for source in tuple(self.source.sources):
                path = Path(source['path'])
                if path.parent == self.folder.resolve():
                    self.source.sources.append(dict(source, path=str(target / path.name)))
            self.editor = Editor(self.source, self.editor.state_path)
            def load_both(root):
                from ff11reader import codecs
                from ff11reader.saving import digest
                fresh = self.load()
                character = deepcopy(fresh.characters[0]); character.folder_id = 'def'
                character.macros = [m for page in (0, 1) for m in codecs.macros(
                    (target / ('mcr' + (str(page) if page else '') + '.dat')).read_bytes(), page)]
                character.equipsets = [e for page in (0, 1, 2) for e in codecs.equipsets(
                    (target / f'es{page}.dat').read_bytes(), page)]
                fresh.characters.append(character)
                fresh.sources.extend({'path': str(p.resolve()), 'sha256': digest(p.read_bytes())}
                                     for p in target.iterdir())
                return fresh
            reader = patch('ff11reader.application.load_snapshot', side_effect=load_both)
            reader.start(); self.addCleanup(reader.stop)
        view = self.open_view()
        self.game = {p: p.read_bytes() for p in self.folder.parent.rglob('*.dat')}
        return view

    def enter_name(self, title):
        self.view.tabs.select('マクロ'); self.app.update()
        self.begin_name(self.view.macro_panel)
        entry = self.view.macro_panel.entries[0]
        entry.delete(0, 'end'); entry.insert(0, title); self.app.update()

    def test_clean_exit_does_not_ask(self):
        view = self.open_session()
        with patch('ff11reader.ui.dialogs.ask_save_changes') as question, patch.object(self.app, 'destroy') as close:
            view.close(); close.assert_called_once(); question.assert_not_called()

    def test_continue_or_discard_includes_applied_edits_and_pending_input(self):
        view = self.open_session()
        view.run_edit(lambda: self.editor.apply(self.editor.prepare_equipment_name_edit('abc', 1, 'Edited')))
        self.enter_name('Input')
        for choice in (None, 'discard'):
            with patch('ff11reader.ui.dialogs.ask_save_changes', return_value=choice), patch.object(self.app, 'destroy') as close:
                view.close()
                self.assertEqual(close.call_count, int(choice == 'discard'))
            self.assertTrue(self.editor.session.dirty); self.assertTrue(view.macro_panel.has_pending())
            for p, raw in self.game.items(): self.assertEqual(p.read_bytes(), raw)
        self.assertFalse(self.editor.state_path.exists())

    def test_exit_saves_all_characters_and_inputs_then_closes(self):
        view = self.open_session(two=True)
        self.enter_name('First')
        view.character_choice.current(1); view.change_character(); self.app.update()
        self.enter_name('Second')
        write = self.editor.writeback
        owner = get_ident(); seen = []
        def save(plans, root):
            seen.append(get_ident())
            self.assertEqual([p.character for p in plans], ['abc', 'def'])
            return write(plans, self.base / 'backups')
        with patch('ff11reader.ui.dialogs.ask_save_changes', return_value='save'), \
             patch.object(self.editor, 'writeback', side_effect=save), patch.object(self.app, 'destroy') as close:
            view.close(); self.app.update(); close.assert_not_called()
            preview = self.preview_window()
            text = next(w for w in preview.winfo_children() if isinstance(w, tk.Text)).get('1.0', 'end')
            self.assertIn('First', text); self.assertIn('Second', text)
            preview.accept_button.invoke(); self.app.update(); close.assert_called_once()
        self.assertNotEqual(seen, [owner])
        self.assertFalse(self.editor.session.dirty); self.assertFalse(view.macro_panel.has_pending())
        from ff11reader.codecs import macros
        for folder, title in (('abc', 'First'), ('def', 'Second')):
            self.assertEqual(macros((self.folder.parent / folder / 'mcr.dat').read_bytes(), 0)[0].title.display, title)
        self.assertFalse(self.editor.state_path.exists())

    def test_save_failure_does_not_close_and_retry_uses_worker(self):
        view = self.open_session(); self.enter_name('Input')
        owner = get_ident(); ticks = []; threads = []; tick_id = None
        def fail(plans, root):
            threads.append(get_ident()); time.sleep(6.1); raise OSError('synthetic failure')
        def tick():
            nonlocal tick_id
            if tasks(self.app).running:
                ticks.append(1); view.save_button.invoke(); view.close()
                tick_id = self.app.after(500, tick)
        with patch('ff11reader.ui.dialogs.ask_save_changes', return_value='save'), patch.object(self.app, 'destroy') as close:
            view.close(); preview = self.preview_window()
            tick_id = self.app.after(100, tick)
            try:
                with patch.object(self.editor, 'writeback', side_effect=fail), patch('ff11reader.ui.dialogs.showerror') as error:
                    preview.accept_button.invoke(); self.app.update()
            finally:
                self.app.after_cancel(tick_id)
            error.assert_called_once(); close.assert_not_called()
        self.assertEqual(len(threads), 1); self.assertNotEqual(threads[0], owner)
        self.assertGreaterEqual(len(ticks), 6)
        self.assertTrue(self.editor.session.dirty); self.assertIsNone(self.app.grab_current())
        self.assertEqual(view.macro_panel.entries[0].get(), 'Input')
        for p, raw in self.game.items(): self.assertEqual(p.read_bytes(), raw)
        write = self.editor.writeback
        with patch.object(self.editor, 'writeback', side_effect=lambda plans, root: write(plans, self.base / 'backups')):
            view.save_button.invoke(); self.preview_window().accept_button.invoke(); self.app.update()
        self.assertFalse(self.editor.session.dirty)

    def test_partial_character_save_keeps_remaining_edit_open(self):
        view = self.open_session(two=True)
        self.enter_name('First'); view.character_choice.current(1); view.change_character(); self.enter_name('Second')
        original = self.editor.save_combined
        def save(plan, root):
            if plan.character == 'def': raise OSError('second character failed')
            return original(plan, self.base / 'backups')
        with patch('ff11reader.ui.dialogs.ask_save_changes', return_value='save'), patch.object(self.app, 'destroy') as close:
            view.close()
            with patch.object(self.editor, 'save_combined', side_effect=save), patch('ff11reader.ui.dialogs.showerror'):
                self.preview_window().accept_button.invoke(); self.app.update()
            close.assert_not_called()
        self.assertTrue(self.editor.session.dirty)
        self.assertEqual([p.character for p in self.editor.prepare_writeback()], ['def'])
        self.assertEqual(self.editor.snapshot().characters[1].macros[0].title.display, 'Second')

    def test_invalid_input_and_cancelled_preview_keep_window_and_edit(self):
        view = self.open_session(); self.enter_name('名前が長すぎるマクロ名')
        with patch('ff11reader.ui.dialogs.ask_save_changes', return_value='save'), patch.object(self.app, 'destroy') as close, \
             patch('ff11reader.ui.dialogs.showerror') as error:
            view.close(); error.assert_called_once(); close.assert_not_called()
        self.assertTrue(view.macro_panel.has_pending() or self.editor.session.dirty)
        self.assertEqual(view.macro_panel.entries[0].get(), '名前が長すぎるマクロ名')
        self.enter_name('Valid')
        with patch('ff11reader.ui.dialogs.ask_save_changes', return_value='save'), patch.object(self.app, 'destroy') as close:
            view.close(); self.preview_window().cancel_button.invoke(); self.app.update(); close.assert_not_called()
        self.assertTrue(self.editor.session.dirty)
        for p, raw in self.game.items(): self.assertEqual(p.read_bytes(), raw)

    def test_exit_dialog_buttons_and_escape_keep_editing(self):
        self.open_session()
        observed = []
        def inspect():
            layer = self.app.grab_current()
            def buttons(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button): yield child
                    yield from buttons(child)
            found = {b.cget('text'): b for b in buttons(layer)}
            observed.extend(found)
            self.assertIs(self.app.focus_get(), found['編集を続ける'])
            for b in found.values():
                self.assertLessEqual(b.winfo_rootx() + b.winfo_width(), self.app.winfo_rootx() + self.app.winfo_width())
            layer.event_generate('<Escape>')
        self.app.after(100, inspect)
        self.assertIsNone(dialogs.ask_save_changes(parent=self.app))
        self.assertTrue({'書き戻して終了', '破棄して終了', '編集を続ける'}.issubset(observed))
