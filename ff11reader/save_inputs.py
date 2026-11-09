"""Detached persistence inputs and their conservative item-dictionary dependencies."""
from copy import deepcopy
import re
from .domain import Snapshot
from .item_tokens import item_id_from_token

# Scan every candidate, including overlapping markers and bytes beyond NUL.
# Extra IDs are harmless; validation/encoding still decides which bytes are valid.
_RAW_TOKENS = re.compile(r'(?=fd([0-9a-f]{8})fd)', re.IGNORECASE)


def required_item_ids(character):
    result = {slot.item_id for equipment in character.equipsets for slot in equipment.slots if slot.item_id}
    if character.macros:
        result.update(row.item_id for row in character.inventory)
    for macro in character.macros:
        fields = (macro.title, *macro.lines)
        identities = [t.identity for field in fields for t in field.tokens or ()]
        for raw_hex in (macro.raw_hex, *(field.raw_hex for field in fields)):
            identities.extend(_RAW_TOKENS.findall(raw_hex))
        for identity in identities:
            try: item_id = item_id_from_token(bytes.fromhex(identity))
            except ValueError: continue  # The existing text validator owns malformed-token errors.
            if item_id is not None: result.add(item_id)
    return result


def copy_save_input(snapshot, character, item_ids=None):
    """Copy complete item records only for IDs used by the validation context."""
    if item_ids is None: item_ids = required_item_ids(character)
    items = {key:snapshot.items[key] for key in item_ids if key in snapshot.items}
    return deepcopy(Snapshot(snapshot.id, snapshot.captured_at, [character], items,
                             snapshot.sources, [], snapshot.installation_key))
