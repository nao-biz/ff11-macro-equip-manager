"""Snapshot decoding and save-validation reads, without UI or save execution."""
from dataclasses import replace
import hashlib
from pathlib import Path
from .adapters import LocalReader
from .codecs import text, BAGS
from .dictionaries import resolve_token
from .domain import Snapshot
from .read_requests import CharacterReadRequest
from .resource_catalog import SHARED_RESOURCES
from .master_data import MasterData, FrozenMapping


MASTER_CHANGED = 'マスターデータが更新されています。アプリを再起動してください。'


def load_master_data(root, icon_ids):
    reader = LocalReader(root)
    items = reader.load_items(icon_ids)
    phrases = reader.load_phrases()
    augment_names = reader.load_augment_names()
    rank_augments = reader.load_rank_augments()
    reader.observe_resources(SHARED_RESOURCES)
    verify_sources(reader)
    return MasterData(str(reader.root), items, phrases, reader.phrase_readings,
                      augment_names, rank_augments, tuple(reader.sources),
                      tuple(reader.diagnostics), frozenset(icon_ids))


def verify_master_data(masters):
    """Hash startup evidence; never relabel cached values with current fingerprints."""
    if masters is None: return
    for path, expected in {s['path']:s['sha256'] for s in masters.sources}.items():
        source = Path(path)
        if source.resolve() != source or not source.is_relative_to(Path(masters.root)):
            raise ValueError(MASTER_CHANGED)
        try: actual = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as exc: raise ValueError(MASTER_CHANGED) from exc
        if actual != expected: raise ValueError(MASTER_CHANGED)


def master_sources(reader, masters):
    if str(reader.root) != masters.root:
        raise ValueError('マスターデータのインストール先が一致しません。')
    reader.sources.extend(dict(source) for source in masters.sources)
    reader.diagnostics.extend(dict(value) for value in masters.diagnostics)


def items_with_icons(masters, icon_ids):
    """Render newly needed icons only; dictionary values retain startup ownership."""
    from .codecs import ROTATE
    from .icons import item_icon
    wanted = set(icon_ids) - masters.icon_ids
    entries = [key for key in wanted if key in masters.items]
    if not entries: return masters.items
    reader = LocalReader(masters.root)
    fingerprints = {s['path']:s['sha256'] for s in masters.sources}
    paths = {masters.items[key]['source_path'] for key in entries}
    data = {path:reader.read(Path(path)) for path in paths}
    if any(hashlib.sha256(raw).hexdigest() != fingerprints[path] for path, raw in data.items()):
        raise ValueError(MASTER_CHANGED)
    items = dict(masters.items)
    for key in entries:
        item = items[key]; start = item['record_offset']
        png = item_icon(data[item['source_path']][start:start+0x1400].translate(ROTATE))
        items[key] = dict(item, icon_png=png)
    return FrozenMapping(items)


def resolve_macro_text(characters, phrases, items):
    resolver = lambda p: resolve_token(p, phrases, items)
    for character in characters:
        character.macros = [replace(m, lines=tuple(text(bytes.fromhex(line.raw_hex), resolver)
            if '{AT:' in line.display else line for line in m.lines)) for m in character.macros]


def verify_sources(reader):
    changed = reader.verify_unchanged()
    if changed:
        raise RuntimeError('Sources changed during snapshot; reload: ' + ', '.join(changed))


def load_macro_validation_snapshot(root, folder, pages, masters=None):
    """Fresh target pages and inventory; preserve the shared dictionary source set.

    File transactions still lock/hash dependencies before calling this reader.
    Sources read here are hash-verified again before returning. No cached UI values
    or icons are regenerated when an application master is supplied. Its startup
    fingerprints remain available for plan equality and dependency verification.
    """
    pages = frozenset(pages)
    if any(type(page) is not int or not 0 <= page < 400 for page in pages):
        raise ValueError('マクロ再検証のページが不正です。')
    filenames = frozenset(BAGS) | {('mcr' + (str(p) if p else '') + '.dat') for p in pages}
    request = CharacterReadRequest((folder,), filenames)
    reader = LocalReader(root)
    characters = reader.load_characters(request=request)
    if masters is None:
        items = reader.load_items()
        phrases = reader.load_phrases()
        reader.observe_resources(SHARED_RESOURCES)
    else:
        items, phrases = masters.items, masters.phrases
    resolve_macro_text(characters, phrases, items)
    verify_sources(reader)
    if masters is not None: master_sources(reader, masters)
    return Snapshot('macro-validation', '', characters, items, reader.sources, reader.diagnostics,
                    phrases=phrases, master_data=masters)
