"""Read-only properties beside inventory selection."""
import tkinter as tk
from tkinter import ttk
from . import theme
from .item_properties import ItemProperties


class ItemPropertyPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.title = ttk.Label(self, font=('Yu Gothic UI', 12, 'bold'))
        self.title.pack(fill='x')
        self.identity = ttk.Label(self, style='Muted.TLabel')
        self.identity.pack(fill='x', pady=(2, 6))
        self.bind('<Configure>', self.resize)
        columns = ttk.Frame(self)
        columns.pack(fill='both', expand=True)
        columns.columnconfigure(0, weight=3, uniform='properties')
        columns.columnconfigure(1, weight=2, uniform='properties')
        columns.rowconfigure(1, weight=1)
        self.texts = []
        for col, name in enumerate(('装備本体', 'オーグメント')):
            color = theme.FG if col == 0 else theme.REVIEW
            ttk.Label(columns, text=name, foreground=color).grid(row=0, column=col, sticky='w')
            frame = ttk.Frame(columns)
            frame.grid(row=1, column=col, sticky='nsew', padx=(0, 5) if col == 0 else (5, 0))
            bar = ttk.Scrollbar(frame)
            bar.pack(side='right', fill='y')
            text = tk.Text(frame, width=1, height=5, wrap='word', relief='flat', bg=theme.PANEL,
                           fg=color, padx=8, pady=6, font=('Yu Gothic UI', 10), yscrollcommand=bar.set,
                           selectbackground=theme.SELECT, selectforeground=theme.FG)
            text.pack(fill='both', expand=True)
            bar.configure(command=text.yview)
            self.texts.append(text)
        self.show(ItemProperties())

    def resize(self, event):
        self.title.configure(wraplength=max(1, event.width))
        self.identity.configure(wraplength=max(1, event.width))

    def show(self, properties):
        self.properties = properties
        self.title.configure(text=properties.title)
        self.identity.configure(text=properties.identity)
        for widget, value in zip(self.texts, (properties.body, properties.augments)):
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
            widget.configure(state='disabled')
            widget.yview_moveto(0)

    def contents(self):
        return tuple(widget.get('1.0', 'end-1c') for widget in self.texts)
