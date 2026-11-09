"""Snapshot decoding and save-validation reads, without UI or save execution."""
from dataclasses import replace
from .adapters import LocalReader
from .codecs import text
from .dictionaries import resolve_token
from .domain import Snapshot


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
    reader = LocalReader(root)
    characters = reader.load_characters(macro_scope=(folder, frozenset(pages)))
    items = reader.load_items()
    phrases = reader.load_phrases()
    # Keep the same shared source closure as full loading for dependency comparison.
    reader.load_augment_names()
    reader.load_rank_augments()
    resolve_macro_text(characters, phrases, items)
    verify_sources(reader)
    return Snapshot('macro-validation', '', characters, items, reader.sources, reader.diagnostics)
