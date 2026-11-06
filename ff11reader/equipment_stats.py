"""Conservative unconditional equipment bonuses; unknown effects retain provenance."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata
from .equipment_stat_names import normalize

BASE=('HP','MP','STR','DEX','VIT','AGI','INT','MND','CHR')
# Names are open-ended: equipment skills and new properties need no registry.
TOKEN=re.compile(r'([^+\d%:;、,\n]+?)\s*([+-]\s*\d+(?:\.\d+)?)(%?)')
DEFENSE=re.compile(r'防(\d+)')

@dataclass(frozen=True)
class EquipmentStats:
    totals: tuple[tuple[str,str,Decimal], ...]
    excluded: tuple[tuple[str,str], ...]
    included: tuple[tuple[str,str], ...]
    incomplete: bool = False


def parse_line(line, names=None):
    line=unicodedata.normalize('NFKC',line).strip().replace('−','-')
    line=re.sub(r'詠唱中断率\s*(\d+(?:\.\d+)?)%ダウン',r'詠唱中断率-\1%',line)
    line=DEFENSE.sub(r'防+\1',line)
    matches=list(TOKEN.finditer(line))
    remainder=TOKEN.sub('',line)
    if not matches or remainder.strip(' ,、;'):
        return None
    values=[normalize(m[1].strip(),m[3],Decimal(re.sub(r'\s+','',m[2])),names) for m in matches]
    return values if all(v is not None for v in values) else None


def summarize(equipset, items, observation=None, names=None):
    totals=defaultdict(int);excluded=[];included=[];incomplete=False
    def add(source,line):
        nonlocal incomplete
        if not line.strip():return
        values=parse_line(line,names)
        if values is None:excluded.append((source,line));incomplete=True;return
        for name,unit,number in values:totals[name,unit]+=number
        included.append((source,line))
    for slot in equipset.slots:
        source=slot.name
        if slot.action=='remove':continue
        if slot.action=='keep':excluded.append((source,'維持する装備が未確定'));incomplete=True;continue
        if slot.action!='equip':excluded.append((source,'装備指定を解釈できません'));incomplete=True;continue
        master=items.get(slot.item_id,{})
        source += ' / '+(master.get('name') or str(slot.item_id))
        description=master.get('description')
        if description is None:excluded.append((source,'装備説明が未取得'));incomplete=True
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
            incomplete=True
        else:
            for line in augmented.augments:
                add(source+' / オグメ',line)
            if augmented.path and not augmented.augments:
                excluded.append((source,'Path '+augmented.path+' の能力が未取得'))
                incomplete=True
    ordered=sorted(totals,key=lambda k:(BASE.index(k[0]) if k[0] in BASE else len(BASE),k))
    return EquipmentStats(tuple((name,unit,totals[name,unit]) for name,unit in ordered),tuple(excluded),tuple(included),incomplete)
