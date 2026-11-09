"""In-memory edit transactions. No GUI, filesystem or binary encoding."""
from copy import deepcopy
from immutables import Map
from dataclasses import dataclass, replace
from .domain import Text
from .text_editing import remap_text
from .edit_values import validate_text
from .edit_state import SnapshotState
from .edit_values import value, character_value, validate_transition, key as edit_key
from .macro_inventory import assess_macro_inventory
from .references import assess_equipment


@dataclass(frozen=True)
class Change:
    character: str
    kind: str
    key: tuple
    before: object
    after: object


@dataclass(frozen=True)
class Edit:
    label: str
    changes: tuple[Change, ...]
    moves: tuple = ()
    atomic: bool = False


def macro_key(macro):
    return macro.book, macro.palette, macro.bank, macro.key


def contents(character):
    """Semantic edit contents, independent of binary encoding and derived states."""
    return character_value(character)


def edit_macro(character, macro, title, lines):
    if len(lines) != 6 or any(not isinstance(s,(str,Text)) for s in [title,*lines]):
        raise ValueError('マクロは名前と6行で入力してください。')
    def text(before, value, *, line=False):
        result=value if isinstance(value,Text) else remap_text(before,value)
        validate_text(result)
        return replace(result,raw_hex=result.raw_hex if line and isinstance(value,Text) and result.raw_hex else before.raw_hex)
    updated = replace(macro, title=text(macro.title, title), lines=tuple(text(a, b, line=True) for a, b in zip(macro.lines, lines)))
    return Edit('マクロを編集', (Change(character.folder_id, 'macros', macro_key(macro), macro, updated),))


def edit_equipment_name(character, equipment, title):
    if not isinstance(title,str):raise ValueError('名前は文字列で入力してください。')
    updated=equipment if title==equipment.title.display else replace(equipment,title=Text(title,equipment.title.raw_hex,'draft'))
    validate_text(updated.title)
    return Edit('装備セット名を編集',(Change(character.folder_id,'equipsets',(equipment.number,),equipment,updated),))


def plan_macro_fixes(character, items, address=None):
    refs = assess_macro_inventory(character, items)
    changes = []
    for macro in character.macros:
        key = macro_key(macro)
        if address is not None and key != address:
            continue
        fixes = {r.line: r.replacement for r in refs if r.address == key and r.replacement is not None}
        if fixes:
            lines = tuple(remap_text(line,fixes[n]) if n in fixes else line for n, line in enumerate(macro.lines, 1))
            changes.append(Change(character.folder_id, 'macros', key, macro, replace(macro, lines=lines)))
    return Edit('マクロの収納番号Fix', tuple(changes))


