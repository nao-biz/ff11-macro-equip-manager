"""Detached inputs for replaying a macro proposal against freshly loaded values."""
from copy import deepcopy
from dataclasses import replace
from .domain import Snapshot, Text
from .editing import macro_key


def replay_macro_proposal(snapshot, folder, changes, record_bases):
    """Return independent before/after inputs; keep fresh snapshot ownership intact.

    Changes use (macro address, field number) keys and record_bases use macro
    addresses. The caller regenerates the plan and compares its bytes and evidence.
    """
    character = next(c for c in snapshot.characters if c.folder_id == folder)
    addresses = {address for address, _ in changes} | set(record_bases)
    selected = [m for m in character.macros if macro_key(m) in addresses]
    if {macro_key(m) for m in selected} != addresses:
        raise ValueError('保存計画のマクロが再読込結果にありません。')
    before = deepcopy(Snapshot(snapshot.id, snapshot.captured_at,
        [replace(character, macros=selected, equipsets=[])], snapshot.items,
        snapshot.sources, [], snapshot.installation_key))
    after = deepcopy(before)

    def changed(macro, number, old):
        change = changes.get((macro_key(macro), number))
        return Text(change.after, change.provenance.hex(), 'draft', change.tokens) if change else old

    after.characters[0].macros = [replace(m,
        title=changed(m, 0, m.title),
        lines=tuple(changed(m, n, line) for n, line in enumerate(m.lines, 1)),
        raw_hex=record_bases.get(macro_key(m), m.raw_hex)) for m in after.characters[0].macros]
    return before, after
