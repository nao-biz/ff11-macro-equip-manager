"""Conservative unconditional equipment bonuses; unknown effects retain provenance."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from .equipment_stat_parser import analyze_line, parse_line, path_metadata

BASE=('HP','MP','STR','DEX','VIT','AGI','INT','MND','CHR')

@dataclass(frozen=True)
class EquipmentStats:
    totals: tuple[tuple[str,str,Decimal], ...]
    excluded: tuple[tuple[str,str], ...]
    included: tuple[tuple[str,str], ...]
    incomplete: bool = False
    available: bool = True
    parts: tuple = ()
    unparsed: tuple = ()
    missing: tuple = ()
    uncertain: frozenset = frozenset()


def summarize(equipset, items, observation=None, names=None):
    parts = tuple(((s.name, s.action, s.item_id, s.container, s.index),
                   _slot_stats(s, items, observation, names)) for s in equipset.slots)
    totals = defaultdict(int)
    for _, report in parts:
        for name, unit, value in report.totals:
            totals[name, unit] += value
    return EquipmentStats(_ordered(totals),
                          tuple(line for _, p in parts for line in p.excluded),
                          tuple(line for _, p in parts for line in p.included),
                          any(p.incomplete for _, p in parts),
                          not parts or any(p.available for _, p in parts), parts,
                          tuple(line for _, p in parts for line in p.unparsed),
                          tuple(line for _, p in parts for line in p.missing),
                          frozenset(key for _, p in parts for key in p.uncertain))


def _ordered(totals):
    ordered = sorted(totals, key=lambda k: (BASE.index(k[0]) if k[0] in BASE else len(BASE), k))
    return tuple((name, unit, totals[name, unit]) for name, unit in ordered)


def _slot_stats(slot, items, observation, names):
    totals=defaultdict(int);excluded=[];included=[];incomplete=False
    unparsed=[];missing=[];uncertain=set()
    available = False
    def add(source,line):
        nonlocal available
        parsed=analyze_line(line,names)
        for name,unit,number in parsed.values:totals[name,unit]+=number
        if parsed.values:
            included.append((source,line));available=True
        if parsed.outside or parsed.unparsed:excluded.append((source,line))
        if parsed.unparsed:unparsed.append((source,line))
        uncertain.update(parsed.uncertain)
        return parsed.continuation
    def unavailable(source, message):
        nonlocal incomplete
        excluded.append((source,message));missing.append((source,message));incomplete=True
    source=slot.name
    if slot.action=='remove':
        available = True
    elif slot.action!='equip':
        unavailable(source, '維持する装備が未確定' if slot.action=='keep' else '装備指定を解釈できません')
    else:
        master=items.get(slot.item_id,{})
        source += ' / '+(master.get('name') or str(slot.item_id))
        description=master.get('description')
        if description is None:unavailable(source,'装備説明が未取得')
        else:
            available = True
            conditional=False
            for line in description.splitlines():
                if conditional:
                    if line.strip():excluded.append((source,line))
                else:conditional=add(source,line)
        augmented=observation.item(slot) if observation else None
        if augmented is None or augmented.decode_state!='decoded':
            unavailable(source,'オグメ能力が未確認')
        else:
            for line in augmented.augments:
                add(source+' / オグメ',line)
            if augmented.path and not any(line.strip() and not path_metadata(line) for line in augmented.augments):
                unavailable(source,'Path '+augmented.path+' の能力が未取得')
    return EquipmentStats(_ordered(totals),tuple(excluded),tuple(included),incomplete,available or not incomplete,
                          unparsed=tuple(unparsed),missing=tuple(missing),uncertain=frozenset(uncertain))


def comparison_kind(current, trial, key=None):
    """Unchanged contributions cancel even when their absolute values are unknown."""
    if trial is None:
        return None
    pairs = [(current, trial)]
    if current.parts and trial.parts:
        before = {ref[0]: (ref, report) for ref, report in current.parts}
        after = {ref[0]: (ref, report) for ref, report in trial.parts}
        if len(before) == len(current.parts) and len(after) == len(trial.parts):
            pairs = [(before[name][1] if name in before else None,
                      after[name][1] if name in after else None)
                     for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
    changed = [report for pair in pairs for report in pair if report is not None]
    if any(report.incomplete and not report.available for report in changed):
        return 'unavailable'
    return 'partial' if any(report.incomplete or key in report.uncertain for report in changed) else 'complete'
