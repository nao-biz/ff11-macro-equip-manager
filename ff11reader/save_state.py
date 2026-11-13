"""Internal save-state coordination using detached character views and persistent records.

Disk plans, dependency validation, backups and rollback remain in the existing
save modules. State ownership stays behind EditSession save operations;
owned mutable records are never returned to callers.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from .editing import macro_key
from .domain import Text
from .codecs import equipsets
from .loaded_files import storage_member


@dataclass(frozen=True)
class SaveRequest:
    """Internal captured state and compacted net changes; history stays in the session."""
    session: object
    identities: frozenset

    @classmethod
    def capture(cls, session):
        captured = session.fork()
        return cls(captured, captured.changes_since_save())

    def folders(self):
        changed = {key[0] for key in self.identities}
        return tuple(folder for folder in self.session.character_folders()
                     if folder in changed or self.session.movement_origins(folder))

    def members(self, folder):
        result = {storage_member(key) for key in self.identities if key[0] == folder}
        result.update((folder, 'equipsets', (target - 1) // 20)
                      for target, source in self.session.movement_origins(folder))
        return frozenset(result)

    def validate_scope(self, plan):
        actual = {(plan.character, kind, file.page)
                  for kind, part in (('macros', plan.macro), ('equipsets', plan.equipment), ('books', plan.books))
                  if part for file in part.files}
        if actual != self.members(plan.character):
            raise ValueError('保存計画のファイル範囲が編集差分と一致しません。')

    def prepare(self, folder):
        from .combined_saving import prepare_combined_save as prepare
        identities = {key for key in self.identities if key[0] == folder}
        transfers = self.session.movement_origins(folder)
        for target, source in transfers:
            identities.update(((folder, 'equipsets', (target,)), (folder, 'equipsets', (source,))))
        before, after, sources = self.session.save_inputs(folder, identities)
        plan = prepare(before, after, folder, transfers, source_index=sources)
        self.validate_scope(plan)
        return plan


def prepare_combined_save(self, folder):
    if self.blocked: raise ValueError(self.blocked)
    return SaveRequest.capture(self.capture_save_session()).prepare(folder)


def prepare_writeback(self):
    if self.blocked: raise ValueError(self.blocked)
    request = SaveRequest.capture(self.capture_save_session())
    return tuple(request.prepare(folder) for folder in request.folders())


def save_combined(self, preview, backup_root):
    from .combined_saving import execute_combined_save
    from .macro_saving import sync_macro_raw
    from .file_io import require_game_closed
    if self.blocked: raise ValueError(self.blocked)
    request = SaveRequest.capture(self.capture_save_session())
    if preview != request.prepare(preview.character):
        raise ValueError('編集内容が変わりました。保存プレビューを開き直してください。')
    require_game_closed()
    session = request.session
    folder = preview.character
    replacements = {}
    # Publish all semantic changes for this fully saved character, retaining other characters.
    for identity in request.identities:
        if identity[0] == folder:
            replacements[identity] = session.read(*identity)
    for file in (preview.equipment.files if preview.equipment else ()):
        for equipment in equipsets(file.replacement, file.page):
            replacements[folder, 'equipsets', (equipment.number,)] = equipment
    if preview.macro:
        changes = {(c.address, c.line): c for f in preview.macro.files for c in f.changes}
        pages = {f.page for f in preview.macro.files}
        def changed(macro, line, old):
            change = changes.get((macro_key(macro), line))
            return Text(change.after, change.replacement.hex(), 'cp932', change.tokens) if change else old
        for address in session.record_addresses(folder, 'macros'):
            book, palette, _, _ = address
            if (book-1)*10+palette-1 not in pages: continue
            identity = folder, 'macros', address
            macro = session.read(*identity)
            replacements[identity] = sync_macro_raw(preview.macro.files,
                replace(macro, title=changed(macro,0,macro.title),
                        lines=tuple(changed(macro,n,line) for n,line in enumerate(macro.lines,1))))
    session.record_saved(folder, replacements)
    return save_checkpoint(self, preview, backup_root, session, execute_combined_save)


def save_checkpoint(self, preview, backup_root, session, execute_save):
    from .snapshot_loading import verify_master_data
    from functools import partial
    verify_master_data(self.master_data)
    if self.master_data is not None:
        execute_save = partial(execute_save, masters=self.master_data)
    session.record_saved_files(preview.files)
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
        self.publish_saved_session(session)
        self.journal.finish()
    except Exception as exc:
        self.blocked = f'ゲームへの保存は完了しましたが、復旧記録の削除に失敗しました。アプリを再起動して復旧を確認してください。バックアップ: {backup}'
        raise RuntimeError(self.blocked) from exc
    return backup
