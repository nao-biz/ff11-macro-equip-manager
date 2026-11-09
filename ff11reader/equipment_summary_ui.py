"""Always-visible equipment totals and an unsaved candidate comparison."""
from . import dialogs
import tkinter as tk
from tkinter import ttk
from .theme import BG, FG, PANEL, SELECT, MUTED, ACCENT, WARNING, DANGER, REVIEW
from .ui_actions import ActionButton
from .equipment_stats import summarize
from .equipment_stats_presentation import GROUPS, comparison, comparison_note, display_totals, exclusion_groups, number
from .item_properties import describe_item, summarize_item, other_properties


class EquipmentSummary:
    def __init__(self, parent, bags=None):
        self.bags = bags
        self.selected_slot = None
        self.frame = ttk.Frame(parent)
        top = ttk.Frame(self.frame)
        top.pack(fill='x')
        ttk.Label(top, text='装備の加算値（上限前）', font=('Yu Gothic UI', 12, 'bold')).pack(side='left')
        ActionButton(top, text='全項目・内訳', command=self.details).pack(side='right')
        self.comparison_label = ttk.Label(self.frame, foreground=REVIEW, width=1, anchor='w')
        self.comparison_label.pack(fill='x', pady=(2, 2))
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
        self.value_headers = []
        for title, column, metrics in GROUPS:
            parent, row = columns[column], positions[column]
            for col, label in enumerate((title, '現在計', '選択装備', '差分')):
                heading = tk.Label(parent, text=label, bg=BG, fg=REVIEW if col == 2 else MUTED,
                                   font=('Yu Gothic UI', 9, 'bold'), anchor='w' if col == 0 else 'e')
                heading.grid(row=row, column=col, sticky='ew', padx=3, pady=(2 if row else 0, 0))
                if col == 2:
                    self.value_headers.append(heading)
            for name, unit, label in metrics:
                row += 1
                cells = []
                for col in range(4):
                    cell = tk.Label(parent, text=label if col == 0 else '', bg=PANEL, fg=FG,
                                    anchor='w' if col == 0 else 'e', font=('Yu Gothic UI', 10), pady=0, borderwidth=0)
                    cell.grid(row=row, column=col, sticky='ew', padx=3)
                    cells.append(cell)
                self.metric_labels[name, unit] = cells
            positions[column] = row + 1
        self.note = ttk.Label(self.frame, wraplength=600, foreground=WARNING)
        self.note.pack(anchor='w', pady=(2, 2))
        ttk.Label(self.frame, text='選択装備のその他の性能・効果', foreground=REVIEW).pack(anchor='w')
        extra = ttk.Frame(self.frame)
        extra.pack(fill='both', expand=True)
        bar = ttk.Scrollbar(extra)
        bar.pack(side='right', fill='y')
        self.extra_properties = tk.Text(extra, height=3, width=1, wrap='word', bg=PANEL, fg=FG,
                                        relief='flat', padx=8, pady=4, font=('Yu Gothic UI', 10),
                                        yscrollcommand=bar.set, state='disabled')
        self.extra_properties.pack(fill='both', expand=True)
        bar.configure(command=self.extra_properties.yview)
        self.result = self.trial_result = None

    def show(self, equipset, items, observation, names=None):
        self.equipset, self.items, self.observation = equipset, items, observation
        self.names = names
        self.result = summarize(equipset, items, observation, names)
        self.selected_slot = None
        self.clear_candidate()
        self.frame.pack(fill='both', expand=True)

    def hide(self):
        self.frame.pack_forget()
        self.result = self.trial_result = self.selected_slot = None

    def clear_candidate(self):
        self.trial_result = None
        if self.result is not None:
            self.render(self.selected_slot)

    def show_selected(self, slot):
        self.selected_slot = slot
        self.clear_candidate()

    def show_candidate(self, equipset, label, slot=None):
        self.trial_result = summarize(equipset, self.items, self.observation, self.names)
        if slot is None and self.selected_slot is not None:
            slot = next(s for s in equipset.slots if s.name == self.selected_slot.name)
        self.render(slot)

    def render(self, slot):
        properties = describe_item(slot, self.items, self.observation, self.names, self.bags)
        selected = summarize_item(slot, self.items, self.observation, self.names) if slot else None
        self.properties, self.selected_result = properties, selected
        label = ('比較: ' if self.trial_result else '選択装備: ') + properties.title
        self.comparison_label.configure(text=label + (' / ' + properties.identity if properties.identity else ''))
        for heading in self.value_headers:
            heading.configure(text='候補計' if self.trial_result else '選択装備')
        rows = comparison(self.result, self.trial_result)
        single = comparison(selected) if selected else {}
        for key, values in rows.items():
            cells = self.metric_labels[key]
            value, candidate, delta = values
            if self.trial_result is None:
                candidate = single[key][0] if selected else ''
                if selected and selected.incomplete and candidate != '未確定' and not candidate.endswith('*'):
                    candidate += '*'
            if self.trial_result is None or delta in ('±0', '±0*'):
                delta = ''
            cells[1].configure(text=value, fg=FG)
            cells[2].configure(text=candidate, fg=REVIEW)
            cells[3].configure(text=delta)
            changed = self.trial_result is not None and values[2] not in ('±0', '±0*')
            cells[2].configure(bg=SELECT if changed else PANEL)
            cells[3].configure(fg=DANGER if delta.startswith('-') else ACCENT if delta.startswith('+')
                               else WARNING if delta else MUTED)
        def coverage(report):
            return ('既知分のみ・' if report.incomplete else '') + f'集計外 {len(report.excluded)}件'
        text = '現在: ' + coverage(self.result)
        if self.trial_result:
            text += ' / 候補: ' + coverage(self.trial_result)
        note = comparison_note(self.result, self.trial_result)
        if note:
            text += ' / ' + note
        if self.trial_result is None and selected and selected.incomplete:
            text += ' / 選択装備は既知分（*）'
        self.note.configure(text=text, foreground=WARNING if note or self.result.incomplete or
                            (self.trial_result and self.trial_result.incomplete) else MUTED)
        text = other_properties(selected) if selected else ''
        if slot is not None and slot.action == 'equip':
            text += '\n\n本体の全プロパティ\n' + properties.body + '\n\nオーグメント\n' + properties.augments
        elif slot is not None:
            text = properties.body
        self.extra_properties.configure(state='normal')
        self.extra_properties.delete('1.0', 'end')
        self.extra_properties.insert('1.0', text)
        self.extra_properties.configure(state='disabled')
        self.extra_properties.yview_moveto(0)

    def details_text(self):
        lines = []
        for title, report in (('現在', self.result), ('候補', self.trial_result)):
            if report is None:
                continue
            lines.append(title + ' — 上限適用前の装備加算値' + ('（既知分のみ）' if report.incomplete else ''))
            lines.extend(f'{name}  {number(value, unit)}' for name, unit, value in display_totals(report.totals))
            lines.extend(('', '集計に使った原文'))
            lines.extend(f'{source}: {line}' for source, line in report.included)
            for heading, entries in exclusion_groups(report):
                if entries:
                    lines.extend(('', heading))
                    lines.extend(f'{source}: {line}' for source, line in entries)
            lines.append('')
        return '\n'.join(lines)

    def details(self):
        if self.result is None:
            return
        window = tk.Toplevel(self.frame, background=BG)
        window.title('装備加算値の内訳'); window.geometry('800x620')
        dialogs.fit_to_screen(window)
        text = tk.Text(window, bg=PANEL, fg=FG, wrap='word', padx=12, pady=12)
        bar = ttk.Scrollbar(window, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y'); text.pack(fill='both', expand=True)
        text.insert('1.0', self.details_text()); text.configure(state='disabled')
        dialogs.child_navigation(window, text)


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
