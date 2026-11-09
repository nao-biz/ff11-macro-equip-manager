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


def ime_composing(entry):
    """Leave conversion Return/Escape to the Windows IME."""
    import os
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    imm=ctypes.windll.imm32
    imm.ImmGetContext.argtypes=[wintypes.HWND]
    imm.ImmGetContext.restype=wintypes.HANDLE
    imm.ImmGetCompositionStringW.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    imm.ImmReleaseContext.argtypes=[wintypes.HWND,wintypes.HANDLE]
    hwnd=entry.winfo_id();context=imm.ImmGetContext(hwnd)
    if not context:return False
    try:return imm.ImmGetCompositionStringW(context,8,None,0)>0
    finally:imm.ImmReleaseContext(hwnd,context)


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
        self.editing_line = None
        self.line_original = None
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
                entry.bind('<Left>', lambda e, n=i: self.move_line(n, -1))
                entry.bind('<Right>', lambda e, n=i: self.move_line(n, 1))
                entry.bind('<FocusIn>', lambda e, n=i: self.focus_line(n))
                entry.bind('<Return>', lambda e, n=i: self.toggle_line(n))
                entry.bind('<Escape>', lambda e, n=i: self.cancel_line(n))
            if not i:entry.bind('<FocusIn>',lambda e:self.focus_line(0))
            self.entries.append(entry)
        linebar=ttk.Frame(self.frame);linebar.pack(fill='x',pady=3)
        self.line_buttons={}
        for label,action in [('行コピー','copy'),('行貼り付け','paste'),('上へ','up'),('下へ','down')]:
            button=ttk.Button(linebar,text=label,command=lambda a=action:self.line_action(a),state='disabled')
            button.pack(side='left',padx=3);self.line_buttons[action]=button
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill='x', pady=6)
        self.mode_hint=ttk.Label(bottom, style='Muted.TLabel')
        self.mode_hint.pack(side='left')
        self.preview_button = ActionButton(bottom, busy=True, text='変更案を確認', command=self.preview,
                                          style='Primary.TButton')
        self.preview_button.pack(side='right')
        ttk.Button(bottom,text='入力を戻す',command=self.revert).pack(side='right',padx=8)
        ttk.Button(bottom,text='参照を確認',command=self.references).pack(side='right')
        self.status = ttk.Label(self.frame, style='Muted.TLabel')
        self.status.pack(anchor='w')

    def line_action(self,action):
        if self.editing_line is not None:return
        index=self.active_line-1
        if not 0<=index<len(self.controllers) or self.view.editor.blocked:return
        current=self.controllers[index]
        if action=='copy':current.copy(whole=True)
        elif action=='paste':current.paste(whole=True)
        else:
            target=index+(-1 if action=='up' else 1)
            if not 0<=target<len(self.controllers):return
            other=self.controllers[target];a,b=current.value,other.value
            current.set_value(b,0);other.set_value(a,0)
            index=target
        self.focus_line(index+1);self.entries[index+1].focus_set()
        self.capture();self.view.update_edit_status()

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
        if self.editing_line is not None and self.editing_line!=index:
            self.finish_line()
        self.active_line = index
        self.mode_hint.configure(text='内容編集：Enter 確定 / Esc 取消 / Tab 定型文' if self.editing_line else '行操作：矢印キー 選択 / Enter 内容編集')
        for action,button in self.line_buttons.items():
            enabled=1<=index<=6 and self.editing_line is None and not self.view.editor.blocked
            if action=='up':enabled=enabled and index>1
            if action=='down':enabled=enabled and index<6
            button.configure(state='normal' if enabled else 'disabled')
        for n, entry in enumerate(self.entries):
            entry.configure(bg=SELECT if n == index else PANEL,readonlybackground=SELECT if n==index else PANEL)

    def toggle_line(self,index):
        if self.view.editor.blocked:return 'break'
        if ime_composing(self.entries[index]):return 'break'
        if self.editing_line is not None:return self.finish_line()
        self.editing_line=index
        self.line_original=self.controllers[index-1].value
        self.controllers[index-1].row_mode=False
        self.entries[index].configure(state='normal')
        self.focus_line(index)
        return 'break'

    def cancel_line(self,index):
        if ime_composing(self.entries[index]):return 'break'
        return self.finish_line(cancel=True)

    def finish_line(self,cancel=False):
        index=self.editing_line
        if index is None:return 'break'
        controller=self.controllers[index-1]
        if cancel:controller.set_value(self.line_original,0)
        controller.row_mode=True
        self.entries[index].configure(state='readonly')
        self.editing_line=None
        self.line_original=None
        self.focus_line(index)
        self.capture()
        return 'break'

    def move_line(self, index, delta):
        if self.editing_line is not None:return
        target = index + delta
        if 1 <= target <= 6:
            self.focus_line(target)
            self.entries[target].focus_set()
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
        self.finish_line()
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
                controller.row_mode=True
                entry.configure(state='readonly')
            else:
                entry.delete(0, 'end')
                entry.insert(0, title)
            if self.view.editor.blocked:
                entry.configure(state='disabled')
        self.loading=False
        self.focus_line(1)
        self.preview_button.configure(state='disabled' if self.view.editor.blocked else 'normal')
        self.address.configure(text=f'Book {macro.book:02} / Palette {macro.palette:02} / {macro.bank.upper()} {macro.key % 10}')
        self.status.configure(text='入力は「変更案を確認」から作業へ適用します。ゲームへの反映は「ゲームへ書き戻す」から行います。')
        self.frame.pack(fill='x')

    def hide(self):
        self.finish_line()
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

    def apply_pending(self):
        """Capture Tk inputs before validating and applying them in the worker."""
        self.capture()
        requests = list(self.pending.items())
        if not requests:
            return
        def apply():
            changes = []
            for (character, address), (base, title, lines) in requests:
                edit = self.view.editor.prepare_macro_edit(character, address, title, lines)
                if any(value(change.before) != value(base) for change in edit.changes):
                    raise ValueError('入力中にマクロの内容が変わりました。入力を確認してください。')
                changes.extend(edit.changes)
            self.view.editor.apply(Edit('入力中のマクロを適用', tuple(changes)))
        background(self.view.app, apply)
        self.discard([key for key, _ in requests])
        self.view.refresh_edits()

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
