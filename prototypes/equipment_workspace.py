"""Synthetic equipment and inventory tabs for native interaction review."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from ff11reader.ui_actions import ActionButton
from . import theme as dialogs
from .theme import PANEL, FG, SELECT, ACCENT

SLOTS = ('メイン', 'サブ', '遠隔', '矢弾', '頭', '首', '左耳', '右耳',
         '胴', '両手', '左指', '右指', '背', '腰', '両脚', '両足')
NAMES = ('ロスタム', 'ネイグリング', 'デスペナルティ', 'クロノブレット',
         'ニャメヘルム', 'コンバタントトルク', 'テロスピアス', 'ブルタルピアス',
         'ニャメメイル', 'ニャメガントレ', '王将の指輪', 'シュネデックリング',
         'カムラスマント', 'セールフィベルト+1', 'ニャメフランチャ', 'ニャメソルレット')


class EquipmentWorkspace:
    def __init__(self, parent, root):
        self.root = root
        self.page = ttk.Frame(parent, padding=12)
        self.inventory_page = ttk.Frame(parent, padding=16)
        self.items = [dict(name=name, path='B' if i in (0, 4, 8, 9, 14, 15) else '',
                           bag='ワードローブ1', position=i + 1, slot=i)
                      for i, name in enumerate(NAMES)]
        self.items.append(dict(name='ロスタム', path='C', bag='ワードローブ2', position=4, slot=0))
        self.sets = [list(range(16)) for _ in range(5)]
        self.saved = deepcopy(self.sets)
        self.set_index = 0
        self.slot_index = 0
        self.editing = False
        body = ttk.Panedwindow(self.page, orient='horizontal')
        body.pack(fill='both', expand=True)
        left, center, right = (ttk.Frame(body, padding=8) for _ in range(3))
        for frame, weight in ((left, 0), (center, 1), (right, 0)):
            body.add(frame, weight=weight)
        self.set_list = tk.Listbox(left, width=19, exportselection=False, bg=PANEL, fg=FG,
                                   selectbackground=SELECT, selectforeground=ACCENT, relief='flat', highlightthickness=0)
        for i, name in enumerate(('通常装備', '近接WS', '射撃WS', 'ロール', '移動'), 1):
            self.set_list.insert('end', f'{i:03} {name}')
        self.set_list.selection_set(0)
        self.set_list.pack(fill='both', expand=True)
        self.set_list.bind('<<ListboxSelect>>', self.select_set)
        heading = ttk.Frame(center)
        heading.pack(fill='x', pady=(0, 12))
        self.heading = ttk.Label(heading, font=('Yu Gothic UI', 14, 'bold'))
        self.heading.pack(side='left')
        ActionButton(heading, text='参照を補正', command=self.fix_preview).pack(side='right')
        grid = ttk.Frame(center)
        grid.pack(fill='x')
        self.cards = []
        for i, slot in enumerate(SLOTS):
            grid.columnconfigure(i % 4, weight=1, uniform='equipment')
            grid.rowconfigure(i // 4, weight=1, uniform='equipment')
            button = ActionButton(grid, width=12, padding=(8, 12), command=lambda index=i: self.select_slot(index))
            button.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky='nsew')
            button.bind('<Double-Button-1>', lambda event, index=i: self.edit_slot(index))
            self.cards.append(button)
        self.detail = ttk.Label(center, wraplength=560, padding=(0, 12))
        self.detail.pack(fill='x')
        ActionButton(center, text='選択枠を編集', command=lambda: self.edit_slot(self.slot_index)).pack(anchor='w')
        self.right = right
        self.summary = ttk.Frame(right, width=270)
        self.summary.pack(fill='both', expand=True)
        ttk.Label(self.summary, text='装備の加算値', font=('Yu Gothic UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(self.summary, text='配置確認用のサンプル値', padding=(0, 10)).pack(anchor='w')
        ttk.Label(self.summary, text='HP +240     MP +80\nSTR +185    DEX +172\n\n攻撃 +310   命中 +286\n飛攻 +260   飛命 +242\n魔攻 +150   魔命 +210\n防 +920     回避 +360\n魔防 +25    魔回避 +510\n\n被ダメージ −38%\nヘイスト +26%\nストアTP +42\nWSダメージ +31%',
                  font=('MS Gothic', 11), padding=(0, 10)).pack(anchor='w')
        ttk.Label(self.summary, text='装備変更後の数値計算は未接続', wraplength=240).pack(anchor='w')
        self.candidates_panel = ttk.Frame(right)
        self.candidate_title = ttk.Label(self.candidates_panel, font=('Yu Gothic UI', 12, 'bold'))
        self.candidate_title.pack(anchor='w', pady=8)
        self.candidates = ttk.Treeview(self.candidates_panel, columns=('path', 'bag'), show='tree headings',
                                      selectmode='browse', style='Mock.Treeview', height=10)
        self.candidates.heading('#0', text='装備名')
        self.candidates.column('#0', width=135)
        self.candidates.heading('path', text='Path')
        self.candidates.column('path', width=50)
        self.candidates.heading('bag', text='収納')
        self.candidates.column('bag', width=100)
        self.candidates.pack(fill='both', expand=True)
        ActionButton(self.candidates_panel, text='この装備に変更', command=self.apply_candidate).pack(fill='x', pady=8)
        ActionButton(self.candidates_panel, text='取消・集計に戻る', command=self.show_summary).pack(fill='x')
        footer = ttk.Frame(self.page, padding=(8, 12))
        footer.pack(side='bottom', fill='x', before=body)
        self.status = tk.StringVar(value='変更なし')
        ttk.Label(footer, textvariable=self.status).pack(side='left')
        ActionButton(footer, text='変更を確認して保存', style='Primary.TButton', command=self.save).pack(side='right')
        self.build_inventory()
        self.render()

    def description(self, value):
        if value == 'keep':
            return '変更しない'
        if value == 'remove':
            return '装備を外す'
        item = self.items[value]
        return item['name'] + (' / Path ' + item['path'] if item['path'] else '')

    def render(self):
        self.heading.configure(text=self.set_list.get(self.set_index))
        for i, button in enumerate(self.cards):
            value = self.sets[self.set_index][i]
            name = self.description(value).replace(' / ', '\n')
            button.configure(text=f'{SLOTS[i]}\n\n{name}', style='Selected.TButton' if i == self.slot_index else 'TButton')
        self.select_slot(self.slot_index)
        self.status.set('● モック内に未保存の変更' if self.sets != self.saved else '変更なし')

    def select_slot(self, index):
        if self.editing and index != self.slot_index:
            self.show_summary()
        self.slot_index = index
        for i, button in enumerate(self.cards):
            button.configure(style='Selected.TButton' if i == index else 'TButton')
        value = self.sets[self.set_index][index]
        text = f'{SLOTS[index]} / {self.description(value)}'
        if isinstance(value, int):
            item = self.items[value]
            text += f'\n{item["bag"]}・位置{item["position"]} / 参照一致'
        self.detail.configure(text=text)

    def select_set(self, event=None):
        if self.set_list.curselection():
            self.show_summary()
            self.set_index = self.set_list.curselection()[0]
            self.render()

    def edit_slot(self, index):
        self.select_slot(index)
        self.editing = True
        self.summary.pack_forget()
        self.candidates_panel.pack(fill='both', expand=True)
        self.candidate_title.configure(text=f'{SLOTS[index]}の装備候補')
        self.candidates.delete(*self.candidates.get_children())
        for action, label in [('keep', '変更しない'), ('remove', '装備を外す')]:
            self.candidates.insert('', 'end', iid=action, text=label)
        for i, item in enumerate(self.items):
            if item['slot'] == index:
                self.candidates.insert('', 'end', iid=str(i), text=item['name'], values=(item['path'], item['bag']))
        self.candidates.selection_set(str(self.sets[self.set_index][index]))
        return 'break'

    def apply_candidate(self):
        selection = self.candidates.selection()
        if selection:
            value = selection[0]
            self.sets[self.set_index][self.slot_index] = int(value) if value.isdigit() else value
            self.show_summary()
            self.render()

    def show_summary(self):
        self.editing = False
        self.candidates_panel.pack_forget()
        self.summary.pack(fill='both', expand=True)

    def fix_preview(self):
        dialogs.showwarning('参照の補正', '合成データの参照は一致しています。補正対象はありません。', parent=self.root)

    def save(self):
        changes = [f'{s+1:03} / {SLOTS[i]}\n{self.description(before)} → {self.description(after)}'
                   for s, row in enumerate(self.sets) for i, after in enumerate(row)
                   if (before := self.saved[s][i]) != after]
        if not changes:
            self.status.set('変更なし')
        elif dialogs.askyesno('装備セットの保存確認',
                             '以下の装備セットを、モック内で保存済みとして扱います。\n'
                             '内容はメモリ上だけに保持され、モックを終了すると失われます。\n'
                             'ゲームファイルへの書き込みはありません。\n\n'
                             '終了後に内容が残らないことを了承して、保存済みにしますか？\n'
                             '「いいえ」では編集を保持して画面に戻ります。\n\n対象の変更\n'
                             + '\n\n'.join(changes), parent=self.root):
            self.saved = deepcopy(self.sets)
            self.render()

    def build_inventory(self):
        top = ttk.Frame(self.inventory_page)
        top.pack(fill='x', pady=(0, 12))
        ttk.Label(top, text='収納').pack(side='left')
        self.bag = tk.StringVar(value='すべて')
        box = ttk.Combobox(top, textvariable=self.bag, state='readonly', values=('すべて', 'ワードローブ1', 'ワードローブ2'))
        box.pack(side='left', padx=8)
        box.bind('<<ComboboxSelected>>', lambda e: self.refresh_inventory())
        ttk.Label(top, text='名前で検索').pack(side='left', padx=(20, 8))
        self.query = tk.StringVar()
        ttk.Entry(top, textvariable=self.query).pack(side='left')
        self.query.trace_add('write', lambda *_: self.refresh_inventory())
        self.inventory = ttk.Treeview(self.inventory_page, columns=('name', 'path', 'bag', 'position'),
                                     show='headings', selectmode='browse', style='Mock.Treeview')
        for key, title, width in [('name', '装備名', 300), ('path', 'Path', 80), ('bag', '収納', 180), ('position', '位置', 80)]:
            self.inventory.heading(key, text=title)
            self.inventory.column(key, width=width)
        self.inventory.pack(fill='both', expand=True)
        self.inventory_detail = ttk.Label(self.inventory_page, padding=(0, 16))
        self.inventory_detail.pack(fill='x')
        self.inventory.bind('<<TreeviewSelect>>', self.inspect_inventory)
        self.refresh_inventory()

    def refresh_inventory(self):
        self.inventory.delete(*self.inventory.get_children())
        for i, item in enumerate(self.items):
            if self.bag.get() not in ('すべて', item['bag']) or self.query.get().casefold() not in item['name'].casefold():
                continue
            self.inventory.insert('', 'end', iid=str(i), values=tuple(item[k] for k in ('name', 'path', 'bag', 'position')))
        self.inventory_detail.configure(text=f'{len(self.inventory.get_children())}件 / 合成データ')

    def inspect_inventory(self, event=None):
        selection = self.inventory.selection()
        if selection:
            i = int(selection[0])
            refs = [f'{s+1:03}' for s, row in enumerate(self.sets) if i in row]
            self.inventory_detail.configure(text=self.description(i) + '\n使用セット: ' + ('・'.join(refs) or 'なし'))
