"""Bounded JSON input; no script execution or game writes."""
import json
import re
from datetime import datetime
from pathlib import Path
from .tracing import traced
from .augment_observation import AugmentItem, AugmentBag, AugmentExport, reconcile

MAX_BYTES = 4 * 1024 * 1024

def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('個体情報の数値が範囲外です。')
    return value

def string(value, limit=256):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError('個体情報の文字列が不正です。')
    return value

def object_keys(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('JSONのキーが重複しています。')
        result[k] = v
    return result

def parse(data):
    if len(data) > MAX_BYTES:
        raise ValueError('個体情報ファイルは4 MiBまでです。')
    try:
        value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=object_keys,
                           parse_constant=lambda s: (_ for _ in ()).throw(ValueError('JSON数値が不正です。')))
        if value['format'] != 'ff11-inventory-export' or type(value['version']) is not int or value['version'] != 1:
            raise ValueError('個体情報の形式または版が未対応です。')
        stamp = string(value['captured_at'])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', stamp):
            raise ValueError('取得日時はUTCで指定してください。')
        datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        char = value['character']
        cid = integer(char['id'], 1, 0xffffffff)
        name = string(char['name'], 64)
        if not name: raise ValueError('キャラ名が空です。')
        server = integer(char['server'], 0, 65535)
        if not isinstance(value['bags'], list) or len(value['bags']) != 17:
            raise ValueError('17収納の取得状態が必要です。')
        bags, seen = [], set()
        for b in value['bags']:
            bid = integer(b['id'], 0, 16)
            if bid in seen: raise ValueError('収納IDが重複しています。')
            seen.add(bid)
            state = b['state']
            if state not in ('ready', 'unavailable', 'incomplete'): raise ValueError('収納の取得状態が不正です。')
            if not isinstance(b['items'], list) or len(b['items']) > 80 or (state != 'ready' and b['items']):
                raise ValueError('収納内の個体一覧が不正です。')
            items, positions = [], set()
            for r in b['items']:
                index = integer(r['index'], 1, 80)
                if index in positions: raise ValueError('内部位置が重複しています。')
                positions.add(index)
                item_id = integer(r['item_id'], 1, 65534)
                count = integer(r['count'], 1, 0xffffffff)
                raw = string(r['extdata'], 48)
                if not re.fullmatch('[0-9a-f]{48}', raw): raise ValueError('追加情報は24バイトのhexで指定してください。')
                decoded = r['decode_state']
                if decoded not in ('decoded', 'unsupported', 'error'): raise ValueError('解析状態が不正です。')
                augments = r['augments']
                if not isinstance(augments, list) or len(augments) > 64: raise ValueError('能力一覧が不正です。')
                augments = tuple(string(a) for a in augments)
                path, rank = r['path'], r['rank']
                if path is not None and path not in ('A', 'B', 'C', 'D'): raise ValueError('Pathが不正です。')
                if rank is not None: integer(rank, 0, 127)
                if decoded != 'decoded' and (augments or path is not None or rank is not None):
                    raise ValueError('未解析の個体に解析結果が含まれています。')
                items.append(AugmentItem(index, item_id, count, raw, decoded, augments, path, rank))
            bags.append(AugmentBag(bid, state, tuple(items)))
        return AugmentExport(stamp, cid, name, server, tuple(bags))
    except (KeyError, TypeError, UnicodeError, RecursionError, OverflowError) as e:
        raise ValueError('個体情報ファイルの構造が不正です。') from e

@traced('augment.import')
def load_observation(path, character):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    return reconcile(parse(data), character)


def export_value(export):
    """Serialize validated immutable values in the original interchange format."""
    from dataclasses import asdict
    return dict(format='ff11-inventory-export', version=1,
                captured_at=export.captured_at,
                character=dict(id=export.character_id, name=export.character_name, server=export.server),
                bags=[asdict(bag) for bag in export.bags])
