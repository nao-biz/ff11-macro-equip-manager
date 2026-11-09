"""Internal save-state coordination using detached character views and persistent records.

Disk plans, dependency validation, backups and rollback remain in the existing
save modules. This module owns the narrow bridge to EditSession's private state;
owned mutable records are never returned to callers.
"""
from copy import deepcopy, copy
from dataclasses import dataclass, replace
from pathlib import Path
from .editing import macro_key
from .domain import Text, Snapshot
from .codecs import equipsets
from .saving import digest


from .loaded_files import storage_member


@dataclass(frozen=True)
class SaveRequest:
    """Internal captured state and compacted net changes; history stays in the session."""
    session: object
    identities: frozenset

    @classmethod
    def capture(cls, session):
        captured = session.fork()
        saved, working = captured._saved, captured._working
        if len(saved._semantic) != len(working._semantic) or any(key not in saved._semantic for key in working._semantic):
            raise ValueError('保存モデルの構成が変わりました。再読み込みしてください。')
        return cls(captured, frozenset(key for key in working._semantic
            if working._semantic[key] != saved._semantic[key]))

    def folders(self):
        changed = {key[0] for key in self.identities}
        return tuple(c.folder_id for c in self.session._working._template.characters
                     if c.folder_id in changed or self.session.movement_origins(c.folder_id))

    def members(self, folder):
        result = {storage_member(key) for key in self.identities if key[0] == folder}
        result.update((folder, 'equipsets', (target - 1) // 20)
                      for target, source in self.session.movement_origins(folder))
        return frozenset(result)

    def validate_scope(self, plan):
        actual = {(plan.character, kind, file.page)
                  for kind, part in (('macros', plan.macro), ('equipsets', plan.equipment))
                  if part for file in part.files}
        if actual != self.members(plan.character):
            raise ValueError('保存計画のファイル範囲が編集差分と一致しません。')

    def prepare(self, folder):
        from .combined_saving import prepare_combined_save as prepare
        identities = {key for key in self.identities if key[0] == folder}
        transfers = self.session.movement_origins(folder)
        for target, source in transfers:
            identities.update(((folder, 'equipsets', (target,)), (folder, 'equipsets', (source,))))
        item_ids = {slot.item_id for state in (self.session._saved, self.session._working)
                    for identity in identities if identity[1] == 'equipsets'
                    for slot in state._entries[identity].slots if slot.item_id}
        # Both sides must carry exactly the same identities for format validation.
        plan = prepare(scoped_snapshot(self.session._saved, folder, identities, item_ids),
                       scoped_snapshot(self.session._working, folder, identities, item_ids), folder, transfers, source_index=self.session._saved._files)
        self.validate_scope(plan)
        return plan


def scoped_snapshot(state, folder, identities=None, item_ids=None):
    character = next(c for c in state._template.characters if c.folder_id == folder)
    if identities is None:
        identities = {key for key in state._entries if key[0] == folder}
    records = {kind:[state._entries[folder,kind,address]
                     for address in state._orders[folder,kind]
                     if (folder,kind,address) in identities] for kind in ('macros','equipsets')}
    character = replace(character, **records)
    template = state._template
    # Macro token resolution needs the item dictionary; equipment needs only its slot items.
    if item_ids is None:
        item_ids = {slot.item_id for e in records['equipsets'] for slot in e.slots if slot.item_id}
    items = template.items if records['macros'] else {key:template.items[key] for key in item_ids if key in template.items}
    return deepcopy(Snapshot(template.id, template.captured_at, [character], items,
                             template.sources, [], template.installation_key))


def prepare_combined_save(self, folder):
    if self.blocked: raise ValueError(self.blocked)
    return SaveRequest.capture(self._session).prepare(folder)


def prepare_writeback(self):
    if self.blocked: raise ValueError(self.blocked)
    request = SaveRequest.capture(self._session)
    return tuple(request.prepare(folder) for folder in request.folders())


def save_combined(self, preview, backup_root):
    from .combined_saving import execute_combined_save
    from .saving import require_game_closed
    if self.blocked: raise ValueError(self.blocked)
    request = SaveRequest.capture(self._session)
    if preview != request.prepare(preview.character):
        raise ValueError('編集内容が変わりました。保存プレビューを開き直してください。')
    require_game_closed()
    session = request.session
    saved, working = session._saved, session._working
    folder = preview.character
    replacements = {}
    # Publish all semantic changes for this fully saved character, retaining other characters.
    for identity in request.identities:
        if identity[0] == folder:
            replacements[identity] = working._entries[identity]
    for file in (preview.equipment.files if preview.equipment else ()):
        for equipment in equipsets(file.replacement, file.page):
            replacements[folder, 'equipsets', (equipment.number,)] = equipment
    if preview.macro:
        changes = {(c.address, c.line): c for f in preview.macro.files for c in f.changes}
        pages = {f.page for f in preview.macro.files}
        def changed(macro, line, old):
            change = changes.get((macro_key(macro), line))
            return Text(change.after, change.replacement.hex(), 'cp932', change.tokens) if change else old
        for address in working._orders[folder, 'macros']:
            book, palette, _, _ = address
            if (book-1)*10+palette-1 not in pages: continue
            identity = folder, 'macros', address
            macro = working._entries[identity]
            replacements[identity] = self._sync_macro_raw(preview.macro.files,
                replace(macro, title=changed(macro,0,macro.title),
                        lines=tuple(changed(macro,n,line) for n,line in enumerate(macro.lines,1))))
    session._saved = saved.updated(replacements)
    session.mark_movement_saved(folder)
    return self._save_checkpoint(preview, backup_root, session, execute_combined_save)


def save_checkpoint(self, preview, backup_root, session, execute_save):
    state = copy(session._saved)
    state._files = state._files.updated(preview.files)
    state._template = replace(state._template, sources=state._files.sources())
    session._saved = state
    if self.journal.path.exists(): raise ValueError('前回のゲーム保存の復旧確認が必要です。')
    record = self.journal.begin(preview)
    try:
        from .elevation import execute_with_permission
        with record:
            backup = execute_with_permission(preview, backup_root, execute_save)
    except Exception as exc:
        try: unchanged = all(Path(f.target).read_bytes() == f.original for f in preview.files)
        except OSError: unchanged = False
        if unchanged: self.journal.finish()
        else:
            self.blocked = 'ゲームへの保存が途中で止まっています。バックアップと復旧用のpending記録を残しています。復旧確認が必要です。'
            raise RuntimeError(self.blocked+' '+str(exc)) from exc
        raise
    try:
        self._session = session
        self.journal.finish()
    except Exception as exc:
        self.blocked = f'ゲームへの保存は完了しましたが、復旧記録の削除に失敗しました。アプリを再起動して復旧を確認してください。バックアップ: {backup}'
        raise RuntimeError(self.blocked) from exc
    return backup
