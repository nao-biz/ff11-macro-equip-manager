"""Stat identities from the installed game's bilingual augment dictionary.

English-to-Japanese names come from paired DAT records, not a fallback glossary.
"""
import re
import unicodedata


def key(name):
    return re.sub(r'[\s.\"“”「」]', '', unicodedata.normalize('NFKC', name)).casefold()


# extdata.lua abbreviations -> English names in the game's dictionary.
ABBREVIATIONS = {
    key('Dbl.Atk.'): 'Double Attack', key('Triple Atk.'): 'Triple Attack',
    key('Crit.hit rate'): 'Critical hit rate', key('Crit. hit damage'): 'Critical hit damage',
    key('Mag. Dmg.'): 'Magic Damage', key('/Mag. Dmg.'): 'Magic Damage',
    key('Magic dmg.'): 'Magic Damage', key('/Mag. Eva.'): 'Mag. Evasion',
    key('Weapon skill accuracy'): 'Weapon Skill Acc.',
    key('Magic burst dmg. II'): 'Magic burst damage II',
}
BASE = ('HP', 'MP', 'STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR')
JAPANESE_ALIASES = {
    '攻撃': '攻', '攻撃力': '攻', '防御': '防', '防御力': '防',
    '魔法攻撃力': '魔攻', '魔法防御力': '魔防', 'クリティカルヒット率': 'クリティカルヒット',
    'ウェポンスキルダメージ': 'ウェポンスキルのダメージ', 'WSダメージ': 'ウェポンスキルのダメージ',
    'WS命中': 'ウェポンスキルの命中', 'MBダメージ': 'マジックバーストダメージ',
    'MBダメージII': 'マジックバーストダメージII', '物理ダメージ上限アップ': '物理ダメージ上限',
    '連携ダメージ': '連携ボーナス',
}
# Aggregation units, including game strings which omit their percentage sign.
PERCENT = frozenset((
    'ヘイスト', 'ファストキャスト', 'ダブルアタック', 'トリプルアタック', 'クワッドアタック',
    'クリティカルヒット', 'クリティカルヒットダメージ', '被ダメージ', '被物理ダメージ',
    '被物理ダメージII', '被魔法ダメージ', '被魔法ダメージII', '被ブレスダメージ',
    '物理ダメージ上限', 'ウェポンスキルのダメージ', 'マジックバーストダメージ',
    'マジックバーストダメージII', '連携ボーナス', '詠唱中断率', 'ケアル回復量',
    'ケアル回復量II', 'ケアル詠唱時間', '被ケアル回復量', '移動速度',
))
FIELD = re.compile(r'([^%\n:：{}]+?)([+-]?)%\+?d(%%)?(ダウン)?\s*$')


def template(value):
    if '\\x' in value or any(ord(c) < 32 for c in value.strip()):
        return None
    match = FIELD.fullmatch(unicodedata.normalize('NFKC', value).strip())
    if match is None:
        return None
    name = match[1].strip()
    if any(s in name for s in ('ペット', '潜在', 'コンビネーション', 'セット効果', '日中', '夜間', '発動', '時TP', '使用時', '装備時')):
        return None
    return name, '%' if match[3] else '', bool(match[4])


def from_dictionary(english, japanese):
    """Join matching resource IDs; conflicting translations stay unavailable."""
    choices = {}
    for ident in english.keys() & japanese.keys():
        en, ja = template(english[ident]), template(japanese[ident])
        if not en or not ja:
            continue
        name = JAPANESE_ALIASES.get(ja[0], ja[0])
        unit = '%' if name in PERCENT else ja[1] or en[1]
        choices.setdefault(key(en[0]), set()).add((name, unit, ja[2]))
    result = {}
    for name, entries in choices.items():
        identities = {(n, down) for n, unit, down in entries}
        if len(identities) != 1:
            result[name] = None
        elif len(entries) == 1:
            result[name] = next(iter(entries))
        else:
            # Multiple units require an explicit input unit; do not choose one.
            canonical, down = next(iter(identities))
            result[name] = (canonical, None, down)
    return result


def normalize(name, unit, value, names=None):
    name = unicodedata.normalize('NFKC', name)
    k = key(name)
    canonical = next((n for n in BASE if key(n) == k), None)
    if canonical:
        return canonical, unit, value
    if re.search(r'[ぁ-んァ-ヶ一-龯]', name):
        canonical = JAPANESE_ALIASES.get(name, name)
        return canonical, unit or ('%' if canonical in PERCENT else ''), value
    identity = (names or {}).get(k)
    if k not in (names or {}) and k in ABBREVIATIONS:
        identity = (names or {}).get(key(ABBREVIATIONS[k]))
    if identity is None:
        return None
    canonical, implied, down = identity
    if implied is None and not unit:
        return None
    return canonical, unit or implied, -abs(value) if down else value
