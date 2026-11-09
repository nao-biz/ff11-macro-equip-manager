"""Session-owned source identities and versions; no process-global path cache."""
from copy import deepcopy
from pathlib import Path
from immutables import Map
from .saving import digest
from .resource_catalog import SHARED_RESOURCES, resource_paths


def storage_member(identity):
    folder, kind, address = identity
    if kind == 'macros':
        book, palette, _, _ = address
        return folder, kind, (book - 1) * 10 + palette - 1
    if kind == 'equipsets':
        return folder, kind, (address[0] - 1) // 20
    raise ValueError('保存モデルの種類が不正です。')


class LoadedFiles:
    """Owned source records and resolved paths, shared until successful save/reload."""
    def __init__(self, sources):
        records = {}
        order = []
        for source in sources:
            path = Path(source['path']).resolve()
            records[path] = deepcopy(source)
            order.append(path)
        self._records = Map(records)
        self._order = tuple(order)
        parents = {}
        for path in records:
            parents.setdefault(path.parent, []).append(path)
        self._parents = Map({p:tuple(paths) for p, paths in parents.items()})

    def __deepcopy__(self, memo): return self

    def records(self):
        return {p:deepcopy(record) for p,record in self._records.items()}

    def sources(self):
        return [deepcopy(self._records[p]) for p in self._order]

    def children(self, parent):
        parent = Path(parent)
        if parent.resolve() != parent:
            raise ValueError('保存先フォルダーの解決先が変わりました。再読み込みしてください。')
        return self._parents.get(parent, ())

    def verify(self, path):
        path = Path(path)
        expected = self._records[path]['sha256']
        if digest(path.read_bytes()) != expected:
            raise ValueError('参照元のファイルが変わりました。再読み込みしてください。')
        return expected

    def shared_resources(self, root):
        """Select catalog-defined evidence, independent of incidental read history."""
        root = Path(root).resolve()
        table_path = (root/'FTABLE.DAT').resolve()
        if table_path not in self._records:
            return ()
        table = table_path.read_bytes()
        if digest(table) != self._records[table_path]['sha256']:
            raise ValueError('共通資料の配置表が変わりました。アプリを再起動してください。')
        paths = (table_path, *(p.resolve() for p in resource_paths(root, table, SHARED_RESOURCES)))
        if any(not p.is_relative_to(root) for p in paths):
            raise ValueError('共通資料の取得元がインストール先の外です。')
        return tuple(dict.fromkeys(p for p in paths if p in self._records))

    def updated(self, files):
        records = self._records
        for file in files:
            path = Path(file.target).resolve()
            if path not in records: raise ValueError('保存対象の取得元情報がありません。')
            records = records.set(path, dict(records[path], sha256=digest(file.replacement)))
        result = object.__new__(LoadedFiles)
        result._records, result._order, result._parents = records, self._order, self._parents
        return result
