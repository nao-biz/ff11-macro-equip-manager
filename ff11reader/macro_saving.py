"""Guarded macro text and storage-number persistence with token preservation."""
from .backup_restore import restore_backup_set
from dataclasses import replace
from pathlib import Path
import re
import os
from uuid import uuid4
from .codecs import macros, BAGS
from .macro_inventory import assess_macro_inventory
from .file_io import digest, locked_read, atomic_replace, require_game_closed
from .loaded_files import LoadedFiles
from .file_transaction import execute_batch, write_json
from .save_plan import LineChange, MacroFile, MacroSavePlan, DeferredChange, deferred_text, require_same_targets
from .macro_save_proposal import replay_macro_proposal
from .macro_save_encoding import patch_line, patch_file
from .macro_save_changes import needs_dictionary, collect_changes


def prepare_macro_save(saved,working,folder,scope='storage-fix', *, source_index=None):
    if scope not in ('storage-fix','all'):raise ValueError('保存範囲が不正です。')
    original=next(c for c in saved.characters if c.folder_id==folder)
    edited=next(c for c in working.characters if c.folder_id==folder)
    require_same_targets(original,edited)
    sources=source_index if source_index is not None else LoadedFiles(saved.sources)
    records=sources.records()
    parent=next((p.parent for p in records if p.parent.name==folder and p.parent.parent.name.upper()=='USER'),None)
    if parent is None or not re.fullmatch('[0-9a-fA-F]+',folder):raise ValueError('キャラクターの保存先を確認してください。')
    root=parent.parent.parent
    dictionary_required=needs_dictionary(original,edited,scope)
    resolver=prepare_resolver(saved,root,records,dictionary_required)
    refs={(r.address,r.line):r for r in assess_macro_inventory(original,saved.items)} if scope=='storage-fix' else {}
    grouped,deferred,record_bases=collect_changes(original,edited,scope,resolver,refs)
    if not grouped:raise ValueError('保存できるマクロの変更がありません。'+('\n'+deferred_text(deferred) if deferred else ''))
    files=build_files(parent,records,grouped,record_bases)
    required={Path(f.target) for f in files}
    if scope=='storage-fix':required.update(parent/name for name in BAGS)
    # Item/phrase dictionaries are part of name-to-ID verification.
    if dictionary_required:required.update(sources.shared_resources(root))
    dependencies=verify_dependencies(required,records,root,saved.master_data is not None)
    return MacroSavePlan(folder,tuple(files),tuple(dependencies),tuple(deferred),scope)



def prepare_resolver(saved, root, records, required):
    from .adapters import LocalReader
    from .dictionaries import resolve_token
    reader=LocalReader(root)
    phrases=(saved.master_data.phrases if saved.master_data is not None else reader.load_phrases()) if required else {}
    resolver=lambda token:resolve_token(token,phrases,saved.items)
    for source in reader.sources:
        p=Path(source['path']).resolve()
        if p not in records or source['sha256']!=records[p]['sha256']:raise ValueError('定型文データが変わりました。再読み込みしてください。')
    return resolver


def build_files(parent, records, grouped, record_bases):
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
    return tuple(files)


def verify_dependencies(required, records, root, has_masters):
    dependencies=[]
    for p in sorted(required):
        raw=p.read_bytes()
        if p not in records or digest(raw)!=records[p]['sha256']:
            message = ('マスターデータが更新されています。アプリを再起動してください。'
                       if has_masters and not p.is_relative_to(root/'USER')
                       else '読込元が変更されています。再読み込みしてください。')
            raise ValueError(message)
        dependencies.append((str(p),digest(raw)))
    return tuple(dependencies)


def validate_macro_plan(plan, masters=None):
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
        args=(root, plan.character, (f.page for f in plan.files))
        fresh=load_macro_validation_snapshot(*args, masters) if masters is not None else load_macro_validation_snapshot(*args)
        changes={(change.address,change.line):change for f in plan.files for change in f.changes}
        bases={address:base.hex() for f in plan.files for address,original,base in f.records}
        before,proposed=replay_macro_proposal(fresh,plan.character,changes,bases)
        verified=prepare_macro_save(before,proposed,plan.character,plan.scope)
        if verified.files!=plan.files or verified.dependencies!=plan.dependencies:raise ValueError('保存計画が現在のマクロ変更と一致しません。')
    return root,validate


def execute_macro_save(plan,backup_root, *, masters=None):
    require_game_closed()
    root,validate=validate_macro_plan(plan, masters)
    return execute_batch(plan,backup_root,root,validate,macros,'macro-edit' if plan.scope=='all' else 'macro-storage-fix','.ff11-macro-',
                         lambda c:{'address':c.address,'line':c.line,'before':c.before,'after':c.after,
                                   'before_token_ids':[t.identity for t in c.original_tokens or ()],
                                   'after_token_ids':[t.identity for t in c.tokens or ()]},
                         require_game_closed,write_json,atomic_replace)


def backup_target_name(page):
    if not isinstance(page, int) or not 0 <= page < 400:
        raise ValueError('バックアップのパレット番号が不正です。')
    return 'mcr'+(str(page) if page else '')+'.dat'


def restore_macro_backup(folder, apply=False):
    return restore_backup_set(folder, apply, kinds=('macro-storage-fix', 'macro-edit'),
                              label='マクロ', target_name=backup_target_name, decode=macros)


def sync_macro_raw(files, macro):
    """Normalize model provenance from the verified file output."""
    page = (macro.book-1)*10+macro.palette-1
    file = next((f for f in files if f.page == page), None)
    offset = 24+((0 if macro.bank == 'ctrl' else 10)+macro.key-1)*380
    raw = file.replacement[offset:offset+380] if file else bytes.fromhex(macro.raw_hex)
    if not raw: return macro
    return replace(macro, raw_hex=raw.hex(), title=replace(macro.title, raw_hex=raw[370:380].hex()),
                   lines=tuple(replace(t, raw_hex=raw[4+i*61:65+i*61].hex()) for i,t in enumerate(macro.lines)))
