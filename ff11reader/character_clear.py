"""Pure proposals for clearing a character's loaded macro and equipment data."""
from dataclasses import replace

from .domain import Text
from .edit_values import EDIT_KINDS, key, records, validate_structure, value
from .editing import Change, Edit
from .transfer_editing import cleared


def plan_character_clear(character):
    changes = []
    for kind in EDIT_KINDS:
        seen = set()
        for item in records(character, kind):
            validate_structure(item, kind)
            address = key(item)
            if address in seen:
                raise ValueError('全消去対象の位置が重複しています。再読み込みしてください。')
            seen.add(address)
            after = (replace(item, title=Text('', item.title.raw_hex, 'draft', ()))
                     if kind == 'books' else cleared(item))
            if kind == 'equipsets':
                after = replace(after, title=Text(f'Set{item.number:03}', item.title.raw_hex, 'draft', ()))
            if value(item) != value(after):
                changes.append(Change(character.folder_id, kind, address, item, after))
    return Edit('キャラのマクロ・装備セットを全消去', tuple(changes), atomic=True)
