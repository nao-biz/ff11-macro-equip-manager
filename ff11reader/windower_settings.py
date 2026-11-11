"""Application-owned Windower location, separate from character bindings."""
import json
from pathlib import Path
from .augment_sources import atomic_json
from .augment_import import object_keys
from . import addon_installer


class WindowerSettings:
    def __init__(self, path):
        self.path = Path(path)

    def _document(self):
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(16385)
        except FileNotFoundError:
            return None
        try:
            if len(raw) > 16384:
                raise ValueError('Windower設定がサイズ上限を超えています。')
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=object_keys)
            if (value['format'] != 'ff11-windower-settings'
                    or type(value['version']) is not int or value['version'] not in (1, 2)):
                raise ValueError('Windower設定の形式・版が不正です。')
            folder = value['folder']
            if not isinstance(folder, str) or not folder or not Path(folder).is_absolute():
                raise ValueError('Windower設定のフォルダが不正です。')
            return value
        except (KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError('Windower設定を読み取れません。設定画面からフォルダを選び直してください。') from exc

    def read(self):
        value = self._document()
        return Path(value['folder']) if value else None

    def save(self, folder):
        if not str(folder).strip():
            raise ValueError('Windowerフォルダを選択してください。')
        root = Path(folder).expanduser().resolve()
        if not (root / 'Windower.exe').is_file():
            raise ValueError('Windower.exeがあるフォルダを選択してください。')
        files, receipt = addon_installer.bundled()
        try:
            previous = self._document()
        except ValueError:
            previous = None  # Explicit folder selection can repair invalid application settings.
        value = dict(format='ff11-windower-settings', version=2, folder=str(root), deployment=receipt)
        if previous == value:
            return root
        addon_installer.install(root, files, self.path.parent/'windower-backups',
                                lambda: atomic_json(self.path, value))
        return root

    def inbox(self):
        root = self.read()
        return root / 'addons' / 'ff11export' / 'data' if root is not None else None
