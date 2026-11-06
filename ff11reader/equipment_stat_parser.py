"""Separate additive effects, conditional/weapon text and unresolved effects."""
from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

from .equipment_stat_names import ABBREVIATIONS, BASE, JAPANESE_ALIASES, PERCENT, key, normalize

TOKEN = re.compile(r'([^+\d%:;、,\n]+?)\s*([+-]\s*\d+(?:\.\d+)?)[ \t]*(%?)')
WEAPON = re.compile(r'^(?:D|隔)\s*[+-]?\d+(?:\.\d+)?')
CONDITION = re.compile(r'潜在|コンビネーション|セット効果|ユニティ|エンチャント|日中|夜間|天候|曜日|'
                       r'のとき|の時|時々|発動|装備時|使用時|(?:\bwhen\b|\bwhile\b|\bduring\b)', re.I)


@dataclass(frozen=True)
class ParsedLine:
    values: tuple = ()
    outside: bool = False
    unparsed: bool = False
    uncertain: frozenset = frozenset()
    conditional: bool = False
    # Explicit headers may scope following lines; a standalone condition does not.
    continuation: bool = False


def path_metadata(line):
    return re.fullmatch(r'(?:Path\s*:\s*[A-Z]|Rank\s*:\s*\d+)',
                        unicodedata.normalize('NFKC', line).strip(), re.I) is not None


def _identity(name, unit, value, names):
    # Japanese stat names have no inter-word spaces; English dictionary names do.
    if re.search(r'[ぁ-んァ-ヶ一-龯]', name) and re.search(r'\s', name):
        return None
    return normalize(name, unit, value, names)


def _hint(text, names):
    """Identify only the named effect; unrelated summary rows remain usable."""
    aliases = (*BASE, *JAPANESE_ALIASES, *JAPANESE_ALIASES.values(), *PERCENT,
               *(names or {}), *ABBREVIATIONS)
    cleaned = key(text.strip())
    candidates = [alias for alias in aliases if cleaned.startswith(key(alias))]
    for alias in sorted(candidates, key=lambda n: len(key(n)), reverse=True):
        result = normalize(alias, '', Decimal(0), names)
        if result:
            return frozenset({result[:2]})
    return frozenset()


def analyze_line(line, names=None):
    text = unicodedata.normalize('NFKC', line).strip().replace('−', '-')
    colon = text.find(':')
    condition = CONDITION.search(text)
    if colon >= 0:
        # A preceding, complete effect is outside the following condition scope.
        preceding = list(TOKEN.finditer(text[:colon]))
        cut = 0
        if condition and condition.start() < colon:
            cut = condition.start()
        elif preceding:
            end = preceding[-1].end()
            if text[end - 1].isspace() or text[end:colon].startswith(' '):
                cut = end
        prefix = _unconditional(text[:cut], names)
        return ParsedLine(prefix.values, True, prefix.unparsed, prefix.uncertain, True, True)
    if condition:
        # Postfix conditions qualify the preceding values as well.
        return ParsedLine(outside=True, conditional=True)
    return _unconditional(text, names)


def _unconditional(text, names):
    outside = False
    while match := WEAPON.match(text):
        outside = True
        text = text[match.end():].lstrip()
    if not text or text == '.':
        return ParsedLine(outside=outside or bool(text))
    text = re.sub(r'詠唱中断率\s*(\d+(?:\.\d+)?)%ダウン', r'詠唱中断率-\1%', text)
    text = re.sub(r'防(\d+)', r'防+\1', text)
    matches = list(TOKEN.finditer(text))
    if not matches:
        return ParsedLine(outside=outside, unparsed=True, uncertain=_hint(text, names))
    values, uncertain = [], set()
    unparsed = bool(text[:matches[0].start()].strip(' ,、;'))
    for index, match in enumerate(matches):
        raw_name = match[1].strip()
        value = Decimal(re.sub(r'\s+', '', match[2]))
        identity = _identity(raw_name, match[3], value, names)
        if identity is None:
            # Recover a separately named effect after another unresolved phrase.
            for boundary in re.finditer(r'\s+', raw_name):
                identity = _identity(raw_name[boundary.end():], match[3], value, names)
                if identity:
                    unparsed = True
                    uncertain.update(_hint(raw_name[:boundary.start()], names))
                    break
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        suffix = text[match.end():end].strip(' ,、;')
        if identity is None or suffix:
            unparsed = True
            uncertain.update({identity[:2]} if identity else _hint(raw_name, names))
        else:
            values.append(identity)
    return ParsedLine(tuple(values), outside, unparsed, frozenset(uncertain))


def parse_line(line, names=None):
    """Compatibility interface for a fully interpreted additive expression."""
    result = analyze_line(line, names)
    if result.unparsed or (result.conditional and not result.values):
        return None
    return list(result.values)
