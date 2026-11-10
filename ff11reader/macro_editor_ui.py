"""Inline macro input; publication and persistence remain in Editor."""
import tkinter as tk
from tkinter import ttk
from . import dialogs
from .edit_values import text_value, value
from .editing import Edit, macro_key
from .edit_interaction import EditInteraction, DraftHistory
from .phrase_ui import PhraseEntry
from .phrases import PhraseCatalog
from .theme import PANEL, FG, MUTED, BORDER, SELECT
from .ui_actions import ActionButton
from .ui_tasks import background


from .input_methods import ime_composing


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
        self.flow = EditInteraction()
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
            for key,delta in [('Up',-1),('Left',-1),('Down',1),('Right',1)]:
                entry.bind('<'+key+'>',lambda e,n=i,d=delta:self.move_line(n,d))
            entry.bind('<FocusIn>',lambda e,n=i:self.focus_line(n))
            entry.bind('<Button-1>',lambda e,n=i:self.click_line(n))
            entry.bind('<Return>',lambda e,n=i:self.toggle_line(n))
            entry.bind('<Escape>',lambda e,n=i:self.cancel_line(n))
            entry.bind('<Control-z>',lambda e:self.history(-1))
            entry.bind('<Control-y>',lambda e:self.history(1))
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
        self.preview_button = ActionButton(bottom, busy=True, text='入力を確定', command=self.preview,
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
        self.restore_input_focus(index+1)
        if action!='copy':
            try:self.publish_inputs();self.view.refresh_edits()
            except (ValueError,OSError) as exc:self.status.configure(text=str(exc))
            self.restore_input_focus(index+1)
        self.view.update_edit_status()

    def references(self):
        if self.identity is not None:
            dialogs.Modal(self.view.app,'マクロの参照',self.reference_text).wait()

    def input_changed(self,*_):
        if self.loading or self.status_job:return
        self.status_job=self.frame.after_idle(self.refresh_status)

    def refresh_status(self):
        self.status_job=None
        self.record_draft()
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
            self.entries[self.editing_line].focus_set()
            return
        self.active_line = index
        self.mode_hint.configure(text='内容編集：Enter 確定 / Esc 取消 / Tab 定型文' if self.editing_line is not None else '行操作：矢印キー 選択 / Enter 内容編集')
        for action,button in self.line_buttons.items():
            enabled=1<=index<=6 and self.editing_line is None and not self.view.editor.blocked
            if action=='up':enabled=enabled and index>1
            if action=='down':enabled=enabled and index<6
            button.configure(state='normal' if enabled else 'disabled')
        for n, entry in enumerate(self.entries):
            entry.configure(bg=SELECT if n == index else PANEL,readonlybackground=SELECT if n==index else PANEL)

    def click_line(self,index):
        if self.editing_line is not None and self.editing_line!=index:
            self.entries[self.editing_line].focus_set()
            self.status.configure(text='Enterで確定、Escで取消してから次の行を選択してください。')
            return 'break'
        self.focus_line(index)
        self.entries[index].focus_set()
        if self.editing_line is None:return 'break'

    def toggle_line(self,index):
        if self.view.editor.blocked:return 'break'
        if ime_composing(self.entries[index]):return 'break'
        if self.editing_line is not None:return self.finish_line()
        self.editing_line=index
        self.line_original=self.controllers[index-1].value if index else self.entries[0].get()
        self.flow.begin(index,self.line_original)
        self.draft_history=DraftHistory(self.line_original)
        if index:self.controllers[index-1].row_mode=False
        self.entries[index].configure(state='normal')
        self.entries[index].icursor('end')
        self.focus_line(index)
        return 'break'

    def cancel_line(self,index):
        if self.editing_line is None:
            card=self.view.commands.cards.get(self.view.active_macro)
            if card is not None:card.focus_set()
            return 'break'
        if ime_composing(self.entries[index]):return 'break'
        return self.finish_line(cancel=True)

    def publish_inputs(self):
        self.capture()
        saved=self.pending.get(self.identity)
        if saved is None:return
        identity=self.identity
        base,title,lines=saved
        def apply():
            edit=self.view.editor.prepare_macro_edit(identity[0],identity[1],title,lines)
            if any(value(change.before)!=value(base) for change in edit.changes):
                raise ValueError('入力中にマクロの内容が変わりました。')
            self.view.editor.apply(edit)
        background(self.view.app,apply)
        self.discard([identity])

    def finish_line(self,cancel=False):
        index=self.editing_line
        if index is None:return 'break'
        if self.flow.stage=='candidate':
            self.close_phrases();self.flow.close_candidate();return 'break'
        if cancel:
            self.flow.cancel()
            if index:self.controllers[index-1].set_value(self.line_original,0)
            else:
                self.entries[0].delete(0,'end');self.entries[0].insert(0,self.line_original)
        else:
            draft=self.controllers[index-1].value if index else self.entries[0].get()
            try:self.flow.commit(draft,lambda *_:self.publish_inputs())
            except (ValueError,OSError) as exc:
                self.status.configure(text=str(exc));self.entries[index].focus_set();return 'break'
        if index:self.controllers[index-1].row_mode=True
        self.entries[index].configure(state='readonly')
        self.editing_line=None
        self.line_original=None
        self.capture()
        if not cancel:self.view.refresh_edits()
        self.restore_input_focus(index)
        return 'break'

    def restore_input_focus(self,index):
        commands=self.view.commands
        if commands.focus_job:
            self.view.app.after_cancel(commands.focus_job);commands.focus_job=None
        self.focus_line(index);self.entries[index].focus_set()

    def record_draft(self):
        index=self.editing_line
        if index is not None and self.flow.stage=='edit':
            current=self.controllers[index-1].value if index else self.entries[0].get()
            self.draft_history.observe(current)

    def history(self,direction):
        if self.editing_line is not None:
            if self.flow.stage!='edit':return 'break'
            self.record_draft()
            index=self.editing_line
            restored=self.draft_history.step(direction)
            if index:self.controllers[index-1].set_value(restored,len(restored.display))
            else:
                self.entries[0].delete(0,'end');self.entries[0].insert(0,restored)
                self.entries[0].icursor('end')
            return 'break'
        index=self.active_line
        self.view.undo_fix() if direction<0 else self.view.redo_edit()
        self.restore_input_focus(index)
        return 'break'

    def clipboard(self,index,action):
        controller=self.controllers[index-1]
        if action=='copy':return controller.copy()
        if action=='cut':controller.copy(cut=True)
        else:controller.paste()
        if self.editing_line is None:
            try:
                self.publish_inputs();self.view.refresh_edits()
            except (ValueError,OSError) as exc:self.status.configure(text=str(exc))
            self.restore_input_focus(index)
        return 'break'

    def move_line(self, index, delta):
        if self.editing_line is not None:return
        target = index + delta
        if 0 <= target <= 6:
            self.focus_line(target)
            self.entries[target].focus_set()
        return 'break'

    def open_candidate(self,index):
        if self.editing_line!=index or self.flow.stage!='edit':return 'break'
        controller=self.controllers[index-1]
        self.flow.open_candidate()
        try:controller.open()
        except Exception:
            self.flow.close_candidate();raise
        popup=controller.popup
        def closed(event):
            if event.widget is popup:
                self.flow.close_candidate()
                if self.entries[index].winfo_exists():self.entries[index].focus_set()
        popup.bind('<Destroy>',closed,add='+')
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
        self.editing_line=None
        self.line_original=None
        self.flow=EditInteraction()
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
                entry.bind('<Tab>',lambda e,n=index:self.open_candidate(n))
                for event,action in [('<<Copy>>','copy'),('<<Cut>>','cut'),('<<Paste>>','paste')]:
                    entry.bind(event,lambda e,n=index,a=action:self.clipboard(n,a))
                controller.row_mode=True
                entry.configure(state='readonly')
            else:
                entry.delete(0, 'end')
                entry.insert(0, title)
                entry.configure(state='readonly')
            if self.view.editor.blocked:
                entry.configure(state='disabled')
        self.loading=False
        self.focus_line(1)
        self.preview_button.configure(state='disabled' if self.view.editor.blocked else 'normal')
        self.address.configure(text=f'Book {macro.book:02} / Palette {macro.palette:02} / {macro.bank.upper()} {macro.key % 10}')
        self.status.configure(text='Enterで入力を確定し、Undoで戻せます。ゲームへの反映は「ゲームへ書き戻す」から行います。')
        self.frame.pack(fill='x')

    def hide(self):
        self.capture()
        self.editing_line=None
        self.line_original=None
        self.flow=EditInteraction()
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

    def apply_pending(self, folder=None):
        """Capture Tk inputs before validating and applying them in the worker."""
        self.capture()
        requests = [(identity, request) for identity, request in self.pending.items()
                    if folder is None or identity[0] == folder]
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
        if self.editing_line is not None:
            self.finish_line()
        else:
            try:self.apply_pending()
            except (ValueError,OSError) as exc:self.status.configure(text=str(exc));return
        if after_apply and self.editing_line is None:after_apply()