class EditSession:
    def __init__(self, snapshot):
        self._baseline = SnapshotState(snapshot)
        self._working = self._baseline
        self._saved = self._baseline
        self._history = ()
        self._origins = Map()
        self._saved_origins = Map()
        self.cursor = 0

    def fork(self):
        result = object.__new__(EditSession)
        result._baseline, result._working, result._saved = self._baseline, self._working, self._saved
        result._history, result.cursor = self._history, self.cursor
        result._origins,result._saved_origins=self._origins,self._saved_origins
        return result

    def __deepcopy__(self, memo): return self.fork()

    @property
    def baseline(self): return self._baseline.export()
    @baseline.setter
    def baseline(self, snapshot): self._baseline = SnapshotState(snapshot)
    @property
    def working(self): return self._working.export()
    @working.setter
    def working(self, snapshot): self._working = SnapshotState(snapshot)
    @property
    def saved(self): return self._saved.export()
    @saved.setter
    def saved(self, snapshot): self._saved = SnapshotState(snapshot)
    @property
    def history(self): return deepcopy(list(self._history))

    def baseline_token(self): return self._baseline._token
    def baseline_records(self): return self._baseline.edit_records()
    def saved_header(self): return self._saved.source_header()

    def view(self, previous=None): return self._working.export(previous)
    def character(self, folder): return self._working.read_character(folder)
    def item_catalog(self): return self._working.items()
    def read(self, folder, kind, address): return self._working.read(folder,kind,address)
    def history_length(self): return len(self._history)

    def has_pending_atomic(self,folder):
        if not any(e.atomic and any(c.character==folder for c in e.changes) for e in self._history):return False
        return character_value(self._working.read_character(folder))!=character_value(self._saved.read_character(folder))

    def saved_origins(self):return tuple(sorted((folder,number,origin) for (folder,number),origin in self._saved_origins.items()))

    def restore_saved_origins(self,records):
        from .edit_values import integer
        result={}
        for folder,number,origin in records:
            if not integer(number,1,200) or not integer(origin,1,200) or not self._saved.has((folder,'equipsets',(number,))) or not self._saved.has((folder,'equipsets',(origin,))) or (folder,number) in result:raise ValueError('移動履歴の原本対応が不正です。')
            result[folder,number]=origin
        for folder in {f for f,n in result}:
            if {n for f,n in result if f==folder}!={o for (f,n),o in result.items() if f==folder}:raise ValueError('移動履歴の原本対応が重複しています。')
        self._saved_origins=Map(result)

    def movement_origins(self,folder):
        numbers={n for f,n in set(self._origins)|set(self._saved_origins) if f==folder}
        inverse={self._saved_origins.get((folder,n),n):n for n in numbers}
        return tuple(sorted((n,inverse[self._origins.get((folder,n),n)]) for n in numbers if inverse[self._origins.get((folder,n),n)]!=n))

    def mark_movement_saved(self,folder):
        self._saved_origins=Map({k:v for k,v in self._saved_origins.items() if k[0]!=folder})
        for key,origin in self._origins.items():
            if key[0]==folder:self._saved_origins=self._saved_origins.set(key,origin)

    @property
    def dirty(self): return not self._saved.same_values(self._working) or self._origins != self._saved_origins

    def _apply(self, edit, reverse=False):
        if not isinstance(edit,Edit) or not isinstance(edit.changes,tuple):raise ValueError('編集案の形式が不正です。')
        seen, replacements = set(), {}
        for change in edit.changes:
            if not isinstance(change,Change) or not isinstance(change.key,tuple) or not isinstance(change.character,str):raise ValueError('変更の形式が不正です。')
            if not edit.moves:validate_transition(change.before,change.after,change.kind)
            else:
                from .edit_values import validate_structure
                validate_structure(change.before,change.kind);validate_structure(change.after,change.kind)
            identity = (change.character, change.kind, change.key)
            if identity in seen or change.kind not in ('macros', 'equipsets'):
                raise ValueError('編集操作の対象が不正です。')
            seen.add(identity)
            before, after = (change.after, change.before) if reverse else (change.before, change.after)
            if not self._working.has(identity) or value(self._working.read(*identity)) != value(before) or edit_key(after) != change.key:
                raise ValueError('作業データが変わりました。変更案を作り直してください。')
            if value(before)!=value(after):replacements[identity] = after
        if replacements:self._working = self._working.updated(replacements)
        for folder,source,target in (reversed(edit.moves) if reverse else edit.moves):
            a=self._origins.get((folder,source),source);b=self._origins.get((folder,target),target)
            self._origins=self._origins.set((folder,source),b).set((folder,target),a)
            if b==source:self._origins=self._origins.delete((folder,source))
            if a==target:self._origins=self._origins.delete((folder,target))

    def apply(self, edit):
        if not isinstance(edit,Edit) or not isinstance(edit.changes,tuple):raise ValueError('編集案の形式が不正です。')
        if type(edit.atomic) is not bool:raise ValueError('一括編集の指定が不正です。')
        if not isinstance(edit.moves,tuple):raise ValueError('移動の形式が不正です。')
        if edit.moves:
            from .equipment_moves import plan_move
            folders={m[0] for m in edit.moves}
            if len(folders)!=1:raise ValueError('同一キャラの移動を指定してください。')
            folder=next(iter(folders))
            if len(edit.moves)==1:
                _,source,target=edit.moves[0]
                expected=plan_move(self.character(folder),source,target)
            else:
                trial=self.fork()
                before=self.character(folder)
                for _,source,target in edit.moves:trial.apply(plan_move(trial.character(folder),source,target))
                after=trial.character(folder)
                expected=Edit(edit.label,tuple(Change(folder,f,edit_key(a),a,b) for f in ('equipsets','macros') for a,b in zip(getattr(before,f),getattr(after,f)) if value(a)!=value(b)))
            semantic=lambda changes:{(c.character,c.kind,c.key):(value(c.before),value(c.after)) for c in changes if value(c.before)!=value(c.after)}
            if semantic(edit.changes)!=semantic(expected.changes):raise ValueError('移動と参照更新が一致しません。')
        for c in edit.changes:
            if not isinstance(c,Change):raise ValueError('変更の形式が不正です。')
            if not edit.moves:validate_transition(c.before,c.after,c.kind)
            if not isinstance(c.key,tuple) or c.key!=edit_key(c.before) or not isinstance(c.character,str):raise ValueError('変更対象のキーが不正です。')
        if len({(c.character,c.kind,c.key) for c in edit.changes})!=len(edit.changes):raise ValueError('変更対象が重複しています。')
        # Copy the incoming history before publishing any next state.
        stored = deepcopy(replace(edit, changes=tuple(c for c in edit.changes if value(c.before) != value(c.after))))
        self._apply(edit)
        if not stored.changes:return
        self._history = self._history[:self.cursor] + (stored,)
        self.cursor += 1

    def undo(self):
        if self.cursor:
            self._apply(self._history[self.cursor - 1], True)
            self.cursor -= 1

    def redo(self):
        if self.cursor < len(self._history):
            self._apply(self._history[self.cursor])
            self.cursor += 1


def plan_equipment_edit(character,plan):
    from .fixes import apply_fixes
    sources={s.container:s.item_reference.inventory_source for e in character.equipsets for s in e.slots if s.container is not None}
    updated=apply_fixes(character,plan,sources)
    changes=tuple(Change(character.folder_id,'equipsets',(a.number,),a,b) for a,b in zip(character.equipsets,updated.equipsets) if value(a)!=value(b))
    return Edit('装備セットの参照Fix',changes)
