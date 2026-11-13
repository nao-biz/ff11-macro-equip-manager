"""Validate and restore backup sets with format-specific names and decoding."""
from contextlib import ExitStack
import json
from pathlib import Path
from . import file_io


def read_entries(folder, receipt, target_name, decode):
    entries, seen, root = [], set(), None
    for entry in receipt['files']:
        target = Path(entry['target']).resolve()
        page = entry['page']
        name = target_name(page)
        if target.name != name or target.parent.name != receipt['character'] or target.parent.parent.name.upper() != 'USER':
            raise ValueError('復元先が不正です。')
        if root is None:
            root = target.parent.parent.parent
        if target.parent.parent.parent != root or target in seen:
            raise ValueError('復元先に重複があるか、異なるインストール先のファイルが含まれています。')
        seen.add(target)
        backup = (folder / entry['backup']).resolve()
        if backup.parent != folder:
            raise ValueError('バックアップのパスが不正です。')
        raw = backup.read_bytes()
        if file_io.digest(raw) != entry['before_sha256']:
            raise ValueError('バックアップが破損しています。')
        decode(raw, page)
        require_known(target.read_bytes(), entry, '保存後にファイルが変更されたため、復元を保留しました。')
        entries.append((target, raw, entry))
    return entries


def require_known(raw, entry, message):
    if file_io.digest(raw) not in (entry['before_sha256'], entry['after_sha256']):
        raise ValueError(message)


def execute_restore(entries):
    file_io.require_game_closed()
    with ExitStack() as stack:
        locks = {}
        for target, raw, entry in entries:
            handle = ExitStack()
            stack.enter_context(handle)
            locks[target] = handle
            current = handle.enter_context(file_io.locked_read(target))
            require_known(current, entry, '復元前にファイルが変わりました。')
        for target, raw, entry in entries:
            file_io.require_game_closed()
            locks[target].close()
            require_known(target.read_bytes(), entry, '置換直前にファイルが変わりました。')
            file_io.atomic_replace(target, raw)
            if target.read_bytes() != raw:
                raise OSError('復元後検証に失敗しました。')


def restore_backup_set(folder, apply, *, kinds, label, target_name, decode):
    """Inspect every member first; interrupted restores can be retried safely."""
    folder = Path(folder).resolve()
    receipt = json.loads((folder / 'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('kind') not in kinds or not receipt.get('files'):
        raise ValueError(label+'のバックアップを指定してください。')
    entries = read_entries(folder, receipt, target_name, decode)
    if apply:
        execute_restore(entries)
    return tuple(str(target) for target, _, _ in entries)
