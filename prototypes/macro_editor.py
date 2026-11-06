"""Native layout prototype. Only synthetic, in-memory records are edited."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from ff11reader.ui_actions import ActionButton
from . import theme as dialogs
from .theme import BG, PANEL, FG, SELECT, BORDER, MUTED, install, TabBar, recolor
from ff11reader.domain import Text
from ff11reader.phrase_ui import PhraseEntry
from ff11reader.phrases import PhraseCatalog
from ff11reader.text_editing import remap_text





class MockPhraseEntry(PhraseEntry):
    """Keep the production token adapter's completed edit in mock memory."""
    def __init__(self, entry, catalog, on_value):
        self.on_value = on_value
        super().__init__(entry, Text('', '', 'draft', ()), catalog)

    def open(self, event=None):
        result = super().open(event)
        recolor(self.popup)
        return result

    def set_value(self, value, cursor):
        super().set_value(value, cursor)
        self.on_value(value)


class MacroEditorMock:
    def __init__(self, root):
        self.root = root
        self.records = {}
        self.saved = {}
        self.key = (1, 1, 'Ctrl', 0)
        self.loading = False
        self.active_line = 0
        self.token_values = {}
        self.phrase_entries = []
        self.catalog = PhraseCatalog({0x0100: '白魔法', 0x0101: 'ケアル',
                                      0x0102: 'リジェネ', 0x0200: 'ジョブアビリティ',
                                      0x0201: 'ファントムロール'})
        self.records[self.key] = ('通常', ('/equipset 001', '/echo 通常装備', '', '', '', ''))
        self.records[(1, 1, 'Ctrl', 1)] = ('WS', ('/equipset 002', '/ws "サベッジブレード" <t>', '', '', '', ''))
        self.saved = deepcopy(self.records)
        root.title('FF11 ワークスペース — デザイン確認版')
        root.geometry('1180x820')
        root.minsize(1000, 760)
        install(root)
        header = ttk.Frame(root, padding=16)
        header.pack(fill='x')
        ttk.Label(header, text='FF11 Macro & Equip', font=('Yu Gothic UI', 14, 'bold')).pack(side='left')
        ttk.Label(header, text='Sample  /  合成データ', style='Muted.TLabel').pack(side='right')
        notebook = ttk.Notebook(root, style='Pages.TNotebook')
        self.notebook = notebook
        notebook.pack(fill='both', expand=True, padx=8, pady=8)
        macro_page = ttk.Frame(notebook)
        notebook.add(macro_page, text='マクロ')
        from .equipment_workspace import EquipmentWorkspace
        self.equipment = EquipmentWorkspace(notebook, root)
        notebook.add(self.equipment.page, text='装備セット')
        notebook.add(self.equipment.inventory_page, text='インベントリ')
        self.tab_bar = TabBar(root, notebook)
        self.tab_bar.pack(fill='x', before=notebook)
        body = ttk.Panedwindow(macro_page, orient='horizontal')
        body.pack(fill='both', expand=True, padx=16, pady=(16, 0))
        left = ttk.Frame(body, padding=(0, 0, 12, 0))
        main = ttk.Frame(body, padding=(16, 0, 0, 0))
        body.add(left, weight=0)
        body.add(main, weight=1)
        self.tree = ttk.Treeview(left, show='tree', selectmode='browse', style='Mock.Treeview')
        self.tree.column('#0', width=180, minwidth=150)
        for book, title in [(1, 'コルセア'), (2, '吟遊詩人')]:
            self.tree.insert('', 'end', iid=f'b{book}', text=f'{book:02} {title}', open=True)
            for palette, name in enumerate(['通常', 'ソロ', 'パーティ'], 1):
                self.tree.insert(f'b{book}', 'end', iid=f'{book}:{palette}', text=f'{palette:02} {name}')
        self.tree.pack(fill='both', expand=True)
        self.tree.selection_set('1:1')
        self.tree.bind('<<TreeviewSelect>>', self.select_palette)
        top = ttk.Frame(main)
        top.pack(fill='x', pady=(0, 14))
        self.heading = ttk.Label(top, font=('Yu Gothic UI', 13, 'bold'))
        self.heading.pack(side='left')
        self.menu = tk.Menu(root, tearoff=False, bg=PANEL, fg=FG)
        self.menu.add_command(label='マクロの収納番号を補正', command=lambda: self.explain('収納番号の補正'))
        self.menu.add_command(label='参照先を確認', command=lambda: self.explain('参照先の確認'))
        self.menu_button = ActionButton(top, text='操作 ⋯', command=self.open_menu)
        self.menu_button.pack(side='right')
        self.buttons = {}
        for bank in ('Ctrl', 'Alt'):
            row = ttk.Frame(main)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=bank, width=4).grid(row=0, column=0)
            for index in range(10):
                row.columnconfigure(index + 1, weight=1, uniform='keys')
                button = ActionButton(row, width=5, command=lambda b=bank, i=index: self.select_macro(b, i))
                button.grid(row=0, column=index + 1, padx=2, sticky='ew')
                self.buttons[bank, index] = button
        name_row = ttk.Frame(main)
        name_row.pack(fill='x', pady=(24, 12))
        ttk.Label(name_row, text='マクロ名').pack(side='left', padx=(0, 12))
        self.name = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.name, width=22).pack(side='left')
        self.address = ttk.Label(name_row)
        self.address.pack(side='left', padx=14)
        self.lines = [tk.StringVar() for _ in range(6)]
        self.entries = []
        for index, variable in enumerate(self.lines):
            row = tk.Frame(main, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill='x')
            tk.Label(row, text=str(index + 1), width=4, bg=PANEL, fg=MUTED).pack(side='left')
            entry = tk.Entry(row, textvariable=variable, bg=PANEL, fg=FG,
                             insertbackground=FG, relief='flat', font=('MS Gothic', 12))
            entry.pack(side='left', fill='x', expand=True, ipady=11, padx=(0, 12))
            entry.bind('<FocusIn>', lambda e, i=index: self.focus_line(i))
            # On Windows IME, composing keys are handled by the IME before Tk.
            entry.bind('<Up>', lambda e, i=index: self.move_line(i, -1))
            entry.bind('<Down>', lambda e, i=index: self.move_line(i, 1))
            self.entries.append(entry)
            self.phrase_entries.append(MockPhraseEntry(
                entry, self.catalog, lambda value, i=index: self.keep_phrase(i, value)))
        tools = ttk.Frame(main)
        tools.pack(fill='x', pady=12)
        ActionButton(tools, text='定型文を挿入（Tab）', command=self.open_phrase).pack(side='left')
        ttk.Label(tools, text='↑ ↓：編集行を移動  /  Tab：定型文候補').pack(side='right')
        footer = ttk.Frame(macro_page, padding=16)
        footer.pack(side='bottom', fill='x', before=body)
        self.status = tk.StringVar(value='変更なし')
        ttk.Label(footer, textvariable=self.status).pack(side='left')
        ActionButton(footer, text='変更を確認して保存', style='Primary.TButton', command=self.preview).pack(side='right')
        for variable in [self.name, *self.lines]:
            variable.trace_add('write', self.changed)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.render()

    def record(self, key):
        return self.records.get(key, ('', ('',) * 6))

    def changed(self, *_):
        if self.loading:
            return
        self.records[self.key] = self.name.get(), tuple(v.get() for v in self.lines)
        for index, adapter in enumerate(self.phrase_entries):
            if not adapter.updating:
                adapter.value = remap_text(adapter.value, self.lines[index].get())
                self.token_values[self.key, index] = adapter.value
        self.status.set('● モック内に未保存の変更' if self.differences() else '変更なし')
        self.refresh_buttons()

    def differences(self):
        empty = ('', ('',) * 6)
        return [k for k in self.records.keys() | self.saved.keys()
                if self.records.get(k, empty) != self.saved.get(k, empty)]

    def refresh_buttons(self):
        book, palette, bank, index = self.key
        for (b, i), button in self.buttons.items():
            title = self.record((book, palette, b, i))[0]
            button.configure(text=f'{(i + 1) % 10}\n{title or "空き"}',
                             style='Selected.TButton' if (b, i) == (bank, index) else 'TButton')

    def render(self):
        self.loading = True
        try:
            name, lines = self.record(self.key)
            self.name.set(name)
            for index, value in enumerate(lines):
                text = self.token_values.get((self.key, index), Text(value, '', 'draft', ()))
                self.phrase_entries[index].set_value(text, 0)
            book, palette, bank, index = self.key
            self.heading.configure(text=f'Book {book:02} / Palette {palette:02}')
            self.address.configure(text=f'{bank} {(index + 1) % 10}')
            self.refresh_buttons()
        finally:
            self.loading = False

    def select_macro(self, bank, index):
        self.close_phrases()
        self.key = (*self.key[:2], bank, index)
        self.render()

    def select_palette(self, event=None):
        selection = self.tree.selection()
        if selection and ':' in selection[0]:
            self.close_phrases()
            book, palette = map(int, selection[0].split(':'))
            self.key = (book, palette, 'Ctrl', 0)
            self.render()

    def focus_line(self, index):
        self.active_line = index
        for i, entry in enumerate(self.entries):
            entry.configure(bg=SELECT if i == index else PANEL)

    def keep_phrase(self, index, value):
        if not self.loading:
            self.token_values[self.key, index] = value
            self.changed()

    def open_phrase(self):
        return self.phrase_entries[self.active_line].open()

    def close_phrases(self):
        for adapter in self.phrase_entries:
            if adapter.popup and adapter.popup.winfo_exists():
                adapter.popup.destroy()
                adapter.popup = None

    def move_line(self, index, delta):
        target = index + delta
        if 0 <= target < 6:
            position = self.entries[index].index('insert')
            self.entries[target].focus_set()
            self.entries[target].icursor(min(position, len(self.lines[target].get())))
        return 'break'

    def open_menu(self):
        try:
            self.menu.tk_popup(self.menu_button.winfo_rootx(), self.menu_button.winfo_rooty() + self.menu_button.winfo_height())
        finally:
            self.menu.grab_release()

    def explain(self, action):
        dialogs.showwarning(action, f'{action}をここから開く配置案です。\nこのモックは名前と6行の編集操作を確認できます。', parent=self.root)

    def preview(self):
        keys = sorted(self.differences())
        if not keys:
            self.status.set('変更なし')
            return
        text = '\n\n'.join(f'Book {b:02} / Palette {p:02} / {bank} {(i + 1) % 10}\n'
                           f'{self.record((b,p,bank,i))[0] or "名前なし"}\n' +
                           '\n'.join(f'{n+1}: {line}' for n, line in enumerate(self.record((b,p,bank,i))[1]))
                           for b,p,bank,i in keys)
        question = ('以下のマクロを、モック内で保存済みとして扱います。\n'
                    '内容はメモリ上だけに保持され、モックを終了すると失われます。\n'
                    'ゲームファイルへの書き込みはありません。\n\n'
                    '終了後に内容が残らないことを了承して、保存済みにしますか？\n'
                    '「いいえ」では編集を保持して画面に戻ります。\n\n対象の変更\n' + text)
        if dialogs.askyesno('マクロの保存確認', question, parent=self.root):
            self.saved = deepcopy(self.records)
            self.status.set('モック内で保存済み')

    def close(self):
        if (self.differences() or self.equipment.sets != self.equipment.saved) and not dialogs.askyesno(
                '編集内容を破棄して終了しますか？',
                'モックを終了すると、マクロと装備セットの編集内容は失われます。\n'
                'モック内で保存済みにした内容も、次回起動時には復元できません。\n\n'
                '編集内容を失うことを了承して、終了しますか？\n'
                '「いいえ」では編集を保持して画面に戻ります。', parent=self.root):
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    MacroEditorMock(root)
    root.mainloop()


if __name__ == '__main__':
    main()
