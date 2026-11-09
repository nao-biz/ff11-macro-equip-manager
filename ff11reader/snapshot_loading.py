"""Snapshot decoding and save-validation reads, without UI or save execution."""
from dataclasses import replace
from .adapters import LocalReader
from .codecs import text, BAGS
from .dictionaries import resolve_token
from .domain import Snapshot
from .read_requests import CharacterReadRequest
from .resource_catalog import SHARED_RESOURCES


def resolve_macro_text(characters, phrases, items):
    resolver = lambda p: resolve_token(p, phrases, items)
    for character in characters:
        character.macros = [replace(m, lines=tuple(text(bytes.fromhex(line.raw_hex), resolver)
            if '{AT:' in line.display else line for line in m.lines)) for m in character.macros]


def verify_sources(reader):
    changed = reader.verify_unchanged()
    if changed:
        raise RuntimeError('Sources changed during snapshot; reload: ' + ', '.join(changed))


def load_macro_validation_snapshot(root, folder, pages):
    """Fresh target pages and inventory; preserve the shared dictionary source set.

    File transactions still lock/hash dependencies before calling this reader.
    Sources read here are hash-verified again before returning. No cached UI values
    or icons are used; shared dictionary sources remain available for plan equality.
    """
    pages = frozenset(pages)
    if any(type(page) is not int or not 0 <= page < 400 for page in pages):
        raise ValueError('マクロ再検証のページが不正です。')
    filenames = frozenset(BAGS) | {('mcr' + (str(p) if p else '') + '.dat') for p in pages}
    request = CharacterReadRequest((folder,), filenames)
    reader = LocalReader(root)
    characters = reader.load_characters(request=request)
    items = reader.load_items()
    phrases = reader.load_phrases()
    reader.observe_resources(SHARED_RESOURCES)
    resolve_macro_text(characters, phrases, items)
    verify_sources(reader)
    return Snapshot('macro-validation', '', characters, items, reader.sources, reader.diagnostics)
