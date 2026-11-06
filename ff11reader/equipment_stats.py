"""Conservative unconditional equipment bonuses; unknown effects retain provenance."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

BASE=('HP','MP','STR','DEX','VIT','AGI','INT','MND','CHR')
ALIASES={'Accuracy':'命中','Attack':'攻','Rng.Acc.':'飛命','Rng.Atk.':'飛攻','Mag. Acc.':'魔命',
 '"Mag.Atk.Bns."':'魔攻','Magic dmg.':'魔法ダメージ','Evasion':'回避','Haste':'ヘイスト',
 'Store TP':'ストアTP','"Dbl.Atk."':'ダブルアタック','"Triple Atk."':'トリプルアタック'}
# Names are open-ended: equipment skills and new properties need no registry.
TOKEN=re.compile(r'([^+\-\d%:;、,\n]+?)\s*([+-]\d+(?:\.\d+)?)(%?)')
DEFENSE=re.compile(r'防(\d+)')

@dataclass(frozen=True)
class EquipmentStats:
    totals: tuple[tuple[str,str,Decimal], ...]
    excluded: tuple[tuple[str,str], ...]
    included: tuple[tuple[str,str], ...]


def parse_line(line):
    line=unicodedata.normalize('NFKC',line).strip()
    line=DEFENSE.sub(r'防+\1',line)
    matches=list(TOKEN.finditer(line))
    remainder=TOKEN.sub('',line)
    if not matches or remainder.strip(' ,、;'):
        return None
    return [(ALIASES.get(m[1].strip(),m[1].strip()),m[3],Decimal(m[2])) for m in matches]


def summarize(equipset, items, observation=None):
    totals=defaultdict(int);excluded=[];included=[]
    def add(source,line):
        if not line.strip():return
        values=parse_line(line)
        if values is None:excluded.append((source,line));return
        for name,unit,number in values:totals[name,unit]+=number
        included.append((source,line))
    for slot in equipset.slots:
        source=slot.name
        if slot.action=='remove':continue
        if slot.action=='keep':excluded.append((source,'維持する装備が未確定'));continue
        if slot.action!='equip':excluded.append((source,'装備指定を解釈できません'));continue
        master=items.get(slot.item_id,{})
        source += ' / '+(master.get('name') or str(slot.item_id))
        description=master.get('description')
        if description is None:excluded.append((source,'装備説明が未取得'))
        else:
            conditional=False
            for line in description.splitlines():
                if any(marker in line for marker in (':','：','潜在','コンビネーション','セット効果','ユニティ','エンチャント','日中','夜間','天候','曜日','発動','装備時','使用時')):
                    conditional=True
                if conditional:
                    if line.strip():excluded.append((source,line))
                else:add(source,line)
        augmented=observation.item(slot) if observation else None
        if augmented is None or augmented.decode_state!='decoded':
            excluded.append((source,'オグメ能力が未確認'))
        else:
            for line in augmented.augments:
                add(source+' / オグメ',line)
            if augmented.path and not augmented.augments:
                excluded.append((source,'Path '+augmented.path+' の能力が未取得'))
    ordered=sorted(totals,key=lambda k:(BASE.index(k[0]) if k[0] in BASE else len(BASE),k))
    return EquipmentStats(tuple((name,unit,totals[name,unit]) for name,unit in ordered),tuple(excluded),tuple(included))
