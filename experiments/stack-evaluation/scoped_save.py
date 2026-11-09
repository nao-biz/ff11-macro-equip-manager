"""Opt-in save-state optimization; production entry points never import this.

Keep disk dependency checks and revalidation unchanged. Narrow only detached
state exports and copy-on-write publication of saved records/source hashes.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy, copy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from ff11reader.edit_application import Editor
from ff11reader.editing import macro_key
from ff11reader.domain import Text
from ff11reader.codecs import equipsets
from ff11reader.saving import digest


def scoped_snapshot(state, folder):
    character = next(c for c in state._template.characters if c.folder_id == folder)
    # Detach the selected character and shared metadata; never expose owned values.
    return deepcopy(replace(state._template, characters=[state._character(character)]))


def prepare_combined_save(self, folder):
    if self.blocked: raise ValueError(self.blocked)
    from ff11reader.combined_saving import prepare_combined_save as prepare
    return prepare(scoped_snapshot(self._session._saved, folder),
                   scoped_snapshot(self._session._working, folder), folder,
                   self._session.movement_origins(folder))


def prepare_writeback(self):
    saved, working = self._session._saved, self._session._working
    changed = {key[0] for key in working._semantic
               if working._semantic[key] != saved._semantic[key]}
    return tuple(self.prepare_combined_save(c.folder_id)
                 for c in working._template.characters if c.folder_id in changed)


def save_combined(self, preview, backup_root):
    from ff11reader.combined_saving import execute_combined_save
    from ff11reader.saving import require_game_closed
    if preview != self.prepare_combined_save(preview.character):
        raise ValueError('編集内容が変わりました。保存プレビューを開き直してください。')
    require_game_closed()
    session = self._session.fork()
    saved, working = session._saved, session._working
    folder = preview.character
    replacements = {}
    # Publish all semantic changes for this fully saved character, retaining other characters.
    for kind in ('macros', 'equipsets'):
        for address in working._orders[folder, kind]:
            identity = folder, kind, address
            if working._semantic[identity] != saved._semantic[identity]:
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
    hashes = {Path(f.target).resolve(): digest(f.replacement) for f in preview.files}
    sources = [dict(source, sha256=hashes[path]) if (path := Path(source['path']).resolve()) in hashes
               else source for source in state._template.sources]
    state._template = replace(state._template, sources=sources)
    session._saved = state
    if self.journal.path.exists(): raise ValueError('前回のゲーム保存の復旧確認が必要です。')
    record = self.journal.begin(preview)
    try:
        from ff11reader.elevation import execute_with_permission
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


@contextmanager
def installed():
    with ExitStack() as stack:
        for name, method in (('prepare_combined_save', prepare_combined_save),
                             ('prepare_writeback', prepare_writeback),
                             ('save_combined', save_combined), ('_save_checkpoint', save_checkpoint)):
            stack.enter_context(patch.object(Editor, name, method))
        yield
