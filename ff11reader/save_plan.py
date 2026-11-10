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
