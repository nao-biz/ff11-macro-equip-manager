"""Read completed export generations for one confirmed identity."""
from pathlib import Path
import re
from .augment_import import MAX_BYTES, parse


class ExportPending(str):
    """Informational import notice, not a read or validation failure."""


EXPORT_PENDING = ExportPending('ゲームにログインすると自動取得されます。ゲーム終了後に自動で反映されます。')


def latest(source):
    directory = Path(source.directory)
    try:
        paths = list(directory.iterdir())
    except FileNotFoundError:
        if directory.parent.is_dir():
            return EXPORT_PENDING
        raise ValueError('自動Exportの配置先が見つかりません: ' + str(directory)) from None
    pattern = re.compile(r'auto-(\d+)-(\d+)-(\d{8}T\d{6}Z)-(\d{6})\.json')
    candidates = []
    for path in paths:
        match = pattern.fullmatch(path.name)
        if match and (match[1], match[2]) == (str(source.server), str(source.character_id)):
            candidates.append((match[3], int(match[4]), path))
    if not candidates:
        return None
    stamp, _, path = max(candidates)
    with path.open('rb') as stream:
        export = parse(stream.read(MAX_BYTES + 1))
    source.verify(export)
    if export.captured_at.replace('-', '').replace(':', '') != stamp:
        raise ValueError('自動Exportのファイル名と取得日時が一致しません。')
    return export
