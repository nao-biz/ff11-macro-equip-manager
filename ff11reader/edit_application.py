"""Edit use cases: coordinate pure transactions and application-owned storage."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from .editing import EditSession, plan_macro_fixes, plan_equipment_edit, edit_macro, macro_key
from .save_journal import SaveJournal
from .tracing import span, traced


class Editor:
    def __init__(self, snapshot, path=None, *, root=None):
        self.root = Path(root).resolve() if root is not None else None
        self.state_path = Path(path or Path(__file__).resolve().parent.parent / 'work' / 'drafts' / (snapshot.installation_key + '.json'))
        self.journal = SaveJournal(self.state_path.with_suffix('.pending.json'), snapshot.installation_key)
        self.blocked = None
        self._transfer = None
        try:
            self.journal.recover(snapshot, self.state_path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as exc:
            self.blocked = str(exc)
        self._session = EditSession(snapshot)

    @traced('editor.reload')
    def reload(self):
        from .application import load_snapshot
        if self.root is None:raise ValueError('読込元のインストール先が設定されていません。')
        if self.journal.path.exists():
            raise ValueError('ゲーム保存の復旧記録があります。アプリを開き直して復旧してください。')
        fresh = load_snapshot(self.root)
        if fresh.installation_key != self._session.saved.installation_key:
            raise ValueError('読込元のインストール先が一致しません。')
        next_session = EditSession(fresh)
        self._session = next_session
        self.blocked = None
        self.clear_transfer()

    @property
    def transfer(self):return deepcopy(self._transfer)

    @property
    def session(self):
        """Detached inspection copy; mutations never publish into the editor."""
        return deepcopy(self._session)

    @traced('editor.snapshot')
    def snapshot(self, previous=None):
        return self._session.view(previous)

    @traced('editor.edit_status')
    def edit_status(self):
        return self._session.cursor,self._session.history_length(),self._session.dirty

    def prepare_macro_edit(self,character,address,title,lines):
        if self.blocked:raise ValueError(self.blocked)
        from .domain import Character
        current=Character(character)
        macro=self._session.read(character,'macros',address)
        return deepcopy(edit_macro(current,macro,title,lines))

    def capture_transfer(self,folder,kind,selection,cut=False):
        if self.blocked:raise ValueError(self.blocked)
        from .transfer_editing import capture
        self._transfer=capture(self._session.character(folder),kind,selection,cut)

    def clear_transfer(self):self._transfer=None

    def prepare_paste(self,folder,anchor,*,overwrite=False):
        if self.blocked:raise ValueError(self.blocked)
        if self._transfer is None:raise ValueError('先にコピーまたは切り取りをしてください。')
        from .transfer_editing import plan_paste
        return deepcopy(plan_paste(self._session.character(folder),self._transfer,anchor,overwrite=overwrite))

    def paste(self,folder,anchor,preview,*,overwrite=False):
        if preview!=self.prepare_paste(folder,anchor,overwrite=overwrite):raise ValueError('貼り付け内容が変わりました。変更案を開き直してください。')
        self.apply(preview)
        if self._transfer.cut:self.clear_transfer()

    def prepare_delete(self,folder,kind,selection):
        if self.blocked:raise ValueError(self.blocked)
        from .transfer_editing import plan_delete
        return plan_delete(self._session.character(folder),kind,selection)

    def prepare_equipment_move(self,folder,source,target):
        if self.blocked:raise ValueError(self.blocked)
        from .equipment_moves import plan_move
        return plan_move(self._session.character(folder),source,target)

    def has_pending_move(self,folder):return bool(self._session.movement_origins(folder)) or self._session.has_pending_atomic(folder)

    def prepare_combined_save(self,folder):
        from .save_state import prepare_combined_save
        return prepare_combined_save(self,folder)

    def prepare_writeback(self):
        from .save_state import prepare_writeback
        return prepare_writeback(self)

    def writeback(self, plans, backup_root):
        if plans != self.prepare_writeback():
            raise ValueError('編集内容が変わりました。書き戻しの確認を開き直してください。')
        backups = []
        for plan in plans:
            backups.append(self.save_combined(plan, backup_root))
        return tuple(backups)

    def save_combined(self,preview,backup_root):
        from .save_state import save_combined
        return save_combined(self,preview,backup_root)

    def equipment_candidates(self,character,slot,query=''):
        from .equipment_editing import candidates
        return candidates(self._session.character(character),self._session.item_catalog(),slot,query)

    def prepare_equipment_slot_edit(self,character,number,slot,action,selection=None):
        if self.blocked:raise ValueError(self.blocked)
        from .equipment_editing import edit_slot
        current=self._session.read(character,'equipsets',(number,))
        return edit_slot(self._session.character(character),self._session.item_catalog(),current,slot,action,selection)

    def prepare_equipment_name_edit(self,character,number,title):
        if self.blocked:raise ValueError(self.blocked)
        from .domain import Character
        from .editing import edit_equipment_name
        current=self._session.read(character,'equipsets',(number,))
        return deepcopy(edit_equipment_name(Character(character),current,title))

    def _execute(self, operation):
        if self.blocked:
            raise ValueError(self.blocked)
        if self.journal.path.exists():raise ValueError('ゲームへの保存または復旧が終わるまで、編集を再開できません。')
        with span('editor.fork_session'):
            next_session = self._session.fork()
        with span('editor.apply_operation'):
            operation(next_session)
        self._session = next_session

    @traced('editor.apply')
    def apply(self, edit):
        self._execute(lambda s: s.apply(edit))

    @traced('editor.undo')
    def undo(self):
        self._execute(lambda s: s.undo())

    @traced('editor.redo')
    def redo(self):
        self._execute(lambda s: s.redo())

    def macro_fixes(self, character, preview, address=None):
        current = self._session.character(character)
        if preview != plan_macro_fixes(current, self._session.item_catalog(), address):
            raise ValueError('Fix案が変わりました。プレビューを開き直してください。')
        self.apply(preview)

    def equipment_fixes(self, character, plan):
        current = self._session.character(character)
        self.apply(plan_equipment_edit(current,plan))

    @traced('editor.start_fresh')
    def start_fresh(self):
        if self.journal.path.exists():
            raise ValueError('ゲーム保存の復旧記録があります。バックアップと復旧記録を確認してください。')
        next_session = EditSession(self._session.saved)
        self._session = next_session
        self.clear_transfer()
        self.blocked = None

    @traced('editor.prepare_macro_save')
    def prepare_macro_save(self,folder,scope='storage-fix'):
        if self.has_pending_move(folder):raise ValueError('依存する変更を一括保存してください。')
        if self.blocked:raise ValueError(self.blocked)
        from .macro_saving import prepare_macro_save
        return prepare_macro_save(self._session.saved,self._session.working,folder,scope)

    @traced('editor.save_macros')
    def save_macros(self,preview,backup_root):
        from .macro_saving import execute_macro_save
        from .saving import require_game_closed
        if preview!=self.prepare_macro_save(preview.character,preview.scope):raise ValueError('編集内容が変わりました。保存プレビューを開き直してください。')
        require_game_closed()
        next_session=self._session.fork()
        saved=next_session.saved
        character=next(c for c in saved.characters if c.folder_id==preview.character)
        changes={(change.address,change.line):change for f in preview.files for change in f.changes}
        from .editing import macro_key
        from .domain import Text
        def changed(m,n,old):
            change=changes.get((macro_key(m),n))
            return Text(change.after,change.replacement.hex(),'cp932',change.tokens) if change else old
        character.macros=[self._sync_macro_raw(preview.files,replace(m,title=changed(m,0,m.title),lines=tuple(changed(m,n,line) for n,line in enumerate(m.lines,1)))) for m in character.macros]
        next_session.saved=saved
        return self._save_checkpoint(preview,backup_root,next_session,execute_macro_save)

    @traced('editor.prepare_equipment_save')
    def prepare_equipment_save(self,folder,scope='reference-fix'):
        if self.has_pending_move(folder):raise ValueError('依存する変更を一括保存してください。')
        if self.blocked:raise ValueError(self.blocked)
        from .equipment_saving import prepare_equipment_save
        return prepare_equipment_save(self._session.saved,self._session.working,folder,scope)

    @traced('editor.save_equipment')
    def save_equipment(self,preview,backup_root):
        from .equipment_saving import execute_equipment_save
        from .saving import require_game_closed
        from .codecs import equipsets, BAGS
        from .references import assess_equipment
        if preview!=self.prepare_equipment_save(preview.character,preview.scope):raise ValueError('編集内容が変わりました。保存プレビューを開き直してください。')
        require_game_closed()
        next_session=self._session.fork()
        saved=next_session.saved
        character=next(c for c in saved.characters if c.folder_id==preview.character)
        decoded={e.number:e for f in preview.files for e in equipsets(f.replacement,f.page)}
        character.equipsets=[decoded.get(e.number,e) for e in character.equipsets]
        sources={BAGS[Path(s['path']).name]:s for s in saved.sources if Path(s['path']).parent.name==preview.character and Path(s['path']).name in BAGS}
        character.equipsets=assess_equipment(character,sources)
        next_session.saved=saved
        return self._save_checkpoint(preview,backup_root,next_session,execute_equipment_save)

    @staticmethod
    def _macro_raw(files,macro):
        page=(macro.book-1)*10+macro.palette-1
        file=next((f for f in files if f.page==page),None)
        if file is None:return macro.raw_hex
        offset=24+((0 if macro.bank=='ctrl' else 10)+macro.key-1)*380
        return file.replacement[offset:offset+380].hex()

    @classmethod
    def _sync_macro_raw(cls,files,macro):
        raw_hex=cls._macro_raw(files,macro)
        if not raw_hex:return macro
        raw=bytes.fromhex(raw_hex)
        return replace(macro,raw_hex=raw_hex,title=replace(macro.title,raw_hex=raw[370:380].hex()),
                       lines=tuple(replace(t,raw_hex=raw[4+i*61:65+i*61].hex()) for i,t in enumerate(macro.lines)))

    def _save_checkpoint(self,preview,backup_root,next_session,execute_save):
        from .save_state import save_checkpoint
        return save_checkpoint(self,preview,backup_root,next_session,execute_save)
