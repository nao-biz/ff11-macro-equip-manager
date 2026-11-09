"""Immutable character/file selection, independent of the requesting use case."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CharacterReadRequest:
    folders: tuple[str, ...] | None = None
    filenames: frozenset[str] | None = None

    def __post_init__(self):
        if self.folders is not None:
            folders = tuple(self.folders)
            if any(not isinstance(f, str) or not re.fullmatch('[0-9a-fA-F]+', f) for f in folders):
                raise ValueError('キャラの読込範囲が不正です。')
            object.__setattr__(self, 'folders', folders)
        if self.filenames is not None:
            names = frozenset(self.filenames)
            if any(not isinstance(n, str) or not n or n in ('.', '..') or any(c in n for c in '/\\:') for n in names):
                raise ValueError('ファイルの読込範囲が不正です。')
            object.__setattr__(self, 'filenames', frozenset(n.lower() for n in names))
