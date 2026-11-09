"""Guarded macro text and storage-number persistence with token preservation."""
from contextlib import ExitStack
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import os
from uuid import uuid4
from .codecs import checked, macros, BAGS
from .macro_text import patch_text
from .edit_values import validate_structure, text_value
from .text_editing import remap_text
from .editing import macro_key
from .macro_inventory import assess_macro_inventory, parse_equip
from .saving import digest, locked_read, atomic_replace, require_game_closed
from .loaded_files import LoadedFiles
from .file_transaction import execute_batch, write_json
from .save_plan import DeferredChange, deferred_text, require_same_targets
from .macro_save_proposal import replay_macro_proposal


@dataclass(frozen=True)
class LineChange:
    address: tuple
    line: int
    before: str
    after: str
    original: bytes
    replacement: bytes
    provenance: bytes = b''
    tokens: tuple | None = None
    original_tokens: tuple | None = None


@dataclass(frozen=True)
class MacroFile:
    target: str
    page: int
    original: bytes
    replacement: bytes
    changes: tuple
    records: tuple = ()


@dataclass(frozen=True)
class MacroSavePlan:
    character: str
    files: tuple
    dependencies: tuple
    deferred_changes: tuple = ()
    scope: str = 'storage-fix'

    @property
    def deferred(self):return len(self.deferred_changes)


def patch_line(raw, before, after, resolver):
    """Map displayed character boundaries back to original bytes, including ATs."""
    if len(raw)!=61:raise ValueError('マクロ行のサイズが不正です。')
    displayed=''; boundaries=[0]; index=0
    while index<len(raw) and raw[index]:
        if raw[index]==0xFD and index+5<len(raw) and raw[index+5]==0xFD:
            name=resolver(raw[index+1:index+5])
            if name is None:raise ValueError('定型文を解決できません。')
            segment='【'+name+'】';index+=6
        else:
            byte=raw[index];size=2 if 0x81<=byte<=0x9f or 0xe0<=byte<=0xfc else 1
            segment=raw[index:index+size].decode('cp932',errors='strict');index+=size
        displayed+=segment
        boundaries.extend([None]*(len(segment)-1)+[index])
    if displayed!=before or index>=61:raise ValueError('マクロの元バイトと表示が一致しません。')
    command=parse_equip(before);new=parse_equip(after)
    if not command or not new or not command.valid or not new.valid or new.storage is None:
        raise ValueError('収納番号Fixの形式を確認してください。')
    start,end=command.storage_span or (command.item_end,command.item_end)
    inserted=str(new.storage) if command.storage_span else ' '+str(new.storage)
    if before[:start]+inserted+before[end:]!=after:raise ValueError('収納番号以外の変更が含まれています。')
    left,right=boundaries[start],boundaries[end]
    if left is None or right is None:raise ValueError('定型文の内部を変更することはできません。')
    payload=raw[:left]+inserted.encode('ascii')+raw[right:index]
    if len(payload)>60:raise ValueError('収納番号を追加するとマクロ行の60バイト上限を超えます。')
    # Keep the unused trailing bytes; only the new content and NUL are written.
    out=bytearray(raw);out[:len(payload)+1]=payload+b'\0'
    return bytes(out)


def patch_file(original,page,changes,records=()):
    checked(original,7624);out=bytearray(original);seen=set()
    record_keys=set()
    for address,before,base in records:
        book,palette,bank,key=address
        if (book-1)*10+palette-1!=page or bank not in ('ctrl','alt') or type(key) is not int or not 1<=key<=10 or address in record_keys or len(before)!=380 or len(base)!=380:raise ValueError('マクロ原本の配置が不正です。')
        record_keys.add(address)
        offset=24+((0 if bank=='ctrl' else 10)+key-1)*380
        if original[offset:offset+380]!=before:raise ValueError('マクロ原本が変わっています。')
        out[offset:offset+380]=base
    base_data=bytes(out)
    for change in changes:
        book,palette,bank,key=change.address
        if (book-1)*10+palette-1!=page or bank not in ('ctrl','alt') or not 1<=key<=10 or not 0<=change.line<=6:
            raise ValueError('マクロの保存位置が不正です。')
        identity=(change.address,change.line)
        if identity in seen:raise ValueError('保存位置が重複しています。')
        seen.add(identity)
        width=10 if change.line==0 else 61
        offset=24+((0 if bank=='ctrl' else 10)+key-1)*380+(370 if change.line==0 else 4+(change.line-1)*61)
        if base_data[offset:offset+width]!=change.original or len(change.replacement)!=width:
            raise ValueError('元のマクロ行が変わっています。')
        out[offset:offset+width]=change.replacement
    out[8:24]=hashlib.md5(out[24:]).digest()
    macros(bytes(out),page)
    return bytes(out)


