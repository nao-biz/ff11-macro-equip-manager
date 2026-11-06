"""Inline slot candidates, with ephemeral selection and explicit edit preview."""
import tkinter as tk
from tkinter import ttk
from .equipment_editing import search_rows
from .ui_actions import ActionButton


class EquipmentPicker:
    def __init__(self, parent, title, slot, rows, items, bags, on_preview, *, on_select, on_cancel,
                 on_details, augment_path):
        self.window = ttk.Frame(parent)
        self.window.pack(fill='both', expand=True)
        self.slot_name, self.slot = slot.name, slot
        self.rows, self.items, self.bags = rows, items, bags
        self.on_preview, self.on_select, self.on_cancel = on_preview, on_select, on_cancel
        self.augment_path = augment_path
        self.action = tk.StringVar(self.window, value='equip')
        self.query = tk.StringVar(self.window)
        self.visible = []
        self.title = ttk.Label(self.window, text=title, font=('Yu Gothic UI', 11, 'bold'))
        self.title.pack(anchor='w', pady=(2, 4))
        search = ttk.Frame(self.window)
        search.pack(fill='x', pady=(0, 4))
        ttk.Label(search, text='名前・種類ID').pack(side='left')
        self.entry = ttk.Entry(search, textvariable=self.query, width=16)
        self.entry.pack(side='left', fill='x', expand=True, padx=6)
        ActionButton(search, text='装備・判定の詳細', command=on_details).pack(side='right')
        controls = ttk.Frame(self.window)
        controls.pack(side='bottom', fill='x', pady=(6, 0))
        self.preview_button = ActionButton(controls, busy=True, text='変更案を確認',
                                          style='Primary.TButton', command=self.preview, state='disabled')
        self.preview_button.pack(side='right')
        ActionButton(controls, text='候補を解除', command=self.cancel).pack(side='right', padx=6)
        self.count = ttk.Label(controls, style='Muted.TLabel')
        self.count.pack(side='left')
        frame = ttk.Frame(self.window)
        frame.pack(fill='both', expand=True)
        self.listing = ttk.Treeview(frame, columns=('name', 'augment', 'bag'), show='headings',
                                   selectmode='browse', style='Mock.Treeview', height=4)
        for key, label, width, stretch in (('name', '装備名', 150, True), ('augment', 'Path', 52, False),
                                          ('bag', '収納・位置', 150, False)):
            self.listing.heading(key, text=label)
            self.listing.column(key, width=width, minwidth=width, stretch=stretch)
        bar = ttk.Scrollbar(frame, command=self.listing.yview)
        self.listing.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y'); self.listing.pack(fill='both', expand=True)
        self.listing.bind('<<TreeviewSelect>>', self.select)
        self.window.bind('<Escape>', lambda e: self.cancel())
        self.query_trace = self.query.trace_add('write', lambda *_: self.filter())
        self.window.bind('<Destroy>', self.release)
        self.filter()

    def chosen(self):
        selected = self.listing.selection()
        if not selected:
            return None, None
        key = selected[0]
        if key in ('keep', 'remove'):
            return key, None
        row = self.visible[int(key)]
        return 'equip', (row.item_id, row.container, row.index)

    def filter(self):
        previous = self.chosen() if self.listing.get_children() else (None, None)
        self.visible = list(search_rows(self.rows, self.items, self.query.get()))
        self.listing.delete(*self.listing.get_children())
        for index, row in enumerate(self.visible):
            name = self.items.get(row.item_id, {}).get('name') or f'ID {row.item_id}'
            self.listing.insert('', 'end', iid=str(index), values=(name, self.augment_path(row),
                                f'{self.bags.get(row.container, row.container)} / {row.index}'))
        for action, label in (('remove', '装備を外す'), ('keep', '変更しない')):
            self.listing.insert('', 'end', iid=action, values=(label, '', ''))
        self.count.configure(text=f'候補 {len(self.visible)}件')
        self._select_identity(*previous)
        self.select()

    def _select_identity(self, action, identity):
        if action in ('keep', 'remove'):
            self.listing.selection_set(action)
        elif action == 'equip':
            for index, row in enumerate(self.visible):
                if (row.item_id, row.container, row.index) == identity:
                    self.listing.selection_set(str(index)); self.listing.see(str(index)); break

    def select(self, event=None):
        action, identity = self.chosen()
        self.action.set(action or 'equip')
        unchanged = action == self.slot.action and identity == ((self.slot.item_id, self.slot.container, self.slot.index)
                                                               if action == 'equip' else None)
        self.preview_button.configure(state='disabled' if action is None or unchanged else 'normal')
        if action is None:
            self.on_cancel()
        else:
            selected = self.listing.selection()[0]
            label = ' / '.join(str(v) for v in self.listing.item(selected, 'values') if v)
            self.on_select(action, identity, label)

    def cancel(self):
        self.listing.selection_remove(*self.listing.selection())
        self.select()

    def preview(self):
        action, identity = self.chosen()
        if action is not None:
            self.on_preview(action, identity, self.window)

    def input_state(self):
        action, identity = self.chosen()
        return dict(action=action, query=self.query.get(), selected=identity)

    def restore_input(self, state):
        self.query.set(state['query'])
        self._select_identity(state['action'], state['selected'])
        self.select()

    def release(self, event):
        if event.widget == self.window:
            self.query.trace_remove('write', self.query_trace)
            self.on_preview = self.on_select = self.on_cancel = self.augment_path = None

    def destroy(self):
        self.window.destroy()
