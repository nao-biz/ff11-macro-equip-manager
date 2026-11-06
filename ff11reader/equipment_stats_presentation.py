"""Shared evaluation groups, stable ordering and value formatting (D-17)."""
from .equipment_stats import comparison_kind

GROUPS = (
    ('基本ステータス', 0, tuple((n, '', n) for n in
                              ('HP', 'MP', 'STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR'))),
    ('攻撃・命中', 0, (('攻', '', '攻'), ('命中', '', '命中'), ('飛攻', '', '飛攻'),
                       ('飛命', '', '飛命'), ('短剣スキル', '', '短剣スキル'))),
    ('TP・手数', 0, (('ヘイスト', '%', 'ヘイスト'), ('ストアTP', '', 'ストアTP'),
                    ('ダブルアタック', '%', 'ダブルアタック'),
                    ('トリプルアタック', '%', 'トリプルアタック'),
                    ('クリティカルヒット', '%', 'クリティカル率'),
                    ('モクシャ', '', 'モクシャ'), ('モクシャII', '', 'モクシャII'))),
    ('魔法', 1, (('魔命', '', '魔命'), ('魔攻', '', '魔攻'), ('魔法ダメージ', '', '魔法ダメージ'),
                 ('魔命スキル', '', '魔命スキル'), ('ファストキャスト', '%', 'ファストキャスト'),
                 ('マジックバーストダメージ', '%', 'MBダメージ'),
                 ('マジックバーストダメージII', '%', 'MBダメージII'))),
    ('防御・耐久', 1, (('防', '', '防'), ('回避', '', '回避'), ('魔回避', '', '魔回避'),
                       ('魔防', '', '魔防'), ('被ダメージ', '%', '被ダメージ'),
                       ('被物理ダメージ', '%', '被物理ダメージ'),
                       ('被物理ダメージII', '%', '被物理ダメージII'),
                       ('被魔法ダメージ', '%', '被魔法ダメージ'),
                       ('被魔法ダメージII', '%', '被魔法ダメージII'), ('詠唱中断率', '%', '詠唱中断率'))),
    ('WS・連携', 1, (('ウェポンスキルのダメージ', '%', 'WSダメージ'),
                     ('物理ダメージ上限', '%', '物理ダメージ上限'),
                     ('ウェポンスキルの命中', '', 'WS命中'), ('TPボーナス', '', 'TPボーナス'),
                     ('連携ボーナス', '%', '連携ボーナス'))),
)

ORDER = {name: index for index, (name, unit, label) in
         enumerate(metric for _, _, metrics in GROUPS for metric in metrics)}
LABELS = {name: label for _, _, metrics in GROUPS for name, unit, label in metrics}


def display_totals(totals):
    """Keep all properties, including additional units and unfamiliar names."""
    return sorted(totals, key=lambda row: (ORDER.get(row[0], len(ORDER)), row[0], row[1]))


def number(value, unit='', signed=False):
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return ('+' if signed and value > 0 else '') + text + unit


def comparison(current, trial=None):
    before = {(n, u): v for n, u, v in current.totals}
    after = {(n, u): v for n, u, v in trial.totals} if trial else {}
    rows = {}
    for _, _, metrics in GROUPS:
        for name, unit, label in metrics:
            key = name, unit
            kind = comparison_kind(current, trial, key)
            value = before.get(key, 0)
            candidate = after.get(key, 0)
            delta = candidate - value
            change = number(delta, unit, signed=True) if delta else '±0'
            if kind == 'partial':
                change += '*'
            elif kind == 'unavailable':
                change = '未確定'
            rows[key] = ((number(value, unit) + ('*' if key in current.uncertain else '')) if current.available else '未確定',
                         (number(candidate, unit) + ('*' if key in trial.uncertain else '') if trial.available else '未確定') if trial else '—',
                         change if trial else '—')
    return rows


def comparison_note(current, trial):
    return '* は既知分' if any(cell.endswith('*') for row in comparison(current, trial).values() for cell in row) else ''


def exclusion_groups(report):
    issues = set(report.unparsed) | set(report.missing)
    return (('集計対象外', tuple(line for line in report.excluded if line not in issues)),
            ('解析未対応', report.unparsed), ('取得不足', report.missing))
