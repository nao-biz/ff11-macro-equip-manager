"""Inline macro input; publication and persistence remain in Editor."""
import tkinter as tk
from tkinter import ttk
from . import dialogs
from .edit_values import text_value, value
from .editing import Edit, macro_key
from .phrase_ui import PhraseEntry
from .phrases import PhraseCatalog
from .theme import PANEL, FG, MUTED, BORDER, SELECT
from .ui_actions import ActionButton
from .ui_tasks import background


class MacroPanel:
    def __init__(self, parent, view):
        self.view = view
        self.frame = ttk.Frame(parent, padding=(4, 8, 4, 0))
        self.pending = {}
        self.identity = None
        self.macro = None
        self.catalog = None
        self.catalog_source = None
        self.controllers = []
        self.entries = []
        self.variables = []
        self.loading = False
        self.status_job = None
        self.frame.bind('<Destroy>',self.cancel_status)
        self.active_line = 0
        self.address = ttk.Label(self.frame, style='Muted.TLabel')
        self.address.pack(anchor='w', pady=(0, 8))
        for i in range(7):
            row = tk.Frame(self.frame, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill='x', pady=(0, 8) if i == 0 else 0)
            tk.Label(row, text='名前' if i == 0 else str(i), bg=PANEL, fg=MUTED, width=5).pack(side='left')
            entry = tk.Entry(row, bg=PANEL, fg=FG, insertbackground=FG, selectbackground=SELECT,
                             relief='flat', font=('Yu Gothic UI', 11))
            entry.pack(side='left', fill='x', expand=True, padx=8, pady=4)
            variable=tk.StringVar(master=entry)
            entry.configure(textvariable=variable)
            variable.trace_add('write',self.input_changed)
            self.variables.append(variable)
            if i:
                entry.bind('<Up>', lambda e, n=i: self.move_line(n, -1))
                entry.bind('<Down>', lambda e, n=i: self.move_line(n, 1))
                entry.bind('<FocusIn>', lambda e, n=i: self.focus_line(n))
            self.entries.append(entry)
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill='x', pady=6)
        ttk.Label(bottom, text='↑↓ 入力行を移動　Tab 定型文', style='Muted.TLabel').pack(side='left')
        self.preview_button = ActionButton(bottom, busy=True, text='変更案を確認', command=self.preview,
                                          style='Primary.TButton')
        self.preview_button.pack(side='right')
        ttk.Button(bottom,text='入力を戻す',command=self.revert).pack(side='right',padx=8)
        ttk.Button(bottom,text='参照を確認',command=self.references).pack(side='right')
        self.status = ttk.Label(self.frame, style='Muted.TLabel')
        self.status.pack(anchor='w')

    def references(self):
        if self.identity is not None:
            dialogs.Modal(self.view.app,'マクロの参照',self.reference_text).wait()

    def input_changed(self,*_):
        if self.loading or self.status_job:return
        self.status_job=self.frame.after_idle(self.refresh_status)

    def refresh_status(self):
        self.status_job=None
        self.view.update_edit_status()

    def cancel_status(self,event):
        if event.widget is self.frame and self.status_job:
            self.frame.after_cancel(self.status_job);self.status_job=None

    def revert(self):
        if self.identity is None or not self.has_pending():return
        if not dialogs.askyesno('マクロの入力を戻す','表示中のマクロを、作業データの内容に戻します。\n未適用の入力は失われます。\n\n入力を戻してよいですか？',parent=self.view.app):return
        folder,address=self.identity
        self.discard([self.identity])
        macro=next(m for m in self.view.character.macros if macro_key(m)==address)
        self.show(folder,macro);self.view.update_edit_status()

    def focus_line(self, index):
        self.active_line = index
        for n, entry in enumerate(self.entries):
            entry.configure(bg=SELECT if n == index else PANEL)

    def move_line(self, index, delta):
        target = index + delta
        if 1 <= target <= 6:
            position = self.entries[index].index('insert')
            self.entries[target].focus_set()
            self.entries[target].icursor(min(position, len(self.entries[target].get())))
        return 'break'

    def close_phrases(self):
        for controller in self.controllers:
            if controller.popup and controller.popup.winfo_exists():
                controller.popup.destroy()
                controller.popup = None

    def capture(self):
        if self.identity is None:
            return
        title = self.entries[0].get()
        lines = tuple(controller.value for controller in self.controllers)
        changed = (title != self.macro.title.display or
                   tuple(map(text_value, lines)) != tuple(map(text_value, self.macro.lines)))
        if changed:
            self.pending[self.identity] = (self.macro, title, lines)
        else:
            self.pending.pop(self.identity, None)

    def show(self, folder, macro):
        self.capture()
        self.close_phrases()
        self.identity = (folder, macro_key(macro))
        self.macro = macro
        source = (id(self.view.snapshot.phrases), id(self.view.snapshot.items))
        if self.catalog_source != source:
            self.catalog = background(self.view.app, PhraseCatalog, self.view.snapshot.phrases,
                                      self.view.snapshot.phrase_readings, self.view.snapshot.items)
            self.catalog_source = source
        saved = self.pending.get(self.identity)
        if saved:
            self.macro, title, lines = saved
        else:
            title, lines = macro.title.display, macro.lines
        self.loading=True
        for index, entry in enumerate(self.entries):
            entry.configure(validate='none', state='normal')
            if index:
                if len(self.controllers) < index:
                    self.controllers.append(PhraseEntry(entry, lines[index - 1], self.catalog))
                controller = self.controllers[index - 1]
                controller.catalog = self.catalog
                controller.set_value(lines[index - 1], 0)
                entry.configure(validate='key')
            else:
                entry.delete(0, 'end')
                entry.insert(0, title)
            if self.view.editor.blocked:
                entry.configure(state='disabled')
        self.loading=False
        self.preview_button.configure(state='disabled' if self.view.editor.blocked else 'normal')
        self.address.configure(text=f'Book {macro.book:02} / Palette {macro.palette:02} / {macro.bank.upper()} {macro.key % 10}')
        self.status.configure(text='入力は「変更案を確認」から作業へ適用します。適用済みの作業は自動保存されます。')
        self.frame.pack(fill='x')

    def hide(self):
        self.capture()
        self.close_phrases()
        self.identity = None
        self.frame.pack_forget()

    def discard(self, identities=None):
        if identities is None:
            self.pending.clear()
        else:
            for identity in identities:
                self.pending.pop(identity, None)
        # Prevent a refresh from capturing just-published inputs against the old base.
        if identities is None or self.identity in identities:
            self.identity = None

    def has_pending(self, folder=None):
        self.capture()
        return any(folder is None or identity[0] == folder for identity in self.pending)

    def preview(self, folder=None, after_apply=None):
        self.capture()
        identities = [key for key in self.pending if key == self.identity] if folder is None else [
            key for key in self.pending if key[0] == folder]
        if not identities:
            self.status.configure(text='入力の変更はありません。')
            return
        requests = [(key, self.pending[key]) for key in identities]
        def prepare():
            changes = []
            for (character, address), (base, title, lines) in requests:
                edit = self.view.editor.prepare_macro_edit(character, address, title, lines)
                if any(value(change.before) != value(base) for change in edit.changes):
                    raise ValueError('入力中にこのマクロの作業内容が変わりました。入力内容を確認してから変更をやり直してください。')
                changes.extend(edit.changes)
            return Edit('マクロの入力を反映', tuple(changes))
        try:
            edit = background(self.view.app, prepare)
        except (OSError, ValueError) as error:
            dialogs.showerror('入力内容', str(error), parent=self.view.app)
            return
        def applied():
            self.discard(identities)
        self.view.preview_edit(edit, lambda: self.view.editor.apply(edit), on_applied=applied,
                               after_close=after_apply)
