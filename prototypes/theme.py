"""Prototype palette matching the selected light HTML mock."""
import tkinter as tk
from tkinter import ttk
from ff11reader import dialogs

from ff11reader.theme import BG, PANEL, FG, MUTED, SELECT, ACCENT, BORDER, install, recolor


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