def prepare_macro_save(saved,working,folder,scope='storage-fix', *, source_index=None):
    if scope not in ('storage-fix','all'):raise ValueError('保存範囲が不正です。')
    from .adapters import LocalReader
    from .dictionaries import resolve_token
    original=next(c for c in saved.characters if c.folder_id==folder)
    edited=next(c for c in working.characters if c.folder_id==folder)
    require_same_targets(original,edited)
    records=(source_index if source_index is not None else LoadedFiles(saved.sources)).records()
    parent=next((p.parent for p in records if p.parent.name==folder and p.parent.parent.name.upper()=='USER'),None)
    if parent is None or not re.fullmatch('[0-9a-fA-F]+',folder):raise ValueError('キャラクターの保存先を確認してください。')
    root=parent.parent.parent
    old={macro_key(m):m for m in original.macros}
    needs_dictionary=scope=='storage-fix' or any(
        (text_value(a)!=text_value(b) or (bool(m.raw_hex) and m.raw_hex!=old[macro_key(m)].raw_hex)) and (a.tokens or b.tokens or b'\xfd' in bytes.fromhex(a.raw_hex) or b'\xfd' in bytes.fromhex(b.raw_hex))
        for m in edited.macros
        if any(text_value(a)!=text_value(b) for a,b in zip(
            (old[macro_key(m)].title,*old[macro_key(m)].lines),(m.title,*m.lines)))
        for a,b in zip(old[macro_key(m)].lines,m.lines))
    reader=LocalReader(root);phrases=reader.load_phrases() if needs_dictionary else {}
    resolver=lambda token:resolve_token(token,phrases,saved.items)
    for source in reader.sources:
        p=Path(source['path']).resolve()
        if p not in records or source['sha256']!=records[p]['sha256']:raise ValueError('定型文データが変わりました。再読み込みしてください。')
    refs={(r.address,r.line):r for r in assess_macro_inventory(original,saved.items)} if scope=='storage-fix' else {}
    old={macro_key(m):m for m in original.macros};grouped={};deferred=[];record_bases={}
    for macro in edited.macros:
        key=macro_key(macro);before=old[key]
        address=f'ブック {macro.book:02} / パレット {macro.palette} / {macro.bank.upper()} {macro.key}'
        validate_structure(macro,'macros')
        relocated=scope=='all' and bool(macro.raw_hex) and macro.raw_hex!=before.raw_hex
        base=bytes.fromhex(macro.raw_hex) if relocated else b''
        if relocated and len(base)!=380:raise ValueError('マクロ原本は380バイト必要です。')
        semantic_changed=any(text_value(a)!=text_value(b) for a,b in zip((before.title,*before.lines),(macro.title,*macro.lines)))
        if not semantic_changed:continue
        if relocated:record_bases[key]=base
        if scope=='storage-fix' and before.title.display!=macro.title.display:
            deferred.append(DeferredChange(address+' / 名前','名前の変更は「ゲームへ書き戻す…」から保存できます。'))
        fields=list(enumerate(zip(before.lines,macro.lines),1))
        if scope=='all':fields.insert(0,(0,(before.title,macro.title)))
        for n,(a,b) in fields:
            if text_value(a)==text_value(b):
                if not relocated:continue
                from .codecs import text as decode_text
                field_raw=base[370:380] if n==0 else base[4+(n-1)*61:4+n*61]
                decoded=decode_text(field_raw,None if n==0 else resolver)
                if decoded.display==b.display and tuple(decoded.tokens or ())==tuple(b.tokens or ()):continue
            if scope=='storage-fix':
                ref=refs.get((key,n))
                if ref is None or ref.replacement is None or text_value(remap_text(a,ref.replacement))!=text_value(b):
                    deferred.append(DeferredChange(address+f' / {n}行目','手編集した行は「ゲームへ書き戻す…」から保存できます。'));continue
            try:
                raw=base[370:380] if relocated and n==0 else base[4+(n-1)*61:4+n*61] if relocated else bytes.fromhex(a.raw_hex)
                from .codecs import text as decode_text
                base_display=decode_text(raw,None if n==0 else resolver).display if relocated else a.display
                provenance=bytes.fromhex(b.raw_hex) if scope=='all' and n else b''
                replacement=(patch_line(raw,a.display,b.display,resolver) if scope=='storage-fix' else
                    patch_text(raw,base_display,b.display,resolver,title=n==0,provenance=provenance,tokens=b.tokens))
            except ValueError as exc:
                label='名前' if n==0 else f'{n}行目'
                raise ValueError(f'{address} / {label}: {exc}') from exc
            page=(macro.book-1)*10+macro.palette-1
            grouped.setdefault(page,[]).append(LineChange(key,n,a.display,b.display,raw,replacement,provenance,b.tokens,tuple(a.tokens or ())))
    if not grouped:raise ValueError('保存できるマクロの変更がありません。'+('\n'+deferred_text(deferred) if deferred else ''))
    files=[]
    for page,changes in sorted(grouped.items()):
        target=parent/('mcr'+(str(page) if page else '')+'.dat')
        if target not in records:raise ValueError('読込元のマクロファイルが見つかりません。')
        raw=target.read_bytes()
        if digest(raw)!=records[target]['sha256']:raise ValueError('マクロが変更されています。再読み込みしてください。')
        records_for_file=[]
        for address,base in record_bases.items():
            book,palette,bank,key=address
            if (book-1)*10+palette-1!=page:continue
            offset=24+((0 if bank=='ctrl' else 10)+key-1)*380
            records_for_file.append((address,raw[offset:offset+380],base))
        records_for_file=tuple(records_for_file)
        files.append(MacroFile(str(target),page,raw,patch_file(raw,page,changes,records_for_file),tuple(changes),records_for_file))
    required={Path(f.target) for f in files}
    if scope=='storage-fix':required.update(parent/name for name in BAGS)
    # Item/phrase dictionaries are part of name-to-ID verification.
    if needs_dictionary:required.update(p for p in records if not p.is_relative_to(root/'USER'))
    dependencies=[]
    for p in sorted(required):
        raw=p.read_bytes()
        if p not in records or digest(raw)!=records[p]['sha256']:raise ValueError('読込元が変更されています。再読み込みしてください。')
        dependencies.append((str(p),digest(raw)))
    return MacroSavePlan(folder,tuple(files),tuple(dependencies),tuple(deferred),scope)


