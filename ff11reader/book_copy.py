"""Pure cross-character book and referenced equipment-set copy proposals."""
from copy import deepcopy
from dataclasses import dataclass, replace
import re

from .domain import BookName, Character
from .edit_values import integer, key, value, validate_structure
from .editing import Change, Edit
from .macro_links import analyze_macro_sets, parse_reference
from .references import assess_equipment, STATUS_LABELS
from .text_editing import remap_text


@dataclass(frozen=True)
class BookCopy:
    source: str
    destination: str
    source_book: int
    destination_book: int
    equipment_numbers: tuple
    overwritten_macros: int
    affected_references: tuple
    warnings: tuple
    edit: Edit


def _book(character, number):
    if not integer(number, 1, 40):
        raise ValueError('ブック番号は1〜40で指定してください。')
    macros = [m for m in character.macros if m.book == number]
    expected = {(number, p, bank, n) for p in range(1, 11)
                for bank in ('ctrl', 'alt') for n in range(1, 11)}
    if len(macros) != 200 or {key(m) for m in macros} != expected:
        raise ValueError(f'{character.folder_id} のブック {number} は全200マクロを読み取れていません。')
    for macro in macros:
        validate_structure(macro, 'macros')
    return sorted(macros, key=key)


def _line(line, source_book, destination_book, warnings):
    if re.match(r'^\s*(?:/(?:equipset|lockstyleset)|【/(?:equipset|lockstyleset)】)(?:\s|$)', line.display, re.I):
        if parse_reference(line.display) is None:
            raise ValueError(f'参照セット番号を判定できません: {line.display}')
    match = re.match(r'^\s*(?:/macro|【/macro】)\s+(?:book|【book】)\s+([0-9]{1,2})(?=\s|<|$)', line.display, re.I)
    if match:
        number = int(match[1])
        if number == source_book:
            start, end = match.span(1)
            return remap_text(line, line.display[:start] + str(destination_book).zfill(end-start) + line.display[end:])
        warnings.add(f'別ブックへの切替を維持: {line.display}')
    return line


def _equipment_changes(source, destination, numbers, warnings):
    source_sets = {e.number: e for e in source.equipsets}
    target_sets = {e.number: e for e in destination.equipsets}
    if any(n not in source_sets or n not in target_sets for n in numbers):
        raise ValueError('参照する装備セットのコピー元またはコピー先を読み取れていません。')
    sets = [source_sets[n] for n in numbers]
    for equipment in sets:
        validate_structure(equipment, 'equipsets')
    assessed = assess_equipment(replace(destination, equipsets=sets))
    for equipment in assessed:
        for slot in equipment.slots:
            if slot.action == 'equip' and slot.item_reference.observation != 'cache_match':
                warnings.add(f'装備セット {equipment.number:03} / {slot.name}: '
                             + STATUS_LABELS[slot.item_reference.observation])
    changed_sets = {n for n in numbers if value(target_sets[n]) != value(source_sets[n])}
    return [Change(destination.folder_id, 'equipsets', (e.number,), target_sets[e.number], e)
            for e in assessed if e.number in changed_sets]


def plan_book_copy(source, destination, source_book, destination_book):
    if source.folder_id == destination.folder_id:
        raise ValueError('コピー先には別のキャラクターを選択してください。')
    originals = _book(source, source_book)
    if source_book not in source.books or destination_book not in destination.books:
        raise ValueError('コピー元またはコピー先のブック名を読み取れていません。')
    targets = {key(m): m for m in _book(destination, destination_book)}
    warnings = set()
    copied = [replace(m, book=destination_book,
                      lines=tuple(_line(t, source_book, destination_book, warnings) for t in m.lines))
              for m in originals]
    numbers = tuple(sorted({r.number for r in analyze_macro_sets(
        Character(source.folder_id, macros=originals)).references}))
    changes = [Change(destination.folder_id, 'macros', key(m), targets[key(m)], m)
               for m in copied if value(targets[key(m)]) != value(m)]
    equipment_changes = _equipment_changes(source, destination, numbers, warnings)
    changes.extend(equipment_changes)
    before_name = BookName(destination_book, destination.books[destination_book])
    after_name = BookName(destination_book, source.books[source_book])
    if value(before_name) != value(after_name):
        changes.append(Change(destination.folder_id, 'books', (destination_book,), before_name, after_name))
    changed_sets = {c.key[0] for c in equipment_changes}
    affected = tuple(r for r in analyze_macro_sets(destination).references
                     if r.book != destination_book and r.number in changed_sets)
    occupied = sum(bool(c.before.title.display or any(t.display for t in c.before.lines))
                   for c in changes if c.kind == 'macros')
    label = f'キャラ間ブックコピー {source.folder_id}:{source_book:02} → {destination.folder_id}:{destination_book:02}'
    return deepcopy(BookCopy(source.folder_id, destination.folder_id, source_book, destination_book,
                             numbers, occupied, affected, tuple(sorted(warnings)),
                             Edit(label, tuple(changes), atomic=True)))
