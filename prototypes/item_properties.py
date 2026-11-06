"""Two-tab native property mock; all data and edits remain in memory."""
from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from ff11reader import theme
from ff11reader.augment_observation import AugmentBag
from ff11reader.ui_actions import ActionButton
from .equipment_review import EquipmentReviewMock
from .equipment_review_data import ReviewData, SLOTS
from .item_property_panel import ItemPropertyPanel


class PropertyData(ReviewData):
    def __init__(self):
        super().__init__()
        # Two storages, with distinct individuals of the same item type.
        self.items = {key: replace(item, container=13 if item.path in ('B', 'C') else 12)
                      for key, item in self.items.items()}
        self.items['15:3'] = replace(self.items['15:3'], item_id=1099, description=None)
        observed = {item.index: item for item in self.observation.export.bags[0].items}
        bags = tuple(AugmentBag(bag, 'ready', tuple(replace(observed[i.position], item_id=i.item_id) for i in self.items.values()
                                                  if i.container == bag)) for bag in (12, 13))
        self.observation = replace(self.observation, export=replace(self.observation.export, bags=bags),
                                   accepted_bags=frozenset({12, 13}))
        for master in self.master.values():
            master['description'] += '\nLv99〜 装備可能ジョブ: 戦赤シ\n雨天のとき被ダメージ-5%\n特殊な能力アップ'
        self.master[self.items['0:0'].item_id]['description'] = (
            'Ｄ100 隔200\n' + self.master[self.items['0:0'].item_id]['description'])
        self.master[1099] = {'name': self.items['15:3'].name, 'description': None}