def validate_macro_plan(plan):
    from .snapshot_loading import load_macro_validation_snapshot
    if not plan.files:raise ValueError('保存対象がありません。')
    root=Path(plan.files[0].target).resolve().parent.parent.parent
    targets={Path(f.target).resolve() for f in plan.files}
    if len(targets)!=len(plan.files):raise ValueError('保存先が重複しています。')
    for f in plan.files:
        p=Path(f.target).resolve()
        expected=root/'USER'/plan.character/('mcr'+(str(f.page) if f.page else '')+'.dat')
        if p!=expected or not 0<=f.page<400:raise ValueError('保存先が不正です。')
    def validate(data):
        # Rebuild the domain proposal from the locked game data.
        fresh=load_macro_validation_snapshot(root, plan.character, (f.page for f in plan.files))
        changes={(change.address,change.line):change for f in plan.files for change in f.changes}
        bases={address:base.hex() for f in plan.files for address,original,base in f.records}
        before,proposed=replay_macro_proposal(fresh,plan.character,changes,bases)
        verified=prepare_macro_save(before,proposed,plan.character,plan.scope)
        if verified.files!=plan.files or verified.dependencies!=plan.dependencies:raise ValueError('保存計画が現在のマクロ変更と一致しません。')
    return root,validate


def execute_macro_save(plan,backup_root):
    require_game_closed()
    root,validate=validate_macro_plan(plan)
    return execute_batch(plan,backup_root,root,validate,macros,'macro-edit' if plan.scope=='all' else 'macro-storage-fix','.ff11-macro-',
                         lambda c:{'address':c.address,'line':c.line,'before':c.before,'after':c.after,
                                   'before_token_ids':[t.identity for t in c.original_tokens or ()],
                                   'after_token_ids':[t.identity for t in c.tokens or ()]},
                         require_game_closed,write_json,atomic_replace)


