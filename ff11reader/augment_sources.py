"""Confirmed character bindings and local automatic-export inboxes."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import hashlib
from .augment_import import integer, string, object_keys


@dataclass(frozen=True)
class AugmentSource:
    installation_key: str
    folder_id: str
    character_id: int
    server: int
    directory: str
    evidence: str

    def __post_init__(self):
        for text in (self.installation_key, self.folder_id, self.directory, self.evidence):
            if not string(text, 4096): raise ValueError('キャラ対応設定に空の値があります。')
        integer(self.character_id, 1, 0xffffffff)
        integer(self.server, 0, 65535)
        if not Path(self.directory).is_absolute():
            raise ValueError('Export出力先は絶対パスで指定してください。')

    def verify(self, export):
        if (export.character_id, export.server) != (self.character_id, self.server):
            raise ValueError('確認済みキャラID・サーバーとExportが一致しません。')
        if export.origin is not None:
            root = Path(export.origin.installation).resolve()
            installation = hashlib.sha256(str(root).casefold().encode()).hexdigest()
            if installation != self.installation_key or export.origin.folder_id != self.folder_id.casefold():
                raise ValueError('確認済みのUSER保存先とExportが一致しません。')


def atomic_json(path, value):
    """Publish one complete document; retain the previous file on failure."""
    data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    atomic_bytes(path, data)


def atomic_bytes(path, data):
    """Replace one application-managed file after a complete durable write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class AugmentSources:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(1024 * 1024 + 1)
        except FileNotFoundError:
            return {}
        if len(raw) > 1024 * 1024:
            raise ValueError('キャラ対応設定がサイズ上限を超えています。')
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=object_keys)
            if value['format'] != 'ff11-augment-sources' or type(value['version']) is not int or value['version'] != 1:
                raise ValueError('キャラ対応設定の形式・版が不正です。')
            result = {}
            for row in value['sources']:
                source = AugmentSource(**row)
                key = source.installation_key, source.folder_id
                if key in result: raise ValueError('キャラ対応設定が重複しています。')
                result[key] = source
            return result
        except (KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError('キャラ対応設定の構造が不正です。') from exc

    def get(self, installation, folder):
        return self.read().get((installation, folder))

    def require(self, installation, folder):
        source = self.get(installation, folder)
        if source is None:
            raise ValueError('キャラとUSERフォルダの対応が未確認です。ログイン観測による対応登録が必要です。')
        return source

    def register(self, source):
        """Register an already observed binding; conflicting bindings require review."""
        self.register_many([source], update_existing=True)

    def register_many(self, additions, *, update_existing=False):
        """Validate the whole observed batch before publishing any binding."""
        sources = self.read()
        before = dict(sources)
        for source in additions:
            key = source.installation_key, source.folder_id
            old = sources.get(key)
            if old and (old.character_id, old.server) != (source.character_id, source.server):
                raise ValueError('既存のキャラ対応と競合しています。観測結果を再確認してください。')
            if any(s.installation_key == source.installation_key and s.folder_id != source.folder_id
                   and (s.character_id, s.server) == (source.character_id, source.server)
                   for s in sources.values()):
                raise ValueError('同じキャラが複数のUSERフォルダに対応しています。')
            if old is None or update_existing:
                sources[key] = source
        if sources == before:
            return
        value = dict(format='ff11-augment-sources', version=1,
                     sources=[asdict(s) for s in sources.values()])
        atomic_json(self.path, value)


def main():
    """Record the values established by a reviewed login observation."""
    import argparse
    import hashlib
    parser = argparse.ArgumentParser(description='ログイン観測で確認済みのキャラ対応とExport出力先を登録')
    parser.add_argument('--root', required=True)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--character-id', type=int, required=True)
    parser.add_argument('--server', type=int, required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parent.parent/'work/drafts/augment-sources.json')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    folder = (root/'USER'/args.folder).resolve()
    if folder.parent != (root/'USER').resolve() or not folder.is_dir():
        parser.error('対象インストール先のUSER直下にあるフォルダを指定してください。')
    directory = Path(args.directory).resolve()
    if not directory.is_dir(): parser.error('Export出力先が存在しません。')
    installation = hashlib.sha256(str(root).casefold().encode()).hexdigest()
    AugmentSources(args.config).register(AugmentSource(installation, args.folder, args.character_id,
                                                    args.server, str(directory), args.evidence))
    print('確認済み対応を登録しました: ' + str(args.config))


if __name__ == '__main__':
    main()
