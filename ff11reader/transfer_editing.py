"""Selection-based transfer and deletion proposals. No UI or file access."""
from copy import deepcopy
from dataclasses import dataclass, replace
import re
from .domain import Character, Text
from .edit_values import key, value
from .editing import Change, Edit
from .paste_placement import assess_placement, calculate_placement
from .text_editing import remap_text


@dataclass(frozen=True)
class Transfer:
    character: str
    kind: str
    selection: tuple
    items: tuple
    cut: bool


def members(kind, selection):
    if kind == 'palette':
        return tuple((*a, bank, n) for a in selection for bank in ('ctrl', 'alt') for n in range(1, 11))
    return tuple(selection)


def capture(character, kind, selection, cut=False):
    selection = tuple(selection)
    calculate_placement(kind, selection, selection[0] if selection else ())
    source = character.equipsets if kind == 'equipment' else character.macros
    result = []
    for address in members(kind, selection):
        matches = [x for x in source if key(x) == address]
        if len(matches) != 1:raise ValueError(f'読み取れていない位置です: {address}')
        result.append(deepcopy(matches[0]))
    return Transfer(character.folder_id, kind, selection, tuple(result), cut)


def cleared(item):
    title = Text('', item.title.raw_hex, 'draft', ())
    if hasattr(item, 'lines'):
        return replace(item, title=title, lines=tuple(Text('', t.raw_hex, 'draft', ()) for t in item.lines))
    return replace(item, title=title, slots=tuple(replace(s, action='keep', item_id=None, container=None, index=None) for s in item.slots))


def located(item, address):
    if hasattr(item, 'lines'):
        return replace(item, book=address[0], palette=address[1], bank=address[2], key=address[3])
    return replace(item, number=address[0])


def _navigation(macro, old_book, destinations):
    old, new = old_book, macro.book
    lines = []
    command = re.compile(r'^\s*(?:/macro|【/macro】)\s+(?:(book|set)|【(book|set)】)\s+([0-9]{1,2})(?=\s|<|$)', re.I)
    for line in macro.lines:
        match = command.match(line.display)
        if not match:
            if re.match(r'^\s*(?:/macro|【/macro】)(?:\s|$)', line.display, re.I):
                raise ValueError(f'{key(macro)}: 切替先を判定できません: {line.display}')
            lines.append(line);continue
        mode, number = (match[1] or match[2]).lower(), int(match[3])
        if not 1 <= number <= (40 if mode == 'book' else 10):raise ValueError(f'{key(macro)}: 切替番号が範囲外です。')
        if mode == 'book':
            old = new = number;lines.append(line);continue
        book, palette = destinations.get((old, number), (old, number))
        if new != book:
            lines.append(Text(f'/macro book {book}', '', 'draft', ()));new = book
        start, end = match.span(3)
        lines.append(remap_text(line, line.display[:start] + str(palette).zfill(end-start) + line.display[end:]))
    while len(lines) > 6 and not lines[-1].display:lines.pop()
    if len(lines) > 6:raise ValueError(f'{key(macro)}: ブック切替の追加で{len(lines)}行になります。6行以内に整理してください。')
    return replace(macro, lines=tuple(lines))


def plan_paste(character, transfer, anchor):
    if character.folder_id != transfer.character:raise ValueError('コピー元と同じキャラクターを選択してください。')
    kind = transfer.kind
    field = 'equipsets' if kind == 'equipment' else 'macros'
    captured = Character(character.folder_id, **{field: list(transfer.items)})
    result = assess_placement(character, kind, transfer.selection, anchor, source_character=captured)
    if not result.allowed:
        labels = {'occupied':'内容があります', 'unavailable':'読込不足', 'out_of_range':'範囲外'}
        raise ValueError('\n'.join(f'{i.member or i.target or i.source}: {labels[i.reason]}' for i in result.issues))
    original = {key(x):x for x in getattr(character, field)}
    captured_items = {key(x):x for x in transfer.items}
    if transfer.cut and any(a not in original or value(original[a]) != value(x) for a,x in captured_items.items()):
        raise ValueError('切り取り元が変更されました。切り取り直してください。')
    pairs = []
    for p in result.placements:
        pairs.extend(zip(members(kind, (p.source,)), members(kind, (p.target,))))
    updated = dict(original)
    if transfer.cut:
        for source in captured_items:updated[source] = cleared(original[source])
    for source, target in pairs:updated[target] = located(captured_items[source], target)
    moves = ()
    if kind == 'equipment' and transfer.cut:
        # Reuse proven raw-record relocation and equipset reference cascading.
        from .equipment_moves import plan_move
        from .editing import EditSession
        from .domain import Snapshot
        session = EditSession(Snapshot('transfer','', [deepcopy(character)], {}, [], []))
        from .equipment_moves import vacant
        pairs = [(a,b) for a,b in pairs if not vacant(captured_items[a])]
        for source, target in pairs:
            session.apply(plan_move(session.character(character.folder_id), source[0], target[0]))
        changed = session.character(character.folder_id)
        changes = tuple(Change(character.folder_id, f, key(a), a, b)
                        for f in ('equipsets','macros') for a,b in zip(getattr(character,f),getattr(changed,f)) if value(a)!=value(b))
        moves = tuple((character.folder_id, a[0], b[0]) for a,b in pairs)
    else:
        if kind != 'equipment':
            destinations = {p.source:p.target for p in result.placements} if kind == 'palette' and transfer.cut else {}
            old_books = {target:source[0] for source,target in pairs}
            for address, item in list(updated.items()):
                if address in old_books or destinations:
                    updated[address] = _navigation(item, old_books.get(address,item.book), destinations)
        changes = tuple(Change(character.folder_id, field, a, item, updated[a]) for a,item in original.items() if value(item)!=value(updated[a]))
    return Edit('選択範囲を移動' if transfer.cut else '選択範囲をコピー', changes, moves, atomic=True)


def plan_delete(character, kind, selection):
    transfer = capture(character, kind, selection)
    field = 'equipsets' if kind == 'equipment' else 'macros'
    return Edit('選択範囲を削除', tuple(Change(character.folder_id, field, key(x), x, cleared(x)) for x in transfer.items), atomic=True)
