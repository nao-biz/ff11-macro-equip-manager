"""Prototype palette matching the selected light HTML mock."""
import tkinter as tk
from tkinter import ttk
from ff11reader import dialogs

BG = '#f2f4f7'
PANEL = '#ffffff'
FG = '#273448'
MUTED = '#637084'
SELECT = '#e8f0fb'
ACCENT = '#2b5d98'
BORDER = '#d5dce6'


def install(root):
    root.configure(bg=BG)
    root.option_add('*Font', ('Yu Gothic UI', 10))
    root.option_add('*TCombobox*Listbox.background', PANEL)
    root.option_add('*TCombobox*Listbox.foreground', FG)
    root.option_add('*TCombobox*Listbox.selectBackground', SELECT)
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=FG, font=('Yu Gothic UI', 10))
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=FG)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background=PANEL, foreground=FG, padding=(10, 7),
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=BORDER, focuscolor=ACCENT)
    style.map('TButton', background=[('disabled', BG), ('pressed', SELECT), ('active', SELECT)],
              foreground=[('disabled', MUTED), ('pressed', FG), ('active', FG)],
              bordercolor=[('focus', ACCENT), ('active', ACCENT)])
    style.configure('Selected.TButton', background=SELECT, foreground=ACCENT, bordercolor=ACCENT)
    style.map('Selected.TButton', background=[('active', SELECT), ('!active', SELECT)],
              foreground=[('active', ACCENT), ('!active', ACCENT)])
    style.configure('Primary.TButton', background=ACCENT, foreground=PANEL)
    style.map('Primary.TButton', background=[('active', '#224d80'), ('!active', ACCENT)],
              foreground=[('active', PANEL), ('!active', PANEL)])
    style.configure('TEntry', fieldbackground=PANEL, foreground=FG, insertcolor=FG,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=BORDER, padding=6)
    style.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=FG,
                    arrowcolor=MUTED, bordercolor=BORDER, padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', FG)])
    style.configure('Mock.Treeview', background=PANEL, fieldbackground=PANEL, foreground=FG,
                    rowheight=32, borderwidth=0)
    style.map('Mock.Treeview', background=[('selected', SELECT)], foreground=[('selected', ACCENT)])
    style.configure('Mock.Treeview.Heading', background=BG, foreground=MUTED, padding=8)
    style.map('Mock.Treeview.Heading', background=[('active', SELECT)], foreground=[('active', FG)])
    style.configure('TScrollbar', background=BORDER, troughcolor=BG, arrowcolor=MUTED,
                    bordercolor=BG)
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('Pages.TNotebook', background=BG, borderwidth=0, tabmargins=0)


def recolor(widget):
    """Apply the prototype palette to classic Tk controls in shared popups."""
    options = widget.keys()
    updates = {}
    for key, value in [('background', PANEL), ('foreground', FG), ('insertbackground', FG),
                       ('selectbackground', SELECT), ('selectforeground', ACCENT),
                       ('activebackground', SELECT), ('activeforeground', FG),
                       ('highlightbackground', BORDER), ('highlightcolor', ACCENT)]:
        if key in options:
            updates[key] = value
    if updates:
        widget.configure(**updates)
    for child in widget.winfo_children():
        recolor(child)


def askyesno(title, message, *, parent, accept_label=None):
    modal = dialogs.Modal(parent, title, message, 'confirm', accept_label='はい')
    modal.cancel_button.configure(text='いいえ')
    recolor(modal.layer)
    return modal.wait()


def showwarning(title, message, *, parent):
    modal = dialogs.Modal(parent, title, message, 'warning')
    recolor(modal.layer)
    return modal.wait()


class TabBar(ttk.Frame):
    def __init__(self, parent, notebook):
        super().__init__(parent, padding=(16, 0))
        self.notebook = notebook
        self.buttons = []
        self.indicators = []
        for i, label in enumerate(('マクロ', '装備セット', 'インベントリ')):
            cell = tk.Frame(self, bg=BG)
            cell.pack(side='left', padx=(0, 4))
            button = tk.Button(cell, text=label, width=15, pady=10, borderwidth=0,
                               bg=BG, fg=FG, activebackground=SELECT, activeforeground=FG,
                               highlightthickness=1, highlightbackground=BG, highlightcolor=ACCENT,
                               command=lambda index=i: notebook.select(index))
            button.pack(fill='x')
            indicator = tk.Frame(cell, height=3, bg=BG)
            indicator.pack(fill='x')
            self.buttons.append(button)
            self.indicators.append(indicator)
        notebook.bind('<<NotebookTabChanged>>', self.refresh, add='+')
        self.refresh()

    def refresh(self, event=None):
        selected = self.notebook.index('current')
        for i, (button, indicator) in enumerate(zip(self.buttons, self.indicators)):
            button.configure(bg=SELECT if i == selected else BG, fg=ACCENT if i == selected else FG)
            indicator.configure(bg=ACCENT if i == selected else BG)
