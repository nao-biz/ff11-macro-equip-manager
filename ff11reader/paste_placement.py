"""Pure placement and availability checks; does not apply edits or follow references."""
from dataclasses import dataclass
from enum import StrEnum

from .edit_values import integer, key, validate_structure
from .equipment_moves import vacant


class SelectionKind(StrEnum):
    MACRO = 'macro'
    PALETTE = 'palette'
    EQUIPMENT = 'equipment'


@dataclass(frozen=True)
class Placement:
    source: tuple
    target: tuple


@dataclass(frozen=True)
class PlacementIssue:
    reason: str  # out_of_range, unavailable, occupied
    side: str  # source or target
    source: tuple
    target: tuple | None
    member: tuple | None = None  # macro within an unavailable/occupied palette


@dataclass(frozen=True)
class PlacementResult:
    kind: SelectionKind
    anchor: tuple
    placements: tuple[Placement, ...]
    issues: tuple[PlacementIssue, ...] = ()

    @property
    def allowed(self):
        return not self.issues


def _valid(kind, address):
    if not isinstance(address, tuple):
        return False
    if kind == SelectionKind.EQUIPMENT:
        return len(address) == 1 and integer(address[0], 1, 200)
    if len(address) != (4 if kind == SelectionKind.MACRO else 2):
        return False
    if not integer(address[0], 1, 40) or not integer(address[1], 1, 10):
        return False
    return kind == SelectionKind.PALETTE or (address[2] in ('ctrl', 'alt') and integer(address[3], 1, 10))


def _coordinates(kind, address):
    if kind == SelectionKind.MACRO:
        return (0 if address[2] == 'ctrl' else 1, address[3] - 1)
    return (address[-1] - 1,)


def calculate_placement(kind, selection, anchor):
    """Translate selected positions, retaining holes. Invalid requests raise ValueError.

    Addresses: macro=(book,palette,bank,key), palette=(book,palette), equipment=(number,).
    On overflow no partial placement is returned; issues identify the offending source.
    """
    kind = SelectionKind(kind)
    selection = tuple(selection)
    if not selection or not _valid(kind, anchor) or any(not _valid(kind, a) for a in selection):
        raise ValueError('選択位置と貼り付け基準を確認してください。')
    if len(set(selection)) != len(selection):
        raise ValueError('選択位置が重複しています。')
    parent_length = 2 if kind == SelectionKind.MACRO else 1 if kind == SelectionKind.PALETTE else 0
    if len({a[:parent_length] for a in selection}) != 1:
        raise ValueError('選択元の階層を揃えてください。')
    ordered = sorted(selection, key=lambda a: _coordinates(kind, a))
    coordinates = [_coordinates(kind, a) for a in ordered]
    origin = tuple(min(axis) for axis in zip(*coordinates))
    start = _coordinates(kind, anchor)
    limits = (2, 10) if kind == SelectionKind.MACRO else (10 if kind == SelectionKind.PALETTE else 200,)
    placements, issues = [], []
    for source, position in zip(ordered, coordinates):
        destination = tuple(a + p - o for a, p, o in zip(start, position, origin))
        if any(n >= limit for n, limit in zip(destination, limits)):
            issues.append(PlacementIssue('out_of_range', 'target', source, None))
            continue
        if kind == SelectionKind.MACRO:
            target = (*anchor[:2], ('ctrl', 'alt')[destination[0]], destination[1] + 1)
        elif kind == SelectionKind.PALETTE:
            target = (anchor[0], destination[0] + 1)
        else:
            target = (destination[0] + 1,)
        placements.append(Placement(source, target))
    return PlacementResult(kind, anchor, () if issues else tuple(placements), tuple(issues))


def _index(items):
    result = {}
    for item in items:
        address = key(item)
        result.setdefault(address, []).append(item)
    return result


def _available(rows, kind):
    if len(rows) != 1:
        return False
    try:
        validate_structure(rows[0], kind)
    except (TypeError, ValueError):
        return False
    return True


def assess_placement(character, kind, selection, anchor, *, source_character=None, overwrite=False):
    """Check current source/target availability and target emptiness for one character.

    This result concerns placement only. Cascade, byte limits, and cut-source freshness
    must still be checked when constructing/applying the complete editing proposal.
    """
    result = calculate_placement(kind, selection, anchor)
    if not result.allowed:
        return result
    kind = result.kind
    index = _index(character.equipsets if kind == SelectionKind.EQUIPMENT else character.macros)
    source_character = source_character or character
    source_index = _index(source_character.equipsets if kind == SelectionKind.EQUIPMENT else source_character.macros)
    issues = []
    for placement in result.placements:
        for side, address in (('source', placement.source), ('target', placement.target)):
            members = (tuple((*address, bank, n) for bank in ('ctrl', 'alt') for n in range(1, 11))
                       if kind == SelectionKind.PALETTE else (address,))
            for member in members:
                rows = (source_index if side == 'source' else index).get(member, [])
                item_kind = 'equipsets' if kind == SelectionKind.EQUIPMENT else 'macros'
                reason = None
                if not _available(rows, item_kind):
                    reason = 'unavailable'
                elif side == 'target':
                    item = rows[0]
                    empty = (vacant(item) if kind == SelectionKind.EQUIPMENT else
                             item.title.display == '' and all(t.display == '' for t in item.lines))
                    if not empty and not (overwrite and kind in (SelectionKind.MACRO, SelectionKind.PALETTE)):
                        reason = 'occupied'
                if reason:
                    issues.append(PlacementIssue(reason, side, placement.source, placement.target,
                                                 member if kind == SelectionKind.PALETTE else None))
    return PlacementResult(kind, anchor, () if issues else result.placements, tuple(issues))
