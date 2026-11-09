"""Immutable application-lifetime master values, independent of I/O and editors."""
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from types import MappingProxyType


class FrozenMapping(Mapping):
    __slots__ = ('_values',)

    def __init__(self, values):
        object.__setattr__(self, '_values', MappingProxyType({freeze(k): freeze(v) for k, v in values.items()}))

    def __setattr__(self, name, value):
        raise TypeError('マスターデータは読み取り専用です。')

    def __delattr__(self, name):
        raise TypeError('マスターデータは読み取り専用です。')

    def __getitem__(self, key): return self._values[key]
    def __iter__(self): return iter(self._values)
    def __len__(self): return len(self._values)
    def __deepcopy__(self, memo): return self


def freeze(value):
    if value is None or isinstance(value, (str, bytes, int, float, bool)): return value
    if isinstance(value, FrozenMapping): return value
    if isinstance(value, Mapping): return FrozenMapping(value)
    if isinstance(value, (list, tuple)): return tuple(freeze(v) for v in value)
    if isinstance(value, (set, frozenset)): return frozenset(freeze(v) for v in value)
    if is_dataclass(value):
        if not value.__dataclass_params__.frozen:
            raise TypeError('マスターのレコードには不変値が必要です。')
        return replace(value, **{f.name: freeze(getattr(value, f.name)) for f in fields(value)})
    raise TypeError(f'Unsupported master value: {type(value).__name__}')


@dataclass(frozen=True)
class MasterData:
    root: str
    items: Mapping
    phrases: Mapping
    phrase_readings: Mapping
    augment_names: Mapping
    rank_augments: object
    sources: tuple
    diagnostics: tuple
    icon_ids: frozenset

    def __post_init__(self):
        for field in fields(self):
            object.__setattr__(self, field.name, freeze(getattr(self, field.name)))

    def __deepcopy__(self, memo): return self
