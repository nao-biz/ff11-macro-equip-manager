"""Shared native workspace palette and fixed-size navigation controls (DP-04)."""
import tkinter as tk
from tkinter import ttk

BG = '#f2f4f7'
PANEL = '#ffffff'
FG = '#273448'
MUTED = '#637084'
SELECT = '#e8f0fb'
ACCENT = '#2b5d98'
BORDER = '#d5dce6'
SUCCESS = '#287248'
WARNING = '#946000'
DANGER = '#b33737'
REVIEW = '#79529a'
GEAR_HEIGHT = 104


def install(root):
    root.configure(bg=BG)
    root.option_add('*Font', ('Yu Gothic UI', 10))
    for name, color in (('background', PANEL), ('foreground', FG),
                        ('selectBackground', SELECT), ('selectForeground', ACCENT)):
        root.option_add('*TCombobox*Listbox.' + name, color)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=FG, font=('Yu Gothic UI', 10))
    style.configure('TFrame', background=BG)
    style.configure('Game.TFrame', background=BG, relief='flat', borderwidth=0)
    style.configure('TLabel', background=BG, foreground=FG)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background=PANEL, foreground=FG, padding=(10, 5),
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=BORDER, focuscolor=ACCENT)
    style.map('TButton', background=[('disabled', BG), ('pressed', SELECT), ('active', SELECT)],
              foreground=[('disabled', MUTED), ('pressed', FG), ('active', FG)],
              bordercolor=[('focus', ACCENT), ('active', ACCENT)])
    style.configure('Selected.TButton', background=SELECT, foreground=ACCENT, bordercolor=ACCENT)
    style.map('Selected.TButton', background=[('!disabled', SELECT)], foreground=[('!disabled', ACCENT)])
    style.configure('Primary.TButton', background=ACCENT, foreground=PANEL)
    style.map('Primary.TButton', background=[('disabled', BORDER), ('active', '#224d80'), ('!active', ACCENT)],
              foreground=[('disabled', MUTED), ('!disabled', PANEL)])
    style.configure('TEntry', fieldbackground=PANEL, foreground=FG, insertcolor=FG,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=BORDER, padding=6)
    style.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=FG,
                    arrowcolor=MUTED, bordercolor=BORDER, padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', FG)])
    for name in ('TRadiobutton', 'Game.TRadiobutton'):
        style.configure(name, background=BG, foreground=FG, padding=(6, 4))
        style.map(name, background=[('active', SELECT)], foreground=[('disabled', MUTED)])
    for name in ('Macro.Treeview', 'Mock.Treeview'):
        style.configure(name, background=PANEL, fieldbackground=PANEL, foreground=FG,
                        rowheight=30, borderwidth=0)
        style.map(name, background=[('selected', SELECT)], foreground=[('selected', ACCENT)])
        style.configure(name + '.Heading', background=BG, foreground=MUTED, padding=6)
        style.map(name + '.Heading', background=[('active', SELECT)], foreground=[('active', FG)])
    style.configure('TScrollbar', background=BORDER, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
    style.configure('TPanedwindow', background=BG)
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('Pages.TNotebook', background=BG, borderwidth=0, tabmargins=0)


def recolor(widget):
    options = widget.keys()
    values = dict(background=PANEL, foreground=FG, insertbackground=FG,
                  selectbackground=SELECT, selectforeground=ACCENT, activebackground=SELECT,
                  activeforeground=FG, highlightbackground=BORDER, highlightcolor=ACCENT)
    updates = {key: value for key, value in values.items() if key in options}
    if updates:
        widget.configure(**updates)
    for child in widget.winfo_children():
        recolor(child)


class ModeTabs(ttk.Frame):
    def __init__(self, parent, variable, command):
        super().__init__(parent, padding=(16, 0))
        self.variable, self.command = variable, command
        self.buttons, self.indicators = {}, {}
        for label in ('マクロ', '装備セット', 'インベントリ'):
            cell = tk.Frame(self, bg=BG)
            cell.pack(side='left', padx=(0, 4))
            button = tk.Button(cell, text=label, width=15, pady=7, borderwidth=0,
                               bg=BG, fg=FG, activebackground=SELECT, activeforeground=FG,
                               highlightthickness=1, highlightbackground=BG, highlightcolor=ACCENT,
                               command=lambda mode=label: self.select(mode))
            button.pack(fill='x')
            indicator = tk.Frame(cell, height=3, bg=BG)
            indicator.pack(fill='x')
            self.buttons[label], self.indicators[label] = button, indicator
        self.refresh()

    def select(self, mode):
        if mode != self.variable.get():
            self.variable.set(mode)
            self.command()
        self.refresh()

    def refresh(self):
        for label, button in self.buttons.items():
            selected = label == self.variable.get()
            button.configure(bg=SELECT if selected else BG, fg=ACCENT if selected else FG)
            self.indicators[label].configure(bg=ACCENT if selected else BG)
