"""Shared selected-item properties for the equipment/inventory layout mock."""
import tkinter as tk
from tkinter import ttk
import re
import unicodedata

from ff11reader import theme
from ff11reader.domain import Equipset, Slot, Text
from ff11reader.equipment_stat_parser import WEAPON, analyze_line
from ff11reader.equipment_stats import summarize
from ff11reader.equipment_stats_presentation import GROUPS, number

BASE_STATS = ('STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR')


def format_properties(text, names):
    """Group basic stats; give every other interpreted property its own line."""
    lines = []
    for raw in text.splitlines():
        remainder = unicodedata.normalize('NFKC', raw).strip()
        weapon = []
        while match := WEAPON.match(remainder):
            weapon.append(match[0])
            remainder = remainder[match.end():].lstrip()
        if weapon:
            lines.extend(weapon)
            if remainder:
                lines.append(format_properties(remainder, names))
            continue
        level = re.fullmatch(r'(Lv\d+[〜～~]?)\s+(.+)', raw)
        if level:
            lines.extend(level.groups())
            continue
        parsed = analyze_line(raw, names)
        if parsed.outside or parsed.unparsed or not parsed.values:
            lines.append(raw)
            continue
        for group in (('HP', 'MP'), BASE_STATS):
            values = [name + number(value, unit, signed=True) for name, unit, value in parsed.values if name in group]
            if values:
                lines.append('  '.join(values))
        lines.extend(name + number(value, unit, signed=True) for name, unit, value in parsed.values
                     if name not in ('HP', 'MP', *BASE_STATS))
    return '\n'.join(lines)


def item_report(data, key):
    item = data.items.get(key)
    slot = (Slot('main', 'equip', item.item_id, item.container, item.position, '') if item
            else Slot('main', key or 'keep', None, None, None, ''))
    return summarize(Equipset(1, Text('', '', 'cp932'), (slot,)), data.master, data.observation, data.names)


def other_properties(report):
    visible = {(name, unit) for _, _, metrics in GROUPS for name, unit, _ in metrics}
    lines = [name + number(value, unit, signed=True) for name, unit, value in report.totals
             if (name, unit) not in visible]
    lines.extend(('オグメ: ' if ' / オグメ' in source else '') + raw for source, raw in report.excluded)
    return '\n'.join(lines) or '主要項目以外の性能・効果はありません。'


def property_content(data, key, *, formatted=True):
    item = data.items.get(key)
    if item is None:
        label = {'keep': '変更しない', 'remove': '装備を外す'}.get(key, 'アイテムを選択')
        body = {'keep': '実行前の装備は未確定です。', 'remove': 'この枠は装備なしになります。'}.get(key, '')
        return label, '', body, ''
    master = data.master.get(item.item_id, {})
    slot = Slot('main', 'equip', item.item_id, item.container, item.position, '')
    observed = data.observation.item(slot) if data.observation else None
    decoded = observed is not None and observed.decode_state == 'decoded'
    path = ' / Path ' + observed.path if decoded and observed.path else ''
    identity = f'ワードローブ{item.container - 11} / 位置 {item.position}' + path
    lines = []
    if decoded:
        for raw in observed.augments:
            lines.append(format_properties(raw, data.names) if formatted else raw)
        if not lines:
            lines.append('付加能力なし')
    else:
        lines.append('オーグメント未取得')
    body = master.get('description') or '本体の説明が未取得'
    return item.name, identity, format_properties(body, data.names) if formatted else body, '\n'.join(lines)


class ItemPropertyPanel(ttk.Frame):
    def __init__(self, parent, data):
        super().__init__(parent)
        self.data, self.key = data, None
        heading = ttk.Frame(self)
        heading.pack(fill='x')
        self.context = ttk.Label(heading, foreground=theme.ACCENT, font=('Yu Gothic UI', 9, 'bold'))
        self.context.pack(side='right')
        self.title = ttk.Label(heading, font=('Yu Gothic UI', 12, 'bold'))
        self.title.pack(side='left')
        self.identity = ttk.Label(self, style='Muted.TLabel')
        self.identity.pack(anchor='w', pady=(0, 5))
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
            frame.grid(row=1, column=col, sticky='nsew', padx=(0, 6) if col == 0 else (6, 0))
            bar = ttk.Scrollbar(frame)
            bar.pack(side='right', fill='y')
            text = tk.Text(frame, width=1, height=5, wrap='word', relief='flat',
                           bg=theme.PANEL, fg=color, padx=8, pady=6,
                           font=('Yu Gothic UI', 10), yscrollcommand=bar.set,
                           selectbackground=theme.SELECT, selectforeground=theme.FG)
            text.pack(fill='both', expand=True)
            bar.configure(command=text.yview)
            self.texts.append(text)
        self.show(None)

    def show(self, key, context='選択中'):
        self.key = key
        title, identity, body, augments = property_content(self.data, key)
        self.context.configure(text=context + 'のプロパティ' if key is not None else 'プロパティ')
        self.title.configure(text=title)
        self.identity.configure(text=identity)
        for widget, value in zip(self.texts, (body, augments)):
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
            widget.configure(state='disabled')
            widget.yview_moveto(0)

    def contents(self):
        return tuple(widget.get('1.0', 'end-1c') for widget in self.texts)