class InventoryPropertiesMock(ttk.Frame):
    def __init__(self, parent, data, on_compare):
        super().__init__(parent, padding=(14, 8))
        self.data, self.on_compare = data, on_compare
        self.selected_key = None
        self.bag = None
        self.query = tk.StringVar()
        self.layout = tk.StringVar(value='リスト')
        self.columnconfigure(1, weight=3, minsize=530)
        self.columnconfigure(2, weight=2, minsize=440)
        self.rowconfigure(0, weight=1)
        left = ttk.Frame(self, padding=(0, 0, 16, 0))
        left.grid(row=0, column=0, sticky='ns')
        ttk.Label(left, text='収納', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        self.bags = tk.Listbox(left, width=17, exportselection=False, activestyle='none', relief='flat',
                               highlightthickness=0, bg=theme.PANEL, fg=theme.FG,
                               selectbackground=theme.SELECT, selectforeground=theme.ACCENT)
        for label in ('すべての収納', 'ワードローブ1', 'ワードローブ2'):
            self.bags.insert('end', label)
        self.bags.pack(fill='both', expand=True)
        self.bags.selection_set(0)
        self.bags.bind('<<ListboxSelect>>', self.change_bag)
        middle = ttk.Frame(self, padding=(0, 0, 20, 0))
        middle.grid(row=0, column=1, sticky='nsew')
        self.heading = ttk.Label(middle, font=('Yu Gothic UI', 13, 'bold'))
        self.heading.pack(anchor='w', pady=(0, 8))
        search = ttk.Frame(middle)
        search.pack(fill='x', pady=(0, 10))
        ttk.Label(search, text='名前・Path').pack(side='left', padx=(0, 8))
        ttk.Entry(search, textvariable=self.query, width=20).pack(side='left', fill='x', expand=True)
        for name in ('リスト', 'パネル'):
            ttk.Radiobutton(search, text=name, variable=self.layout, value=name,
                            command=self.render).pack(side='left', padx=(8, 0))
        self.list_frame = ttk.Frame(middle)
        self.listing = ttk.Treeview(self.list_frame, columns=('name', 'path', 'slot', 'bag'),
                                    show='headings', selectmode='browse', style='Mock.Treeview')
        for key, label, width in (('name', 'アイテム名', 180), ('path', 'Path', 50),
                                   ('slot', '部位', 70), ('bag', '収納 / 位置', 130)):
            self.listing.heading(key, text=label)
            self.listing.column(key, width=width, minwidth=width, stretch=key == 'name')
        bar = ttk.Scrollbar(self.list_frame, command=self.listing.yview)
        bar.pack(side='right', fill='y')
        self.listing.configure(yscrollcommand=bar.set)
        self.listing.pack(fill='both', expand=True)
        self.listing.bind('<<TreeviewSelect>>', self.select_row)
        self.panel_frame = ttk.Frame(middle)
        self.canvas = tk.Canvas(self.panel_frame, bg=theme.BG, highlightthickness=0)
        panel_bar = ttk.Scrollbar(self.panel_frame, command=self.canvas.yview)
        panel_bar.pack(side='right', fill='y')
        self.canvas.configure(yscrollcommand=panel_bar.set)
        self.canvas.pack(fill='both', expand=True)
        self.panels = ttk.Frame(self.canvas)
        window = self.canvas.create_window(0, 0, window=self.panels, anchor='nw')
        self.panels.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.bind('<MouseWheel>', self.scroll_panels)
        self.panel_buttons = {}
        right = ttk.Frame(self)
        right.grid(row=0, column=2, sticky='nsew')
        self.compare_button = ActionButton(right, text='装備セットで比較', command=self.compare,
                                           style='Primary.TButton')
        self.compare_button.pack(side='bottom', anchor='e', pady=(12, 0))
        self.properties = ItemPropertyPanel(right, data)
        self.properties.pack(fill='both', expand=True)
        self.query.trace_add('write', lambda *_: self.render())
        self.render()
        self.choose('0:0')

    def change_bag(self, event=None):
        selected = self.bags.curselection()
        if selected:
            self.bag = (None, 12, 13)[selected[0]]
            self.render()

    def render(self):
        query = self.query.get().casefold().strip()
        keys = [key for key, item in self.data.items.items()
                if (self.bag is None or item.container == self.bag) and query in item.label.casefold()]
        self.visible_keys = keys
        self.heading.configure(text=f'{len(keys)} アイテム')
        if self.selected_key not in keys:
            self.selected_key = None
        self.list_frame.pack_forget(); self.panel_frame.pack_forget()
        self.listing.delete(*self.listing.get_children())
        for button in self.panel_buttons.values():
            button.destroy()
        self.panel_buttons.clear()
        if self.layout.get() == 'リスト':
            self.list_frame.pack(fill='both', expand=True)
            for key in keys:
                item = self.data.items[key]
                self.listing.insert('', 'end', iid=key, values=(item.name, item.path if item.decoded else '未取得',
                                     SLOTS[item.slot], f'収納{item.container - 11} / {item.position}'))
        else:
            self.panel_frame.pack(fill='both', expand=True)
            for index, key in enumerate(keys):
                item = self.data.items[key]
                self.panels.columnconfigure(index % 3, weight=1, uniform='items')
                button = ActionButton(self.panels, text=item.name + '\n' +
                                      (f'Path {item.path}' if item.decoded else 'オグメ未取得') +
                                      f'  /  収納{item.container - 11} #{item.position}',
                                      width=1, padding=(6, 12), command=lambda k=key: self.choose(k))
                button.grid(row=index // 3, column=index % 3, sticky='ew', padx=3, pady=3)
                button.bind('<MouseWheel>', self.scroll_panels)
                self.panel_buttons[key] = button
            self.canvas.yview_moveto(0)
        self.choose(self.selected_key)

    def scroll_panels(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), 'units')
        return 'break'

    def select_row(self, event=None):
        selection = self.listing.selection()
        if self.layout.get() == 'リスト':
            self.choose(selection[0] if selection else None)

    def choose(self, key):
        self.selected_key = key if key in self.visible_keys else None
        if self.layout.get() == 'リスト':
            desired = (self.selected_key,) if self.selected_key else ()
            if self.listing.selection() != desired:
                self.listing.selection_set(desired)
        for candidate, button in self.panel_buttons.items():
            button.configure(style='Selected.TButton' if candidate == self.selected_key else 'TButton')
        self.properties.show(self.selected_key)
        self.compare_button.configure(state='normal' if self.selected_key else 'disabled')

    def compare(self):
        if self.selected_key:
            self.on_compare(self.selected_key)


class ItemPropertiesMock:
    def __init__(self, root):
        self.root = root
        theme.install(root)
        self.data = PropertyData()
        header = ttk.Frame(root, padding=(18, 8))
        header.pack(fill='x')
        ttk.Label(header, text='FF11 Macro & Equip', font=('Yu Gothic UI', 14, 'bold')).pack(side='left')
        ttk.Label(header, text='プロパティ表示の検討 / 合成データ', style='Muted.TLabel').pack(side='right')
        tabbar = ttk.Frame(root, padding=(14, 0, 14, 6))
        tabbar.pack(fill='x')
        self.mode, self.tab_buttons = '装備セット', {}
        for name in ('装備セット', 'インベントリ'):
            button = ActionButton(tabbar, text=name, width=18, command=lambda n=name: self.select_tab(n))
            button.pack(side='left', padx=(0, 6))
            self.tab_buttons[name] = button
        self.pages = ttk.Frame(root)
        self.pages.pack(fill='both', expand=True)
        self.equipment_page = ttk.Frame(self.pages)
        self.equipment = EquipmentReviewMock(root, parent=self.equipment_page, data=self.data, show_properties=True)
        self.inventory = InventoryPropertiesMock(self.pages, self.data, self.compare_item)
        root.title('アイテムの性能を見ながら操作 — 列を使う案')
        self.select_tab('装備セット')

    def select_tab(self, mode):
        self.mode = mode
        self.equipment_page.pack_forget(); self.inventory.pack_forget()
        (self.equipment_page if mode == '装備セット' else self.inventory).pack(fill='both', expand=True)
        for name, button in self.tab_buttons.items():
            button.configure(style='Selected.TButton' if name == mode else 'TButton')

    def compare_item(self, key):
        self.select_tab('装備セット')
        self.equipment.select_slot(self.data.items[key].slot)
        self.equipment.candidates.selection_set(key)
        self.equipment.candidates.see(key)
        self.equipment.preview_candidate()


def main():
    root = tk.Tk()
    ItemPropertiesMock(root)
    root.mainloop()


if __name__ == '__main__':
    main()
