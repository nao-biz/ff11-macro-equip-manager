"""Keyboard interaction prototype with synthetic Text values; no game I/O."""
import tkinter as tk
from tkinter import ttk
from ff11reader.domain import Text
from ff11reader.edit_interaction import EditInteraction
from ff11reader.phrase_ui import PhraseEntry
from ff11reader.phrases import PhraseCatalog
from ff11reader.text_editing import replace_range
from ff11reader import theme
from ff11reader.macro_editor_ui import ime_composing


class InteractionMock:
    def __init__(self, root):
        self.root = root
        root.title('FF11 共通操作モック')
        root.geometry('1000x620')
        theme.install(root)
        self.flow = EditInteraction()
        self.selected = 1
        self.history = []
        self.cursor = 0
        self.entries, self.controllers = [], []
        names = {0x1B70: 'イレース', 0x1BC0: 'オーラ', 0x1FAB: '簡素清貧の章'}
        catalog = PhraseCatalog(names)
        text = lambda s: Text(s, '', 'draft', ())
        self.values = [text('回復'), text('/ja '), text('/ma '), text('/ma '), text('/wait 1'), text(''), text('')]
        for row, key in [(1, 0x1FAB), (2, 0x1B70), (3, 0x1BC0)]:
            self.values[row] = replace_range(self.values[row], 4, 4, '【'+names[key]+'】', f'0201{key:04X}')
        ttk.Label(root, text='マクロ編集 · 操作確認', font=('Yu Gothic UI', 18, 'bold'), padding=18).pack(anchor='w')
        ttk.Label(root, text='合成データ / ゲームへの書き込みなし', padding=(18, 0)).pack(anchor='w')
        self.mode = ttk.Label(root, padding=18)
        self.mode.pack(anchor='w')
        for i, value in enumerate(self.values):
            row = ttk.Frame(root, padding=(18, 5)); row.pack(fill='x')
            ttk.Label(row, text='名前' if i == 0 else str(i), width=5).pack(side='left')
            entry = tk.Entry(row, font=('Yu Gothic UI', 13), relief='flat', fg=theme.FG)
            entry.pack(side='left', fill='x', expand=True, ipady=6)
            controller = PhraseEntry(entry, value, catalog)
            controller.set_value(value, 0)
            controller.row_mode = True
            entry.configure(state='readonly', readonlybackground=theme.PANEL)
            self.entries.append(entry); self.controllers.append(controller)
            entry.bind('<Button-1>', lambda e, n=i: self.select(n))
            for key, step in [('Up', -1), ('Left', -1), ('Down', 1), ('Right', 1)]:
                entry.bind('<'+key+'>', lambda e, d=step: self.move(d))
            entry.bind('<Return>', lambda e: self.decide())
            entry.bind('<Escape>', lambda e: self.cancel())
            entry.bind('<Tab>', lambda e: self.candidate())
            entry.bind('<Control-z>', lambda e: self.undo(-1))
            entry.bind('<Control-y>', lambda e: self.undo(1))
            entry.bind('<<Cut>>', lambda e, c=controller: 'break' if self.flow.stage == 'select' else c.copy(cut=True))
            entry.bind('<<Paste>>', lambda e, c=controller: 'break' if self.flow.stage == 'select' else c.paste())
        bar = ttk.Frame(root, padding=18); bar.pack(fill='x')
        ttk.Button(bar, text='決定 / 確定  Enter', command=self.decide).pack(side='left')
        ttk.Button(bar, text='取消 / 戻る  Esc', command=self.cancel).pack(side='left', padx=6)
        ttk.Button(bar, text='Undo  Ctrl+Z', command=lambda: self.undo(-1)).pack(side='right')
        ttk.Button(bar, text='Redo  Ctrl+Y', command=lambda: self.undo(1)).pack(side='right', padx=6)
        self.message = ttk.Label(root, padding=(18, 0), wraplength=940)
        self.message.pack(anchor='w')
        self.select(1)

    def paint(self):
        stage = {'select': '行選択', 'edit': '内容編集', 'candidate': '定型文候補'}[self.flow.stage]
        self.mode.configure(text=f'{stage}   |   ↑↓←→ 選択   Enter 決定・確定   Esc 取消   Tab 定型文   |   履歴 {self.cursor}/{len(self.history)}')
        for i, entry in enumerate(self.entries):
            entry.configure(readonlybackground=theme.SELECT if i == self.selected else theme.PANEL)

    def select(self, index):
        if self.flow.stage != 'select':
            self.message.configure(text='Enterで確定、またはEscで取消してから次の行を選択します。')
            self.entries[self.selected].focus_set()
            return 'break'
        self.selected = max(0, min(6, index))
        self.entries[self.selected].focus_set()
        self.paint()
        return 'break'

    def move(self, delta):
        if self.flow.stage == 'select':
            return self.select(self.selected + delta)

    def apply(self, index, before, after):
        limit = 16 if index == 0 else 60
        if len(after.display.encode('cp932')) > limit:
            raise ValueError(f'入力が長すぎます（このモックでは表示文字列をCP932で{limit}バイトまで）。')
        if before != self.values[index]:
            raise ValueError('編集開始後に元の値が変わりました。')
        if before == after:
            return
        self.history[self.cursor:] = [(index, before, after)]
        self.cursor += 1
        self.values[index] = after

    def decide(self):
        index = self.selected
        if self.flow.stage == 'candidate':
            return 'break'
        if ime_composing(self.entries[index]):
            return 'break'
        if self.flow.stage == 'select':
            self.flow.begin(index, self.values[index])
            self.controllers[index].row_mode = False
            self.entries[index].configure(state='normal')
            self.entries[index].icursor('end')
            self.message.configure(text='内容を編集できます。Enterで確定、Escで編集開始前に戻ります。')
        else:
            try:
                self.flow.commit(self.controllers[index].value, self.apply)
            except (ValueError, UnicodeError) as exc:
                self.message.configure(text=str(exc)); return 'break'
            self.lock()
            self.message.configure(text='確定しました。Undoでこの編集を戻せます。')
        self.entries[index].focus_set(); self.paint()
        return 'break'

    def lock(self):
        self.entries[self.selected].configure(state='readonly')
        self.controllers[self.selected].row_mode = True

    def cancel(self):
        if ime_composing(self.entries[self.selected]):
            return 'break'
        if self.flow.stage == 'candidate':
            popup = self.controllers[self.selected].popup
            if popup is not None: popup.destroy()
            self.flow.close_candidate()
        else:
            restored = self.flow.cancel()
            if restored:
                index, original = restored
                self.controllers[index].set_value(original, 0)
                self.lock()
        self.entries[self.selected].focus_set(); self.paint()
        self.message.configure(text='元の操作段階へ戻りました。')
        return 'break'

    def candidate(self):
        if self.flow.stage != 'edit' or self.selected == 0:
            return 'break'
        controller = self.controllers[self.selected]
        self.flow.open_candidate()
        controller.open()
        popup = controller.popup
        def closed(event):
            if event.widget is popup:
                self.flow.close_candidate(); self.paint()
                self.entries[self.selected].focus_set()
        popup.bind('<Destroy>', closed, add='+')
        self.paint()
        return 'break'

    def undo(self, direction):
        if self.flow.stage != 'select':
            self.message.configure(text='編集中の取消はEscを使います。確定後はUndoで戻せます。')
            return 'break'
        target = self.cursor + direction
        if not 0 <= target <= len(self.history): return 'break'
        index, before, after = self.history[self.cursor-1 if direction < 0 else self.cursor]
        self.values[index] = before if direction < 0 else after
        self.controllers[index].set_value(self.values[index], 0)
        self.cursor = target
        self.select(index)
        self.message.configure(text='Undoしました。' if direction < 0 else 'Redoしました。')
        return 'break'


if __name__ == '__main__':
    root = tk.Tk()
    InteractionMock(root)
    root.mainloop()
