"""One guarded transaction for equipment movement and its macro references."""
from dataclasses import dataclass, asdict
from pathlib import Path
import re
from . import equipment_saving, macro_saving
from .edit_values import value
from .saving import digest, require_game_closed, atomic_replace, locked_read
from .file_transaction import execute_batch, write_json
from .codecs import equipsets, macros


@dataclass(frozen=True)
class CombinedSavePlan:
    character: str
    equipment: equipment_saving.EquipmentSavePlan
    macro: macro_saving.MacroSavePlan | None
    dependencies: tuple
    members: tuple

    @property
    def files(self):return self.equipment.files+(self.macro.files if self.macro else ())
    @property
    def deferred(self):return self.equipment.deferred+(self.macro.deferred if self.macro else 0)


def prepare_combined_save(saved,working,folder,transfers):
    if not transfers:raise ValueError('一括保存する移動がありません。')
    equipment=equipment_saving.prepare_equipment_save(saved,working,folder,'all',transfers)
    before=next(c for c in saved.characters if c.folder_id==folder)
    after=next(c for c in working.characters if c.folder_id==folder)
    macro=macro_saving.prepare_macro_save(saved,working,folder,'all') if any(value(a)!=value(b) for a,b in zip(before.macros,after.macros)) else None
    dependencies=dict(equipment.dependencies)
    if macro:dependencies.update(macro.dependencies)
    parent=Path(equipment.files[0].target).resolve().parent
    for record in saved.sources:
        path=Path(record['path']).resolve()
        if path.parent==parent and re.fullmatch(r'mcr[0-9]*\.dat',path.name):
            if digest(path.read_bytes())!=record['sha256']:raise ValueError('参照元のマクロが変わりました。再読み込みしてください。')
            dependencies[str(path)]=record['sha256']
    if equipment.deferred or (macro and macro.deferred):raise ValueError('保存対象に含められない変更があります。')
    files=equipment.files+(macro.files if macro else ())
    members=tuple((f.target,digest(f.replacement)) for f in files)
    return CombinedSavePlan(folder,equipment,macro,tuple(sorted(dependencies.items())),members)


def serialize_change(change):
    if isinstance(change,macro_saving.LineChange):
        return {'address':change.address,'line':change.line,'before':change.before,'after':change.after,
                'before_token_ids':[t.identity for t in change.original_tokens or ()],
                'after_token_ids':[t.identity for t in change.tokens or ()]}
    return asdict(change)


def execute_combined_save(plan,backup_root):
    require_game_closed()
    if plan.members!=tuple((f.target,digest(f.replacement)) for f in plan.files):raise ValueError('依存グループの保存対象が欠落または変更されています。')
    if type(plan.equipment) is not equipment_saving.EquipmentSavePlan or not plan.equipment.transfers or plan.equipment.character!=plan.character or plan.equipment.scope!='all':raise ValueError('移動の一括保存計画が不正です。')
    root,validate_equipment=equipment_saving.validate_equipment_plan(plan.equipment)
    checks=[validate_equipment];required=dict(plan.equipment.dependencies)
    if plan.macro:
        if type(plan.macro) is not macro_saving.MacroSavePlan or plan.macro.character!=plan.character or plan.macro.scope!='all':raise ValueError('参照マクロの保存範囲が不正です。')
        macro_root,validate_macro=macro_saving.validate_macro_plan(plan.macro)
        if macro_root!=root:raise ValueError('保存先が異なります。')
        checks.append(validate_macro)
        for p,h in plan.macro.dependencies:
            if p in required and required[p]!=h:raise ValueError('依存資料の指紋が一致しません。')
            required[p]=h
    parent=root/'USER'/plan.character
    dependencies={Path(p).resolve():h for p,h in plan.dependencies}
    if len(dependencies)!=len(plan.dependencies):raise ValueError('依存資料が重複しています。')
    macro_paths={p.resolve() for p in parent.glob('mcr*.dat') if re.fullmatch(r'mcr[0-9]*\.dat',p.name)}
    expected={Path(p).resolve() for p in required}|macro_paths
    if set(dependencies)!=expected or any(dependencies.get(Path(p).resolve())!=h for p,h in required.items()):raise ValueError('一括保存の依存資料が不足または変更されています。')
    def validate(data):
        if macro_paths!={p.resolve() for p in parent.glob('mcr*.dat') if re.fullmatch(r'mcr[0-9]*\.dat',p.name)}:raise ValueError('マクロファイルが増減しました。')
        for check in checks:check(data)
    def decode(file,data):
        if type(file) is equipment_saving.EquipmentFile:return equipsets(data,file.page)
        if type(file) is macro_saving.MacroFile:return macros(data,file.page)
        raise ValueError('保存ファイルの形式が不正です。')
    return execute_batch(plan,backup_root,root,validate,None,'equipment-move','.ff11-move-',serialize_change,require_game_closed,write_json,atomic_replace,decode_file=decode)


def restore_combined_backup(folder,apply=False):
    from contextlib import ExitStack
    import json
    folder=Path(folder).resolve();receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('kind')!='equipment-move' or not receipt.get('files'):raise ValueError('移動の一括保存バックアップを指定してください。')
    entries=[];seen=set();parent=None
    for item in receipt['files']:
        target=Path(item['target']).resolve();page=item['page'];backup=(folder/item['backup']).resolve()
        if not re.fullmatch('[0-9a-fA-F]+',receipt['character']) or target.parent.name!=receipt['character'] or target.parent.parent.name.upper()!='USER':raise ValueError('復元先が不正です。')
        if parent is None:parent=target.parent
        if parent!=target.parent or target in seen or backup.parent!=folder:raise ValueError('復元先またはバックアップが不正です。')
        seen.add(target);raw=backup.read_bytes()
        if type(page) is not int:raise ValueError('ファイル番号が不正です。')
        if target.name==f'es{page}.dat' and 0<=page<10:equipsets(raw,page)
        elif target.name==('mcr'+(str(page) if page else '')+'.dat') and 0<=page<400:macros(raw,page)
        else:raise ValueError('復元ファイルが不正です。')
        if digest(raw)!=item['before_sha256'] or digest(target.read_bytes()) not in (item['before_sha256'],item['after_sha256']):raise ValueError('原本または保存先が変わっています。')
        entries.append((target,raw,item))
    if not apply:return tuple(str(p) for p,_,_ in entries)
    require_game_closed()
    with ExitStack() as stack:
        handles={}
        for p,raw,item in entries:
            handle=ExitStack();stack.enter_context(handle);handles[p]=handle
            current=handle.enter_context(locked_read(p))
            if digest(current) not in (item['before_sha256'],item['after_sha256']):raise ValueError('復元前にファイルが変わりました。')
        for p,raw,item in entries:
            require_game_closed();handles[p].close()
            if digest(p.read_bytes()) not in (item['before_sha256'],item['after_sha256']):raise ValueError('復元直前にファイルが変わりました。')
            atomic_replace(p,raw)
            if p.read_bytes()!=raw:raise OSError('復元の検証に失敗しました。')
    return tuple(str(p) for p,_,_ in entries)
