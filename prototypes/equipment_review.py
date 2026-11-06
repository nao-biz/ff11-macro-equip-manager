"""Native, memory-only equipment evaluation mock (VIEW-005/006, DP-06)."""
import tkinter as tk
from tkinter import ttk

from ff11reader import theme
from ff11reader.ui_actions import ActionButton
from ff11reader.equipment_stats_presentation import comparison, comparison_note, exclusion_groups
from .equipment_review_data import (
    GROUPS, SET_NAMES, SLOTS, ReviewData, incomplete, number,
)


class EquipmentReviewMock:
    def __init__(self, root):
        self.root = root
        root.title('装備セット評価 — Pythonモック')
        root.geometry('1440x900')
        root.minsize(1320, 840)
        theme.install(root)
        self.data = ReviewData()
        self.set_index = self.slot_index = 0
        self.trial_key = None
        self.history = []
        self.query = tk.StringVar()
        self.status = tk.StringVar(value='枠を選ぶ → 候補を選んで差分を見る → 適用')

        header = ttk.Frame(root, padding=(18, 12, 18, 10))
        header.pack(fill='x')
        ttk.Label(header, text='装備セット', font=('Yu Gothic UI', 17, 'bold')).pack(side='left')
        ttk.Label(header, text='画面構成の検討  /  合成データ', style='Muted.TLabel').pack(side='left', padx=18)
        ttk.Label(header, text='変更はモックを閉じるまで保持', style='Muted.TLabel').pack(side='right')
        footer = ttk.Frame(root, padding=(18, 8))
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, textvariable=self.status).pack(side='left')
        self.undo_button = ActionButton(footer, text='直前の適用を戻す', command=self.undo)
        self.undo_button.pack(side='right')
        body = ttk.Frame(root, padding=(14, 0, 14, 0))
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=4, minsize=490)
        body.columnconfigure(2, weight=6, minsize=600)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, width=134, padding=(0, 8, 8, 0))
        left.grid(row=0, column=0, sticky='nsew')
        ttk.Label(left, text='装備セット', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        self.set_list = tk.Listbox(left, width=17, height=5, exportselection=False,
                                   bg=theme.PANEL, fg=theme.FG, relief='flat',
                                   selectbackground=theme.SELECT, selectforeground=theme.ACCENT,
                                   highlightthickness=0, activestyle='none')
        for index, name in enumerate(SET_NAMES, 1):
            self.set_list.insert('end', f'{index:03}  {name}')
        self.set_list.pack(fill='x')
        self.set_list.selection_set(0)
        self.set_list.bind('<<ListboxSelect>>', self.select_set)
        ttk.Label(left, text='比較用の4例\n数値はすべて合成', style='Muted.TLabel').pack(anchor='w', pady=18)

        center = ttk.Frame(body, padding=(6, 0, 14, 0))
        center.grid(row=0, column=1, sticky='nsew')
        self.heading = ttk.Label(center, font=('Yu Gothic UI', 13, 'bold'))
        self.heading.pack(anchor='w', pady=(4, 8))
        self.gear_grid = ttk.Frame(center)
        self.gear_grid.pack(fill='x')
        self.cards = []
        for part, name in enumerate(SLOTS):
            self.gear_grid.columnconfigure(part % 4, weight=1, uniform='slot')
            cell = ttk.Frame(self.gear_grid, height=78)
            cell.grid(row=part // 4, column=part % 4, sticky='nsew', padx=2, pady=2)
            cell.grid_propagate(False)
            cell.columnconfigure(0, weight=1)
            cell.rowconfigure(0, weight=1)
            button = ActionButton(cell, width=1, padding=(4, 6), command=lambda p=part: self.select_slot(p))
            button.grid(row=0, column=0, sticky='nsew')
            button.bind('<Double-Button-1>', lambda e, p=part: self.focus_candidates(p))
            self.cards.append(button)
        ttk.Separator(center).pack(fill='x', pady=(12, 8))
        self.candidate_title = ttk.Label(center, font=('Yu Gothic UI', 12, 'bold'))
        self.candidate_title.pack(anchor='w')
        self.current_item = ttk.Label(center, style='Muted.TLabel')
        self.current_item.pack(anchor='w', pady=(2, 8))
        search = ttk.Frame(center)
        search.pack(fill='x', pady=(0, 6))
        ttk.Label(search, text='候補を絞る').pack(side='left', padx=(0, 8))
        self.search_entry = ttk.Entry(search, textvariable=self.query)
        self.search_entry.pack(side='left', fill='x', expand=True)
        ActionButton(search, text='原文・個体詳細', command=self.show_item_details).pack(side='right', padx=(8, 0))
        self.candidates_panel = ttk.Frame(center)
        self.candidates_panel.pack(fill='both', expand=True)
        self.candidates = ttk.Treeview(self.candidates_panel, columns=('name', 'path', 'state'),
                                      show='headings', height=6, selectmode='browse', style='Mock.Treeview')
        for key, label, width, stretch in (('name', '装備名', 172, True), ('path', 'Path', 46, False),
                                           ('state', '個体・取得状態', 194, False)):
            self.candidates.heading(key, text=label)
            self.candidates.column(key, width=width, minwidth=width, stretch=stretch)
        self.candidates.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(self.candidates_panel, command=self.candidates.yview)
        scrollbar.pack(side='right', fill='y')
        self.candidates.configure(yscrollcommand=scrollbar.set)
        self.candidates.bind('<<TreeviewSelect>>', self.preview_candidate)
        actions = ttk.Frame(center, padding=(0, 8, 0, 0))
        actions.pack(fill='x')
        self.apply_button = ActionButton(actions, text='この候補を適用', style='Primary.TButton', command=self.apply_candidate)
        self.apply_button.pack(side='right')
        self.cancel_button = ActionButton(actions, text='候補を解除', command=self.cancel_candidate)
        self.cancel_button.pack(side='right', padx=8)
        ttk.Label(actions, text='選択だけでは変更しません', style='Muted.TLabel').pack(side='left')

        self.summary = ttk.Frame(body, padding=(10, 4, 0, 0))
        self.summary.grid(row=0, column=2, sticky='nsew')
        top = ttk.Frame(self.summary)
        top.pack(fill='x')
        ttk.Label(top, text='装備の加算値', font=('Yu Gothic UI', 13, 'bold')).pack(side='left')
        ActionButton(top, text='全項目・内訳', command=self.show_report).pack(side='right')
        ttk.Label(self.summary, text='上限適用前  /  キャラの基礎値を含まない', style='Muted.TLabel').pack(anchor='w', pady=(2, 4))
        self.comparison_title = ttk.Label(self.summary, foreground=theme.ACCENT)
        self.comparison_title.pack(anchor='w', pady=(0, 6))
        tables = ttk.Frame(self.summary)
        tables.pack(fill='x')
        tables.columnconfigure(0, weight=1, uniform='stats')
        tables.columnconfigure(1, weight=1, uniform='stats')
        columns = [tk.Frame(tables, bg=theme.PANEL) for _ in range(2)]
        for i, frame in enumerate(columns):
            frame.grid(row=0, column=i, sticky='new', padx=(0, 7) if i == 0 else (7, 0))
            frame.columnconfigure(0, weight=1)
            for col in (1, 2, 3):
                frame.columnconfigure(col, minsize=61)
        self.metric_labels = {}
        positions = [0, 0]
        for title, column, metrics in GROUPS:
            frame, row = columns[column], positions[column]
            for col, label in enumerate((title, '現在', '候補', '差分')):
                heading = tk.Label(frame, text=label, bg=theme.BG, fg=theme.MUTED,
                                   font=('Yu Gothic UI', 9, 'bold'), anchor='w' if col == 0 else 'e')
                heading.grid(row=row, column=col, sticky='ew', pady=(6 if row else 0, 3), padx=4)
            for name, unit, label in metrics:
                row += 1
                cells = []
                for col in range(4):
                    cell = tk.Label(frame, text=label if col == 0 else '', bg=theme.PANEL,
                                    fg=theme.FG, anchor='w' if col == 0 else 'e',
                                    font=('Yu Gothic UI', 10), pady=1)
                    cell.grid(row=row, column=col, sticky='ew', padx=4)
                    cells.append(cell)
                self.metric_labels[name, unit] = cells
            positions[column] = row + 1
        self.coverage = ttk.Label(self.summary, foreground=theme.WARNING)
        self.coverage.pack(anchor='w', pady=(12, 3))
        ttk.Label(self.summary, text='集計外の効果は内訳で確認。未取得がある比較は差分を「未確定」と表示。',
                  style='Muted.TLabel', wraplength=570).pack(anchor='w')
        self.query.trace_add('write', lambda *_: self.filter_candidates())
        self.render()

    @property
    def selection(self):
        return self.data.sets[self.set_index]

    def render(self):
        self.heading.configure(text=f'{self.set_index + 1:03}  {SET_NAMES[self.set_index]}')
        for part, (key, button) in enumerate(zip(self.selection, self.cards)):
            item = self.data.items.get(key)
            name = item.name if item else ('変更しない' if key == 'keep' else '装備なし')
            path = f'Path {item.path}' if item else ' '
            button.configure(text=f'{SLOTS[part]}\n{name}\n{path}',
                             style='Selected.TButton' if part == self.slot_index else 'TButton')
        self.candidate_title.configure(text=f'{SLOTS[self.slot_index]}の候補')
        self.current_item.configure(text='現在: ' + self.data.label(self.selection[self.slot_index]))
        self.filter_candidates()
        self.undo_button.configure(state='normal' if self.history else 'disabled')

    def select_set(self, event=None):
        selected = self.set_list.curselection()
        if selected and selected[0] != self.set_index:
            self.set_index = selected[0]
            self.trial_key = None
            self.query.set('')
            self.render()

    def select_slot(self, part):
        self.slot_index = part
        self.trial_key = None
        self.query.set('')
        self.render()

    def focus_candidates(self, part):
        self.select_slot(part)
        self.candidates.focus_set()
        return 'break'

    def filter_candidates(self):
        previous = self.trial_key
        self.candidates.delete(*self.candidates.get_children())
        query = self.query.get().casefold().strip()
        for key, item in self.data.items.items():
            if item.slot != self.slot_index or query not in item.label.casefold():
                continue
            state = f'収納1 #{item.position}  ' + ('取得済み' if item.decoded else 'オグメ未取得')
            if key == self.selection[self.slot_index]:
                state = '装備中 / ' + state
            self.candidates.insert('', 'end', iid=key, values=(item.name, item.path, state))
        for key, name in (('remove', '装備を外す'), ('keep', '変更しない')):
            if not query or query in name:
                self.candidates.insert('', 'end', iid=key, values=(name, '', '未確定' if key == 'keep' else '加算なし'))
        if previous is not None and self.candidates.exists(previous):
            self.candidates.selection_set(previous)
        else:
            self.trial_key = None
        self.refresh_summary()

    def preview_candidate(self, event=None):
        selected = self.candidates.selection()
        self.trial_key = selected[0] if selected else None
        self.refresh_summary()

    def refresh_summary(self):
        self.current_report = self.data.report(self.selection)
        trial = list(self.selection)
        if self.trial_key is not None:
            trial[self.slot_index] = self.trial_key
        self.trial_report = self.data.report(trial) if self.trial_key is not None else None
        rows = comparison(self.current_report, self.trial_report)
        for key, (_, now, after, change) in self.metric_labels.items():
            value, candidate, delta = rows[key]
            now.configure(text=value)
            after.configure(text=candidate)
            changed = self.trial_report is not None and delta not in ('±0', '±0*')
            change.configure(text=delta,
                             fg=theme.WARNING if delta == '未確定' or delta.endswith('*') else theme.ACCENT if changed else theme.MUTED)
            after.configure(bg=theme.SELECT if changed else theme.PANEL)
        label = self.data.label(self.trial_key) if self.trial_key is not None else '下の一覧で候補を選ぶと差分を表示'
        if self.trial_report and incomplete(self.trial_report):
            label += '（候補は既知分のみ）'
        self.comparison_title.configure(text='比較: ' + label)
        def coverage(report):
            return ('既知分のみ・' if incomplete(report) else '') + f'集計外 {len(report.excluded)}件'
        text = '現在: ' + coverage(self.current_report)
        if self.trial_report:
            text += '   /   候補: ' + coverage(self.trial_report)
        note = comparison_note(self.current_report, self.trial_report)
        if note:
            text += '\n' + note
        self.coverage.configure(text=text, foreground=theme.WARNING if note or self.current_report.incomplete or
                                (self.trial_report and self.trial_report.incomplete) else theme.MUTED)
        changed = self.trial_key is not None and self.trial_key != self.selection[self.slot_index]
        self.apply_button.configure(state='normal' if changed else 'disabled')
        self.cancel_button.configure(state='normal' if self.trial_key is not None else 'disabled')

    def cancel_candidate(self):
        self.trial_key = None
        self.candidates.selection_remove(*self.candidates.selection())
        self.refresh_summary()
        self.status.set('候補を解除しました。現在の装備を表示しています。')

    def apply_candidate(self):
        if self.trial_key is None or self.trial_key == self.selection[self.slot_index]:
            return
        self.history.append((self.set_index, self.slot_index, self.selection[self.slot_index]))
        self.selection[self.slot_index] = self.trial_key
        self.status.set(f'{SLOTS[self.slot_index]}に {self.data.label(self.trial_key)} を適用しました。')
        self.trial_key = None
        self.render()

    def undo(self):
        if not self.history:
            return
        self.set_index, self.slot_index, previous = self.history.pop()
        self.selection[self.slot_index] = previous
        self.trial_key = None
        self.query.set('')
        self.set_list.selection_clear(0, 'end')
        self.set_list.selection_set(self.set_index)
        self.status.set('直前の適用を戻しました。')
        self.render()

    def show_text(self, title, text):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry('800x620')
        window.transient(self.root)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill='both', expand=True)
        ActionButton(frame, text='閉じる', command=window.destroy).pack(side='bottom', anchor='e', pady=(8, 0))
        scroll = ttk.Scrollbar(frame)
        scroll.pack(side='right', fill='y')
        view = tk.Text(frame, wrap='word', bg=theme.PANEL, fg=theme.FG, relief='flat',
                       padx=12, pady=12, yscrollcommand=scroll.set)
        view.pack(fill='both', expand=True)
        scroll.configure(command=view.yview)
        view.insert('1.0', text)
        view.configure(state='disabled')
        window.bind('<Escape>', lambda e: window.destroy())

    def show_item_details(self):
        key = self.trial_key if self.trial_key is not None else self.selection[self.slot_index]
        item = self.data.items.get(key)
        if item is None:
            self.show_text('個体詳細', self.data.label(key))
            return
        self.show_text('個体詳細 — 合成データ',
                       item.label + f'\nワードローブ1 / 位置 {item.position}\n\n装備本体\n'
                       + (item.description or '未取得') + '\n\nオーグメント原文\n'
                       + ('\n'.join(item.raw_augments) or '未取得')
                       + '\n\n日本語の能力値と集計の根拠は「全項目・内訳」で確認できます。')

    def report_text(self):
        lines = []
        for title, report in (('現在', self.current_report), ('候補', self.trial_report)):
            if report is None:
                continue
            lines.extend((title + ' — 上限適用前の装備加算値', '既知分のみ' if incomplete(report) else ''))
            lines.extend(f'{name}  {number(value, unit)}' for name, unit, value in report.totals)
            for heading, entries in exclusion_groups(report):
                if entries:
                    lines.extend(('', heading))
                    lines.extend(f'{source}: {line}' for source, line in entries)
            lines.extend(('', '集計に使った内訳（合成入力）'))
            lines.extend(f'{source}: {line}' for source, line in report.included)
            lines.append('\n')
        return '\n'.join(lines)

    def show_report(self):
        self.show_text('全項目・内訳 — 合成データ', self.report_text())


def main():
    root = tk.Tk()
    EquipmentReviewMock(root)
    root.mainloop()


if __name__ == '__main__':
    main()
