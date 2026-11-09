"""Immutable supplemental observations and pure location reconciliation."""
from dataclasses import dataclass

@dataclass(frozen=True)
class AugmentItem:
    index: int
    item_id: int
    count: int
    extdata: str
    decode_state: str
    augments: tuple[str, ...]
    path: str | None
    rank: int | None

@dataclass(frozen=True)
class AugmentBag:
    id: int
    state: str
    items: tuple[AugmentItem, ...]

@dataclass(frozen=True)
class AugmentExport:
    captured_at: str
    character_id: int
    character_name: str
    server: int
    bags: tuple[AugmentBag, ...]

@dataclass(frozen=True)
class AugmentObservation:
    export: AugmentExport
    accepted_bags: frozenset[int]
    issues: tuple[tuple[int, str], ...]
    rank_catalog: object = None

    def abilities(self, item):
        from .rank_augments import abilities
        return abilities(item, self.rank_catalog)

    def item(self, row):
        if row.container not in self.accepted_bags:
            return None
        return next((item for bag in self.export.bags if bag.id == row.container
                     for item in bag.items if (item.index, item.item_id) == (row.index, row.item_id)), None)


def reconcile(export, character, rank_catalog=None):
    accepted, issues = set(), []
    for bag in export.bags:
        rows = [r for r in character.inventory if r.container == bag.id]
        local = {(r.index, r.item_id) for r in rows}
        expected = {(r.index, r.item_id) for r in bag.items}
        if bag.state != 'ready':
            issues.append((bag.id, bag.state))
        elif character.inventory_coverage.get(bag.id) != 'loaded':
            issues.append((bag.id, 'local_unavailable'))
        elif len({r.index for r in rows}) != len(rows) or local != expected:
            issues.append((bag.id, 'locations_changed'))
        else:
            accepted.add(bag.id)
    return AugmentObservation(export, frozenset(accepted), tuple(issues), rank_catalog)
