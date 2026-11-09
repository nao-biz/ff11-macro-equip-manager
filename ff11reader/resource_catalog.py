"""Shared DAT identities and FTABLE layout; no file I/O or semantic decoding."""
from pathlib import Path
import struct

ITEM_RESOURCES = (4, 5, 8, 7, 6, 9, 0xD8FB, 0xD8FC, 0xD8FF, 0xD8FD)
AUTO_TRANSLATE_RESOURCE = 0xD8F9
PHRASE_LINKS = (('A', 0xD8EF), ('C', 0xD91E), ('J', 0xD8F0), ('Y', 0xD91D))
AUGMENT_NAME_RESOURCES = (0xD98C, 0xD914)
RANK_RESOURCES = (0x51, 0xD914)
SHARED_RESOURCES = tuple(dict.fromkeys((*ITEM_RESOURCES, AUTO_TRANSLATE_RESOURCE,
    *(logical for _, logical in PHRASE_LINKS), *AUGMENT_NAME_RESOURCES, *RANK_RESOURCES)))


def resource_path(root, table, logical):
    if not 0 <= logical * 2 <= len(table) - 2:
        raise ValueError('Truncated FTABLE')
    packed = struct.unpack_from('<H', table, logical * 2)[0]
    return Path(root)/'ROM'/str(packed >> 7)/f'{packed & 127}.DAT'


def resource_paths(root, table, logical_ids):
    return tuple(dict.fromkeys(resource_path(root, table, logical)
        for logical in logical_ids if 0 <= logical * 2 <= len(table) - 2))
