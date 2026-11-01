"""Pure same-character moves to empty equipment-set numbers."""
from dataclasses import replace
from .domain import Slot, Text
from .macro_links import is_empty, retarget_reference
from .edit_values import value, integer


def vacant(equipment):return equipment.title.display=='' and is_empty(equipment)


def plan_move(character,source,target):
    from .editing import Edit, Change, macro_key
    if not integer(source,1,200) or not integer(target,1,200) or source==target:raise ValueError('異なる移動元・移動先番号を指定してください。')
    sets={e.number:e for e in character.equipsets}
    if source not in sets or target not in sets:raise ValueError('移動元または移動先を読み取れていません。')
    before=sets[source];destination=sets[target]
    if not vacant(destination):raise ValueError('移動先は名前が空で、全枠が「変更しない」のセットを選んでください。')
    if vacant(before):raise ValueError('移動元は空の装備セットです。')
    empty=replace(before,title=Text('',destination.title.raw_hex,'draft'),slots=tuple(Slot(s.name,'keep',None,None,None,s.raw_hex) for s in destination.slots))
    moved=replace(before,number=target)
    changes=[Change(character.folder_id,'equipsets',(source,),before,empty),Change(character.folder_id,'equipsets',(target,),destination,moved)]
    for macro in character.macros:
        updated=replace(macro,lines=tuple(retarget_reference(line,source,target) for line in macro.lines))
        if value(macro)!=value(updated):changes.append(Change(character.folder_id,'macros',macro_key(macro),macro,updated))
    return Edit(f'装備セットを移動 {source:03} → {target:03}',tuple(changes),((character.folder_id,source,target),))