def restore_macro_backup(folder,apply=False):
    """Validate a complete backup set; retry safely after an interrupted restore."""
    folder=Path(folder).resolve();receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('kind') not in ('macro-storage-fix','macro-edit') or not receipt.get('files'):raise ValueError('マクロのバックアップを指定してください。')
    entries=[];seen=set();root=None
    for entry in receipt['files']:
        target=Path(entry['target']).resolve();page=entry['page']
        if not isinstance(page,int) or not 0<=page<400:raise ValueError('バックアップのパレット番号が不正です。')
        name='mcr'+(str(page) if page else '')+'.dat'
        if target.name!=name or target.parent.name!=receipt['character'] or target.parent.parent.name.upper()!='USER':raise ValueError('復元先が不正です。')
        if root is None:root=target.parent.parent.parent
        if target.parent.parent.parent!=root or target in seen:raise ValueError('復元先に重複があるか、異なるインストール先のファイルが含まれています。')
        seen.add(target)
        backup=(folder/entry['backup']).resolve()
        if backup.parent!=folder:raise ValueError('バックアップのパスが不正です。')
        raw=backup.read_bytes()
        if digest(raw)!=entry['before_sha256']:raise ValueError('バックアップが破損しています。')
        macros(raw,page)
        if digest(target.read_bytes()) not in (entry['before_sha256'],entry['after_sha256']):raise ValueError('保存後にファイルが変更されたため、復元を保留しました。')
        entries.append((target,raw,entry))
    if not apply:return tuple(str(p) for p,_,_ in entries)
    require_game_closed()
    with ExitStack() as stack:
        locks={}
        for target,raw,entry in entries:
            handle=ExitStack();stack.enter_context(handle);locks[target]=handle
            current=handle.enter_context(locked_read(target))
            if digest(current) not in (entry['before_sha256'],entry['after_sha256']):raise ValueError('復元前にファイルが変わりました。')
        for target,raw,entry in entries:
            require_game_closed();locks[target].close()
            if digest(target.read_bytes()) not in (entry['before_sha256'],entry['after_sha256']):raise ValueError('置換直前にファイルが変わりました。')
            atomic_replace(target,raw)
            if target.read_bytes()!=raw:raise OSError('復元後検証に失敗しました。')
    return tuple(str(p) for p,_,_ in entries)


def sync_macro_raw(files, macro):
    """Normalize model provenance from the verified file output."""
    page = (macro.book-1)*10+macro.palette-1
    file = next((f for f in files if f.page == page), None)
    offset = 24+((0 if macro.bank == 'ctrl' else 10)+macro.key-1)*380
    raw = file.replacement[offset:offset+380] if file else bytes.fromhex(macro.raw_hex)
    if not raw: return macro
    return replace(macro, raw_hex=raw.hex(), title=replace(macro.title, raw_hex=raw[370:380].hex()),
                   lines=tuple(replace(t, raw_hex=raw[4+i*61:65+i*61].hex()) for i,t in enumerate(macro.lines)))
