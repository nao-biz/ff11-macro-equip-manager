"""Register identities observed at the game's USER-directory boundary."""
import hashlib
from pathlib import Path
import re
from .augment_import import MAX_BYTES, parse
from .augment_sources import AugmentSource


def discover(directory, installation, folders, sources):
    """Only complete newest exports with explicit native provenance can bind."""
    directory = Path(directory)
    folder_names = {folder.casefold(): folder for folder in folders}
    if not directory.exists():
        return
    pattern = re.compile(r'auto-(\d+)-(\d+)-(\d{8}T\d{6}Z)-(\d{6})\.json')
    latest = {}
    for path in directory.iterdir():
        match = pattern.fullmatch(path.name)
        if match:
            key = int(match[1]), int(match[2])
            order = match[3], int(match[4])
            if key not in latest or order > latest[key][0]:
                latest[key] = order, path
    additions = []
    for (server, cid), ((stamp, _), path) in latest.items():
        with path.open('rb') as stream:
            export = parse(stream.read(MAX_BYTES + 1))
        if (export.server, export.character_id) != (server, cid) or export.captured_at.replace('-', '').replace(':', '') != stamp:
            raise ValueError('自動Exportのファイル名とキャラ情報が一致しません。')
        origin = export.origin
        if origin is None:
            continue
        root = Path(origin.installation).resolve()
        if hashlib.sha256(str(root).casefold().encode()).hexdigest() != installation:
            continue
        folder = folder_names.get(origin.folder_id)
        if folder is None:
            continue
        user = (root/'USER').resolve()
        target = (user/folder).resolve()
        if target.parent != user or not target.is_dir():
            raise ValueError('Exportのキャラ保存先を確認できません。')
        additions.append(AugmentSource(installation, folder, cid, server,
                                      str(directory.resolve()), 'ffxi-user-directory-v1: '+path.name))
    sources.register_many(additions)
