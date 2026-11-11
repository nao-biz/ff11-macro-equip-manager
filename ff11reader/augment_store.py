"""Application-owned individual-item observations, independent of edit drafts."""
import hashlib
from dataclasses import replace
import json
from pathlib import Path
from .augment_import import parse, export_value, object_keys
from .augment_observation import reconcile
from .tracing import traced
from .augment_sources import AugmentSources, atomic_json
from .augment_inbox import latest, ExportPending, EXPORT_PENDING
from .windower_settings import WindowerSettings

MAX_STORE_BYTES = 8 * 1024 * 1024


class AugmentStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.sources = AugmentSources(self.directory.parent / 'augment-sources.json')
        self.settings = WindowerSettings(self.directory.parent / 'windower-settings.json')

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
                    or value['version'] not in (1, 2) or value['installation_key'] != installation
                    or value['folder_id'] != folder):
                raise ValueError('保存済み個体情報の版またはキャラ対応が一致しません。')
            export = parse(json.dumps(value['export'], ensure_ascii=False).encode('utf-8'))
            source = self.sources.require(installation, folder)
            source.verify(export)
            if value['version'] == 2 and value.get('binding') != [source.character_id, source.server]:
                raise ValueError('保存済み個体情報のキャラ対応が一致しません。')
            return export
        except (KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError('保存済み個体情報の構造が不正です。') from exc

    @traced('augment.save')
    def save(self, installation, folder, export):
        source = self.sources.require(installation, folder)
        source.verify(export)
        value = dict(format='ff11-augment-store', version=2,
                              installation_key=installation, folder_id=folder,
                              binding=[source.character_id, source.server],
                              export=export_value(export))
        data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        if len(data) > MAX_STORE_BYTES:
            raise ValueError('個体情報が保存サイズ上限を超えています。')
        # Validate before creating any file, including programmatic callers.
        parse(json.dumps(export_value(export), ensure_ascii=False).encode('utf-8'))
        atomic_json(self.path(installation, folder), value)

    @traced('augment.restore')
    def restore(self, snapshot):
        observations, errors = {}, {}
        try:
            from .augment_binding import discover
            inbox = self.settings.inbox()
            if inbox is not None:
                discover(inbox, snapshot.installation_key,
                         {c.folder_id for c in snapshot.characters}, self.sources)
        except (OSError, ValueError) as exc:
            errors['キャラ対応'] = str(exc)
        for character in snapshot.characters:
            export = None
            try:
                export = self.load(snapshot.installation_key, character.folder_id)
                source = self.sources.get(snapshot.installation_key, character.folder_id)
                if source:
                    inbox = self.settings.inbox()
                    if inbox is not None:
                        source = replace(source, directory=str(inbox))
                    incoming = latest(source)
                    if isinstance(incoming, ExportPending) or (incoming is None and export is None):
                        errors[character.folder_id] = EXPORT_PENDING
                    elif incoming is not None and (export is None or
                            (incoming.captured_at >= export.captured_at and incoming != export)):
                        self.save(snapshot.installation_key, character.folder_id, incoming)
                        export = incoming
            except (OSError, ValueError) as exc:
                errors[character.folder_id] = str(exc)
            if export is not None:
                observations[character.folder_id] = reconcile(export, character, snapshot.rank_augments)
        return observations, errors
