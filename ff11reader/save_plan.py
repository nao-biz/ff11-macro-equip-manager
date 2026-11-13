"""Save preview contracts, independent of files and UI."""
from dataclasses import dataclass
from .edit_values import character_value, validate_structure


@dataclass(frozen=True)
class BookNameChange:
    number: int
    before: str
    after: str
    replacement: bytes


@dataclass(frozen=True)
class BookFile:
    target: str
    page: int
    original: bytes
    replacement: bytes
    changes: tuple


@dataclass(frozen=True)
class BookSavePlan:
    character: str
    files: tuple
    dependencies: tuple

@dataclass(frozen=True)
class DeferredChange:
    target: str
    reason: str

def deferred_text(changes):
    return '\n'.join(f'{c.target}: {c.reason}' for c in changes)

def require_same_targets(before,after):
    left=character_value(before);right=character_value(after)
    if any(a.keys()!=b.keys() for a,b in zip(left,right)):
        raise ValueError('対象の追加・削除・移動の保存は未対応です。')
    for c in (before,after):
        for m in c.macros:validate_structure(m,'macros')
        for e in c.equipsets:validate_structure(e,'equipsets')


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


@dataclass(frozen=True)
class EquipmentNameChange:
    equipset: int
    before: str
    after: str


@dataclass(frozen=True)
class EquipmentSlotChange:
    equipset: int
    slot: str
    before: tuple
    after: tuple


@dataclass(frozen=True)
class EquipmentFile:
    target: str
    page: int
    original: bytes
    replacement: bytes
    changes: tuple

@dataclass(frozen=True)
class EquipmentSavePlan:
    character: str
    files: tuple
    dependencies: tuple
    deferred_changes: tuple = ()
    scope: str = 'reference-fix'
    catalogs: tuple = ()
    transfers: tuple = ()

    @property
    def deferred(self):return len(self.deferred_changes)


@dataclass(frozen=True)
class CombinedSavePlan:
    character: str
    equipment: EquipmentSavePlan | None
    macro: MacroSavePlan | None
    dependencies: tuple
    members: tuple
    books: BookSavePlan | None = None

    @property
    def files(self):return (self.equipment.files if self.equipment else ())+(self.macro.files if self.macro else ())+(self.books.files if self.books else ())
    @property
    def deferred(self):return (self.equipment.deferred if self.equipment else 0)+(self.macro.deferred if self.macro else 0)
