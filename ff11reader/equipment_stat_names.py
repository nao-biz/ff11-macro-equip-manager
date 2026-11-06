"""Semantic names and implied units for equipment/decoded augment text.

Windower output spellings: docs/reference/augment-stat-names.md.
Matching is exact after typography cleanup; qualifiers and tiers stay intact.
"""
import re
import unicodedata


def key(name):
    name = unicodedata.normalize('NFKC', name)
    return re.sub(r'[\s.\"“”「」]', '', name).casefold()


# Japanese name, implied unit, accepted source spellings.
DEFINITIONS = (
    ('命中', '', ('Accuracy',)), ('攻', '', ('Attack', '攻撃', '攻撃力')),
    ('飛命', '', ('Rng.Acc.', 'Ranged Accuracy')), ('飛攻', '', ('Rng.Atk.', 'Ranged Attack')),
    ('魔命', '', ('Mag. Acc.', 'Magic Accuracy')), ('魔攻', '', ('Mag.Atk.Bns.', 'Magic Attack Bonus', '魔法攻撃力')),
    ('魔防', '', ('Mag.Def.Bns.', 'Magic Defense Bonus', '魔法防御力')),
    ('魔法ダメージ', '', ('Magic dmg.', 'Mag. Dmg.', '/Mag. Dmg.')),
    ('回避', '', ('Evasion', 'Eva.')), ('魔回避', '', ('Mag. Evasion', 'Mag. Eva.', '/Mag. Eva.', 'Magic Evasion')),
    ('防', '', ('DEF', 'Defense', '防御', '防御力')), ('敵対心', '', ('Enmity',)),
    ('ヘイスト', '%', ('Haste',)), ('ファストキャスト', '%', ('Fast Cast',)),
    ('ストアTP', '', ('Store TP',)), ('モクシャ', '', ('Subtle Blow',)),
    ('モクシャII', '', ('Subtle Blow II',)), ('二刀流', '', ('Dual Wield',)),
    ('ダブルアタック', '%', ('Dbl.Atk.', 'Double Attack')),
    ('トリプルアタック', '%', ('Triple Atk.', 'Triple Attack')),
    ('クワッドアタック', '%', ('Quadruple Attack',)),
    ('クリティカルヒット', '%', ('Crit.hit rate', 'Critical hit rate', 'クリティカルヒット率')),
    ('クリティカルヒットダメージ', '%', ('Crit. hit damage', 'Critical hit damage')),
    ('被ダメージ', '%', ('Damage taken',)),
    ('被物理ダメージ', '%', ('Phys. dmg. taken', 'Physical damage taken')),
    ('被物理ダメージII', '%', ('Phys. dmg. taken II', 'Physical damage taken II')),
    ('被魔法ダメージ', '%', ('Magic dmg. taken', 'Magic damage taken')),
    ('被魔法ダメージII', '%', ('Magic dmg. taken II', 'Magic damage taken II')),
    ('被ブレスダメージ', '%', ('Breath dmg. taken', 'Breath damage taken')),
    ('物理ダメージ上限', '%', ('Physical damage limit', 'Phys. dmg. limit', '物理ダメージ上限アップ')),
    ('ウェポンスキルのダメージ', '%', ('Weapon skill damage', 'ウェポンスキルダメージ', 'WSダメージ')),
    ('ウェポンスキルの命中', '', ('Weapon skill accuracy', 'WS命中')),
    ('マジックバーストダメージ', '%', ('Magic burst dmg.', 'Magic burst damage', 'MBダメージ')),
    ('マジックバーストダメージII', '%', ('Magic burst dmg. II', 'Magic burst damage II', 'MBダメージII')),
    ('TPボーナス', '', ('TP Bonus',)), ('連携ボーナス', '%', ('Skillchain dmg.', 'Skillchain damage', 'Skillchain bonus')),
    ('詠唱中断率', '%', ('Spell interruption rate down',)),
    ('ケアル回復量', '%', ('Cure potency',)), ('ケアル回復量II', '%', ('Cure potency II',)),
    ('ケアル詠唱時間', '%', ('Cure spellcasting time',)), ('被ケアル回復量', '%', ('Potency of Cure effect received',)),
    ('リジェネ', '', ('Regen',)), ('リフレシュ', '', ('Refresh',)), ('リゲイン', '', ('Regain',)),
    ('ヒーリングHP', '', ('HP recovered while healing',)), ('ヒーリングMP', '', ('MP recovered while healing',)),
    ('移動速度', '%', ('Movement speed',)), ('魔命スキル', '', ('Magic Accuracy skill',)),
    ('格闘スキル', '', ('Hand-to-Hand skill',)), ('短剣スキル', '', ('Dagger skill',)),
    ('片手剣スキル', '', ('Sword skill',)), ('両手剣スキル', '', ('Great Sword skill',)),
    ('片手斧スキル', '', ('Axe skill',)), ('両手斧スキル', '', ('Great Axe skill',)),
    ('両手鎌スキル', '', ('Scythe skill',)), ('両手槍スキル', '', ('Polearm skill',)),
    ('片手刀スキル', '', ('Katana skill',)), ('両手刀スキル', '', ('Great Katana skill',)),
    ('片手棍スキル', '', ('Club skill',)), ('両手棍スキル', '', ('Staff skill',)),
    ('弓術スキル', '', ('Archery skill',)), ('射撃スキル', '', ('Marksmanship skill',)),
    ('投てきスキル', '', ('Throwing skill',)), ('盾スキル', '', ('Shield skill',)),
    ('神聖魔法スキル', '', ('Divine magic skill',)), ('回復魔法スキル', '', ('Healing magic skill',)),
    ('強化魔法スキル', '', ('Enha.mag. skill', 'Enhancing magic skill')),
    ('弱体魔法スキル', '', ('Enfb.mag. skill', 'Enfeebling magic skill')),
    ('精霊魔法スキル', '', ('Elem. magic skill', 'Elemental magic skill')),
    ('暗黒魔法スキル', '', ('Dark magic skill',)), ('召喚魔法スキル', '', ('Summoning magic skill',)),
    ('忍術スキル', '', ('Ninjutsu skill',)), ('歌唱スキル', '', ('Singing skill',)),
    ('弦楽器スキル', '', ('String instrument skill',)), ('管楽器スキル', '', ('Wind instrument skill',)),
    ('青魔法スキル', '', ('Blue Magic skill',)),
)
NAMES = {key(alias): (name, unit) for name, unit, aliases in DEFINITIONS for alias in (name, *aliases)}
NAMES.update({key(n): (n, '') for n in ('HP', 'MP', 'STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR')})


def normalize(name, unit, value):
    identity = NAMES.get(key(name))
    if identity:
        canonical, implied = identity
        if key(name) == key('Spell interruption rate down'):
            value = -abs(value)
        return canonical, unit or implied, value
    # Preserve extensible Japanese properties, but don't publish unknown English
    # as a second stat or guess away a condition/recipient.
    if re.search(r'[A-Za-z]', name) or any(c in name for c in '\"“”「」'):
        return None
    return name, unit, value
