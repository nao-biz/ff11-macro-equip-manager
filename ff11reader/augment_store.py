"""Application-owned individual-item observations, independent of edit drafts."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .augment_import import parse, export_value, object_keys
from .augment_observation import reconcile
from .tracing import traced

MAX_STORE_BYTES = 8 * 1024 * 1024


class AugmentStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, installation, folder):
        key = json.dumps([installation, folder], ensure_ascii=True).encode('ascii')
        return self.directory / (hashlib.sha256(key).hexdigest() + '.json')

    def load(self, installation, folder):
        path = self.path(installation, folder)
        try:
            with path.open('rb') as stream:
                data = stream.read(MAX_STORE_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(data) > MAX_STORE_BYTES:
            raise ValueError('保存済み個体情報がサイズ上限を超えています。')
        try:
            value = json.loads(data.decode('utf-8'), object_pairs_hook=object_keys)
            if (value['format'] != 'ff11-augment-store' or type(value['version']) is not int
                    or value['version'] != 1 or value['installation_key'] != installation
                    or value['folder_id'] != folder):
                raise ValueError('保存済み個体情報の版またはキャラ対応が一致しません。')
            return parse(json.dumps(value['export'], ensure_ascii=False).encode('utf-8'))
        except (KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError('保存済み個体情報の構造が不正です。') from exc

    @traced('augment.save')
    def save(self, installation, folder, export):
        data = json.dumps(dict(format='ff11-augment-store', version=1,
                              installation_key=installation, folder_id=folder,
                              export=export_value(export)), ensure_ascii=False).encode('utf-8')
        if len(data) > MAX_STORE_BYTES:
            raise ValueError('個体情報が保存サイズ上限を超えています。')
        # Validate before creating any file, including programmatic callers.
        parse(json.dumps(export_value(export), ensure_ascii=False).encode('utf-8'))
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(installation, folder)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, suffix='.tmp', delete=False) as stream:
                temp = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    @traced('augment.restore')
    def restore(self, snapshot):
        observations, errors = {}, {}
        for character in snapshot.characters:
            try:
                export = self.load(snapshot.installation_key, character.folder_id)
                if export is not None:
                    observations[character.folder_id] = reconcile(export, character, snapshot.rank_augments)
            except (OSError, ValueError) as exc:
                errors[character.folder_id] = str(exc)
        return observations, errors
