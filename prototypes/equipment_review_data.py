"""Synthetic, explicitly normalized inputs for a layout experiment, never game data.

Raw English augment examples have hand-authored expected values. This fixture is
not a normalization implementation. Calculation uses the production summarizer.
"""
from dataclasses import dataclass

from ff11reader.augment_observation import (
    AugmentBag, AugmentExport, AugmentItem, AugmentObservation,
)
from ff11reader.domain import Equipset, Slot, Text
from ff11reader.equipment_stats import summarize
from .equipment_workspace import SLOTS

SLOT_KEYS = ('main', 'sub', 'range', 'ammo', 'head', 'neck', 'ear1', 'ear2',
             'body', 'hands', 'ring1', 'ring2', 'back', 'waist', 'legs', 'feet')
PARTS = ('短剣', '片手剣', '銃', '矢弾', '兜', '首飾り', '耳飾り', '耳飾り',
         '鎧', '手袋', '指輪', '指輪', 'マント', '帯', '脚装備', '靴')
SET_NAMES = ('通常攻撃', 'ウェポンスキル', '魔法', '未取得を含む例')

# Stable groups are a proposal for review, not an adopted gameplay priority list.
# Each entry is the production key, unit, and a compact, unambiguous label.
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


@dataclass(frozen=True)
class ReviewItem:
    key: str
    slot: int
    item_id: int
    position: int
    name: str
    path: str
    description: str | None
    raw_augments: tuple[str, ...]
    normalized_augments: tuple[str, ...]
    decoded: bool = True

    @property
    def label(self):
        return f'{self.name} / Path {self.path}'


class ReviewData:
    def __init__(self):
        self.items = {}
        for part in range(16):
            for variant in range(4):
                key = f'{part}:{variant}'
                # Same name and ID for multiple individual Paths; position differs.
                name = f'試作の{PARTS[part]}'
                description = 'HP+25 MP+10 STR+5 DEX+6 VIT+4 AGI+5 INT+3 MND+3 CHR+2\n'
                description += '攻+20 命中+18 飛攻+10 飛命+12 魔命+15 魔攻+6\n'
                description += '防+55 回避+20 魔回避+30 魔防+2'
                if part == 0:
                    description += '\n短剣スキル+242 魔命スキル+215 魔法ダメージ+108 TPボーナス+250'
                if part in (4, 8, 9, 14, 15):
                    description += '\nヘイスト+5% 被ダメージ-5% 被物理ダメージ-1% 被魔法ダメージ-2% 詠唱中断率-4%'
                if part in (0, 8):
                    description += ('\nモクシャ+5 モクシャII+2 物理ダメージ上限+3%'
                                    ' 被物理ダメージII-3% 被魔法ダメージII-4% マジックバーストダメージII+2%')
                if part in (5, 10, 12, 13):
                    description += ('\nストアTP+8 ダブルアタック+3% トリプルアタック+1%'
                                    ' クリティカルヒット+2% ウェポンスキルのダメージ+4%'
                                    ' ウェポンスキルの命中+3 連携ボーナス+2.5%'
                                    ' ファストキャスト+3% マジックバーストダメージ+2%')
                if part == 12:
                    description += '\nHP+3% リジェネ+2\n潜在能力: 攻+40'
                normalized = (
                    ('命中+10', 'ストアTP+4', '魔命+5'),
                    ('STR+10', 'ウェポンスキルのダメージ+5%', '攻+15'),
                    ('魔命+20', '魔攻+10', 'ファストキャスト+2%'),
                    (),
                )[variant]
                raw = (
                    ('Accuracy+10', '"Store TP"+4', '"Mag. Acc."+5'),
                    ('STR+10', 'Weapon skill damage +5%', 'Attack+15'),
                    ('"Mag. Acc."+20', '"Mag.Atk.Bns."+10', '"Fast Cast"+2'),
                    (),
                )[variant]
                if part in (0, 8) and variant == 2:
                    extra = ('モクシャ+3', 'モクシャII+1', '物理ダメージ上限+2%',
                             '被物理ダメージ-1%', '被物理ダメージII-2%',
                             '被魔法ダメージ-2%', '被魔法ダメージII-3%',
                             'マジックバーストダメージ+1%', 'マジックバーストダメージII+3%')
                    normalized += extra
                    raw += extra
                self.items[key] = ReviewItem(key, part, 1000 + part, part * 4 + variant + 1,
                                            name, 'ABC?'[variant], description, raw, normalized,
                                            variant != 3)
        augmented = tuple(AugmentItem(i.position, i.item_id, 1, '00' * 24,
                                     'decoded' if i.decoded else 'unsupported',
                                     i.normalized_augments, i.path if i.decoded else None, None)
                          for i in self.items.values())
        export = AugmentExport('2026-11-06T00:00:00Z', 1, 'Synthetic', 0,
                               (AugmentBag(12, 'ready', augmented),))
        self.observation = AugmentObservation(export, frozenset({12}), ())
        self.master = {i.item_id: {'name': i.name, 'description': i.description}
                       for i in self.items.values()}
        self.sets = [[f'{part}:{variant}' for part in range(16)] for variant in (0, 1, 2, 0)]
        self.sets[3][4] = '4:3'

    def report(self, selection):
        slots = []
        for part, key in enumerate(selection):
            if key in ('keep', 'remove'):
                slots.append(Slot(SLOT_KEYS[part], key, None, None, None, ''))
            else:
                item = self.items[key]
                slots.append(Slot(SLOT_KEYS[part], 'equip', item.item_id, 12, item.position, ''))
        return summarize(Equipset(1, Text('合成データ', '', 'cp932'), tuple(slots)),
                         self.master, self.observation)

    def label(self, key):
        return {'keep': '変更しない（実行前の装備は未確定）', 'remove': '装備を外す'}.get(key) or self.items[key].label


def totals(report):
    return {(name, unit): value for name, unit, value in report.totals}


def incomplete(report):
    return any('未確認' in line or '未取得' in line or '未確定' in line for _, line in report.excluded)


def number(value, unit='', signed=False):
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return ('+' if signed and value > 0 else '') + text + unit
