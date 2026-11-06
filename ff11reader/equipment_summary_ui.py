"""Always-visible equipment totals and an unsaved candidate comparison."""
import tkinter as tk
from tkinter import ttk
from .theme import BG, FG, PANEL, SELECT, MUTED, ACCENT, WARNING
from .ui_actions import ActionButton
from .equipment_stats import summarize
from .equipment_stats_presentation import GROUPS, comparison, display_totals, number


class EquipmentSummary:
    def __init__(self, parent):
        self.frame = ttk.Frame(parent)
        top = ttk.Frame(self.frame)
        top.pack(fill='x')
        ttk.Label(top, text='装備の加算値', font=('Yu Gothic UI', 12, 'bold')).pack(side='left')
        ActionButton(top, text='全項目・内訳', command=self.details).pack(side='right')
        ttk.Label(self.frame, text='上限適用前 / キャラの基礎値を含まない', style='Muted.TLabel').pack(anchor='w')
        self.comparison_label = ttk.Label(self.frame, foreground=ACCENT, width=1, anchor='w')
        self.comparison_label.pack(fill='x', pady=(2, 4))
        tables = ttk.Frame(self.frame)
        tables.pack(fill='x')
        columns = [tk.Frame(tables, bg=PANEL) for _ in range(2)]
        for index, column in enumerate(columns):
            tables.columnconfigure(index, weight=1, uniform='stats')
            column.grid(row=0, column=index, sticky='new', padx=(0, 5) if index == 0 else (5, 0))
            column.columnconfigure(0, weight=1)
            for col in (1, 2, 3):
                column.columnconfigure(col, minsize=61)
        positions = [0, 0]
        self.metric_labels = {}
        for title, column, metrics in GROUPS:
            parent, row = columns[column], positions[column]
            for col, label in enumerate((title, '現在', '候補', '差分')):
                tk.Label(parent, text=label, bg=BG, fg=MUTED, font=('Yu Gothic UI', 9, 'bold'),
                         anchor='w' if col == 0 else 'e').grid(row=row, column=col, sticky='ew', padx=3,
                                                            pady=(5 if row else 0, 2))
            for name, unit, label in metrics:
                row += 1
                cells = []
                for col in range(4):
                    cell = tk.Label(parent, text=label if col == 0 else '', bg=PANEL, fg=FG,
                                    anchor='w' if col == 0 else 'e', font=('Yu Gothic UI', 10), pady=0)
                    cell.grid(row=row, column=col, sticky='ew', padx=3)
                    cells.append(cell)
                self.metric_labels[name, unit] = cells
            positions[column] = row + 1
        self.note = ttk.Label(self.frame, wraplength=600, foreground=WARNING)
        self.note.pack(anchor='w', pady=(6, 0))
        self.result = self.trial_result = None

    def show(self, equipset, items, observation, names=None):
        self.equipset, self.items, self.observation = equipset, items, observation
        self.names = names
        self.result = summarize(equipset, items, observation, names)
        self.clear_candidate()
        self.frame.pack(fill='both', expand=True)

    def hide(self):
        self.frame.pack_forget()

    def clear_candidate(self):
        self.trial_result = None
        if self.result is not None:
            self.render('候補を選ぶと現在との差分を表示')

    def show_candidate(self, equipset, label):
        self.trial_result = summarize(equipset, self.items, self.observation, self.names)
        self.render('候補: ' + label + ('（既知分のみ）' if self.trial_result.incomplete else ''))

    def render(self, label):
        self.comparison_label.configure(text=label)
        rows = comparison(self.result, self.trial_result)
        for key, values in rows.items():
            cells = self.metric_labels[key]
            for cell, value in zip(cells[1:], values):
                cell.configure(text=value)
            changed = self.trial_result is not None and values[2] != '±0'
            cells[2].configure(bg=SELECT if changed else PANEL)
            cells[3].configure(fg=WARNING if values[2] == '未確定' else ACCENT if changed else MUTED)
        def coverage(report):
            return ('既知分のみ・' if report.incomplete else '') + f'集計外 {len(report.excluded)}件'
        text = '現在: ' + coverage(self.result)
        if self.trial_result:
            text += ' / 候補: ' + coverage(self.trial_result)
        self.note.configure(text=text)

    def details_text(self):
        lines = []
        for title, report in (('現在', self.result), ('候補', self.trial_result)):
            if report is None:
                continue
            lines.append(title + ' — 上限適用前の装備加算値' + ('（既知分のみ）' if report.incomplete else ''))
            lines.extend(f'{name}  {number(value, unit)}' for name, unit, value in display_totals(report.totals))
            lines.extend(('', '集計に使った原文'))
            lines.extend(f'{source}: {line}' for source, line in report.included)
            lines.extend(('', '集計外'))
            lines.extend(f'{source}: {line}' for source, line in report.excluded)
            lines.append('')
        return '\n'.join(lines)

    def details(self):
        if self.result is None:
            return
        window = tk.Toplevel(self.frame, background=BG)
        window.title('装備加算値の内訳'); window.geometry('800x620')
        text = tk.Text(window, bg=PANEL, fg=FG, wrap='word', padx=12, pady=12)
        bar = ttk.Scrollbar(window, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y'); text.pack(fill='both', expand=True)
        text.insert('1.0', self.details_text()); text.configure(state='disabled')
        window.bind('<Escape>', lambda e: window.destroy())


def operation_menu(parent,buttons):
    """Menu delegates to existing ActionButtons, preserving state and busy behavior."""
    menu=tk.Menu(parent,tearoff=False,bg=PANEL,fg=FG,activebackground=SELECT)
    groups={name:tk.Menu(menu,tearoff=False,bg=PANEL,fg=FG,activebackground=SELECT) for name in ('編集','確認・補正','個体情報','作業')}
    entries=[]
    for button in buttons:
        label=button.cget('text')
        group='個体情報' if '個体情報' in label else '作業' if 'リセット' in label else '確認・補正' if any(x in label for x in ('確認','補正','未参照')) else '編集'
        child=groups[group];index=child.index('end');index=0 if index is None else index+1
        child.add_command(label=label,command=button.invoke)
        entries.append((child,index,button))
        button.pack_forget()
    def sync():
        for child,index,button in entries:child.entryconfigure(index,state='disabled' if button.instate(['disabled']) else 'normal')
    for name,child in groups.items():
        child.configure(postcommand=sync);menu.add_cascade(label=name,menu=child)
    menu.configure(postcommand=sync)
    control=ttk.Menubutton(parent,text='操作 ▾',menu=menu);control.pack(side='left',padx=8)
    return control,menu
