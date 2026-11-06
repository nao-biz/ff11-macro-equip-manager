"""Stable display order for equipment bonuses, independent of their values."""
import unicodedata
from .equipment_stats import BASE

GROUPS=(
    BASE,
    ('命中','攻','飛命','飛攻','ヘイスト','二刀流','ダブルアタック','トリプルアタック',
     'クワッドアタック','ストアTP','クリティカルヒット','クリティカルヒットダメージ',
     'ウェポンスキルの命中','ウェポンスキルのダメージ','ウェポンスキルダメージ',
     '格闘スキル','短剣スキル','片手剣スキル','両手剣スキル','片手斧スキル','両手斧スキル',
     '両手鎌スキル','両手槍スキル','片手刀スキル','両手刀スキル','片手棍スキル','両手棍スキル',
     '弓術スキル','射撃スキル','投てきスキル','スナップショット','ラピッドショット'),
    ('魔命','魔攻','魔法ダメージ','魔命スキル','ケアル回復量','ケアル回復量II',
     'ファストキャスト','ケアル詠唱時間','詠唱中断率','コンサーブMP',
     '神聖魔法スキル','回復魔法スキル','強化魔法スキル','弱体魔法スキル',
     '精霊魔法スキル','暗黒魔法スキル','召喚魔法スキル','忍術スキル',
     '歌唱スキル','弦楽器スキル','管楽器スキル','青魔法スキル','風水魔法スキル','風水鈴スキル'),
    ('防','回避','魔回避','魔防','被ダメージ','被物理ダメージ','被魔法ダメージ',
     '被ブレスダメージ','盾スキル','受け流しスキル','ガードスキル'),
    ('移動速度','敵対心','リジェネ','リフレシュ','リゲイン','モクシャ','モクシャII'),
)
PRIORITY=('攻','攻撃','命中','飛攻','飛命','魔攻','魔命','防','回避','魔防','魔回避',
          '被ダメージ','被物理ダメージ','被魔法ダメージ','ヘイスト','敵対心',
          'ダブルアタック','トリプルアタック','ストアTP','モクシャ',
          'ウェポンスキルのダメージ','ウェポンスキルダメージ','連携ボーナス',
          'マジックバーストダメージ')
ORDER={name:(0,index) for index,name in enumerate(BASE+PRIORITY)}
for group,names in enumerate(GROUPS[1:],1):
    for index,name in enumerate(names):
        ORDER.setdefault(name,(group,index))
LABELS={'攻':'攻撃','ウェポンスキルのダメージ':'WSダメージ',
        'ウェポンスキルダメージ':'WSダメージ','マジックバーストダメージ':'MBダメージ'}



def display_totals(totals):
    """Keep every row; unknown names follow the known properties by name."""
    return sorted(totals,key=lambda row:(*ORDER.get(row[0],(len(GROUPS),0)),row[0],row[1]))


def compact_properties(totals):
    """Pair short fields in reading order; retain full long or unknown names."""
    fields=[f'{LABELS.get(name,name)} {value:+}{unit}'
            for name,unit,value in display_totals(totals) if name not in BASE]
    def width(text):
        return sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in text)
    lines=[]
    index=0
    while index<len(fields):
        first=fields[index]
        if index+1<len(fields) and width(first)<=20 and width(fields[index+1])<=20:
            lines.append(first+' '*(22-width(first))+fields[index+1])
            index+=2
        else:
            lines.append(first)
            index+=1
    return lines
