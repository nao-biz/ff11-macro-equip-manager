"""Resolve bundle augments from installed MNC2 tables, without game mutations."""
from dataclasses import dataclass
import re
import struct


# Format IDs and bit order, not item-specific stats or rank curves.
MASKS = {
    2049: tuple(range(9, 18)), 2050: tuple(range(11, 18)),
    2051: tuple(range(1, 9)), 2052: (18, 20, 24),
    2053: (19, 21, 133, 362), 2054: (23, 134, 22, 25),
    2055: (18, 20, 19, 133, 23), 2056: (24, 133, 362, 134, 25),
}
PREFIXES = {2064: 128, 2065: 2044, 2066: 135, 2067: 2045, 2068: 2043, 2069: 2042}


@dataclass(frozen=True)
class Abilities:
    lines: tuple[str, ...]
    complete: bool
    reason: str = ''
    source: str = ''


def decode_bundles(data):
    """MNC2: 1024 six-index bundles, followed by 76-byte effect records."""
    if len(data) < 48 or data[:4] != b'menu' or data[32:36] != b'mnc2':
        raise ValueError('Unsupported rank augment DAT header')
    size = ((struct.unpack_from('<I', data, 36)[0] >> 7) & 0x7ffff) * 16
    end = 32 + size
    if size < 12432 or end > len(data):
        raise ValueError('Truncated rank augment DAT')
    bundles = {}
    for bundle in range(1, 1024):
        indexes = struct.unpack_from('<6H', data, 176 + bundle * 12)
        effects = []
        for index in indexes:
            if not index:
                continue
            offset = 12464 + index * 76
            if offset + 76 > end:
                raise ValueError('Rank augment record outside MNC2')
            effect, parameter = struct.unpack_from('<HH', data, offset + 8)
            values = struct.unpack_from('<31h', data, offset + 12)
            effects.append((effect, parameter, values))
        if effects:
            bundles[bundle] = tuple(effects)
    return bundles


def format_effect(effect, parameter, value, formats):
    if effect == 2076:
        prefix = formats.get(parameter)
        if not prefix or not prefix.endswith(':'):
            raise ValueError('Weapon skill format unavailable')
        return tuple(prefix + line for line in format_effect(47, 0, value, formats))
    if effect in PREFIXES:
        prefix = formats.get(PREFIXES[effect])
        if not prefix:
            raise ValueError('Rank effect prefix unavailable')
        return tuple(prefix + line for line in format_effect(parameter, 0, value, formats))
    if effect == 4096:
        return tuple(line for ident in range(11, 18) for line in format_effect(ident, 0, value, formats))
    if effect in MASKS:
        ids = MASKS[effect]
        if not parameter or parameter >= 1 << len(ids):
            raise ValueError('Unsupported rank stat mask')
        return tuple(line for bit, ident in enumerate(ids) if parameter & (1 << bit)
                     for line in format_effect(ident, 0, value, formats))
    pattern = formats.get(effect)
    if not pattern or '%' in re.sub(r'%%|%[+]?d', '', pattern):
        raise ValueError('Rank effect format unavailable')
    count = sum(token != '%%' for token in re.findall(r'%%|%[+]?d', pattern))
    if not count:
        raise ValueError('Rank effect has no numeric format')
    return ((pattern % ((value,) * count)).strip(),)


@dataclass(frozen=True)
class RankCatalog:
    bundles: dict
    formats: dict

    def resolve(self, item):
        raw = bytes.fromhex(item.extdata)
        block, bundle = struct.unpack_from('<II', raw, 4)
        rank, path = (block >> 18) & 31, 'ABCD'[block & 3]
        max_rank = (3 + ((block >> 23) & 3)) * 5
        if item.rank != rank or item.path != path or rank > max_rank:
            return Abilities((), False, 'Rank・Pathと生データが一致しません')
        effects = self.bundles.get(bundle)
        if effects is None:
            return Abilities((), False, 'Rankの能力表が未取得')
        lines, missing = [], []
        for effect, parameter, values in effects:
            value = values[rank]
            if not value:
                continue
            try:
                lines.extend(format_effect(effect, parameter, value, self.formats))
            except (ValueError, TypeError):
                missing.append(f'能力ID {effect} / パラメータ {parameter} / 値 {value}')
        return Abilities(tuple(lines), not missing,
                         'Rank能力の解析未対応: ' + '、'.join(missing) if missing else '',
                         f'ゲームDAT / Rank {rank}')


def abilities(item, catalog=None):
    if item.decode_state != 'decoded':
        return Abilities((), False, 'オーグメントを解析できません（生データを保持）')
    if item.extdata.startswith('0383'):
        if catalog is None:
            return Abilities((), False, 'Rankの能力表が未取得')
        return catalog.resolve(item)
    from .equipment_stat_parser import path_metadata
    complete = not item.path or any(line.strip() and not path_metadata(line) for line in item.augments)
    return Abilities(item.augments, complete,
                     '' if complete else 'Path ' + item.path + ' の能力が未取得')
