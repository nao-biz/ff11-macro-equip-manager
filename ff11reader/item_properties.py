"""Selected-item properties from loaded game descriptions and reconciled observations."""
from dataclasses import dataclass
import re
import unicodedata

from .domain import Equipset, Slot, Text
from .equipment_stat_parser import WEAPON, analyze_line, path_metadata
from .equipment_stats import summarize
from .equipment_stats_presentation import GROUPS, number

BASE_STATS = ('STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR')


def format_properties(text, names=None):
    """Keep condition text; group basic stats and put other properties on separate lines."""
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


@dataclass(frozen=True)
class ItemProperties:
    title: str = 'アイテムを選択'
    identity: str = ''
    body: str = ''
    augments: str = ''
    metadata: str = ''


def describe_item(row, items, observation=None, names=None, bags=None):
    if row is None:
        return ItemProperties()
    action = getattr(row, 'action', 'equip')
    if action != 'equip':
        title, body = {'keep': ('変更しない', '実行前の装備は未確定です。'),
                       'remove': ('装備を外す', 'この枠は装備なしになります。')}.get(
                           action, ('装備指定を確認', '装備指定を解釈できません。'))
        return ItemProperties(title=title, body=body)
    master = items.get(row.item_id, {})
    observed = observation.item(row) if observation is not None else None
    decoded = observed is not None and observed.decode_state == 'decoded'
    identity = f'{(bags or {}).get(row.container, "収納 " + str(row.container))} / 位置 {row.index}'
    if decoded and observed.path:
        identity += ' / Path ' + observed.path
    if decoded and observed.rank is not None:
        identity += ' / Rank ' + str(observed.rank)
    augments, metadata = [], []
    if decoded:
        resolved = observation.abilities(observed)
        augments.extend(format_properties(raw, names) for raw in resolved.lines if not path_metadata(raw))
        if not resolved.complete:
            augments.append(resolved.reason)
        if not augments:
            augments.append('付加能力なし')
        if resolved.source:
            metadata.append('能力の参照元: ゲームデータ')
    elif observed is not None:
        augments.append('オーグメントを解析できません（生データを保持）')
    else:
        augments.append('オーグメント未取得' if observation is None else '個体情報の再取得が必要')
    if observation is not None:
        metadata.append('取得日時: ' + observation.export.captured_at)
    return ItemProperties(master.get('name') or f'ID {row.item_id}', identity,
                          format_properties(master.get('description') or '本体の説明が未取得', names),
                          '\n'.join(augments), '\n'.join(metadata))


def summarize_item(row, items, observation=None, names=None):
    slot = row if isinstance(row, Slot) else Slot('main', 'equip', row.item_id, row.container, row.index, '')
    return summarize(Equipset(0, Text('', '', 'cp932'), (slot,)), items, observation, names)


def other_properties(report):
    visible = {(name, unit) for _, _, metrics in GROUPS for name, unit, _ in metrics}
    lines = [name + number(value, unit, signed=True) for name, unit, value in report.totals
             if (name, unit) not in visible]
    lines.extend(('オグメ: ' if ' / オグメ' in source else '') + raw for source, raw in report.excluded)
    return '\n'.join(lines) or '主要項目以外の性能・効果はありません。'
