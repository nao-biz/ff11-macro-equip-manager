"""Small synthetic resource pairs for isolated mocks/tests; no installed DATs."""
from ff11reader.equipment_stat_names import from_dictionary

PAIRS = (
    ('Accuracy%+d', '命中%+d'), ('Attack%+d', '攻%+d'),
    ('Mag. Acc.%+d', '魔命%+d'), ('"Mag. Atk. Bns."%+d', '魔攻%+d'),
    ('"Store TP"%+d', 'ストアTP%+d'), ('Haste%+d%%', 'ヘイスト%+d'),
    ('"Double Attack"%+d%%', 'ダブルアタック%+d%%'), ('"Fast Cast"%+d%%', 'ファストキャスト%+d%%'),
    ('Weapon skill damage%+d%%', 'ウェポンスキルのダメージ%+d%%'),
    ('Magic burst dmg.%+d%%', 'マジックバーストダメージ%+d%%'),
    ('Magic burst damage II%+d', 'マジックバーストダメージII%+d'),
    ('"Subtle Blow"%+d', 'モクシャ%+d'), ('"Subtle Blow II"%+d', 'モクシャII%+d'),
    ('Phys. dmg. taken%+d%%', '被物理ダメージ%+d%%'),
    ('Magic dmg. taken%+d%%', '被魔法ダメージ%+d%%'),
    ('Physical damage limit%+d%%', '物理ダメージ上限%+d%%'),
    ('Hand-to-Hand skill%+d', '格闘スキル%+d'), ('Dagger skill%+d', '短剣スキル%+d'),
    ('Magic Damage%+d', '魔法ダメージ%+d'),
    ('Spell interruption rate down %d%%', '詠唱中断率%d%%ダウン'),
    # Synthetic additional records exercise tier preservation, not live coverage.
    ('Phys. dmg. taken II%+d%%', '被物理ダメージII%+d%%'),
    ('Magic dmg. taken II%+d%%', '被魔法ダメージII%+d%%'),
)


def names():
    return from_dictionary({i: en for i, (en, ja) in enumerate(PAIRS)},
                           {i: ja for i, (en, ja) in enumerate(PAIRS)})
