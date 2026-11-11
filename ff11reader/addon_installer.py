"""Install the bundled exporter and its startup command, preserving other files."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from .augment_sources import atomic_bytes as replace_bytes

FILES = ('ff11export.lua', 'export_core.lua', 'auto_export.lua', 'login_observation.lua',
         'user_directory.lua', 'user_directory_win32.lua', 'ff11identity-v1.dll')
BUNDLE = Path(__file__).resolve().parent.parent / 'addons' / 'ff11export'
AUTOLOAD_REVISION = 1


def bundled():
    files = {name: (BUNDLE / name).read_bytes() for name in FILES}
    version = re.search(rb"_addon.version\s*=\s*['\"]([^'\"]+)", files['ff11export.lua'])
    if version is None:
        raise ValueError('同梱アドオンのバージョンを読み取れません。')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    receipt = dict(completed=True, bundle_sha256=fingerprint,
                   addon_version=version[1].decode('ascii'), autoload_revision=AUTOLOAD_REVISION)
    return files, receipt


def startup_bytes(original):
    """Append an ASCII command without re-encoding existing user settings."""
    if original.startswith((b'\xff\xfe', b'\xfe\xff')) or b'\x00' in original:
        raise ValueError('scripts/init.txtの文字コードに対応していません。UTF-8またはCP932を使用してください。')
    for line in original.removeprefix(b'\xef\xbb\xbf').splitlines():
        active = re.split(rb'#|//', line, maxsplit=1)[0]
        for command in active.split(b';'):
            if re.fullmatch(rb'\s*lua\s+(?:load|l)\s+[\"\']?ff11export[\"\']?\s*', command, re.I):
                return original
    newline = b'\r\n' if b'\r\n' in original or b'\n' not in original else b'\n'
    separator = b'' if not original or original.endswith((b'\n', b'\r')) else newline
    return original + separator + b'lua load ff11export' + newline


@dataclass(frozen=True)
class Change:
    path: Path
    original: bytes | None
    replacement: bytes


def plan(root, files):
    targets = {Path('addons/ff11export') / name: data for name, data in files.items()}
    targets[Path('scripts/init.txt')] = None
    changes = []
    for relative, content in targets.items():
        path = root / relative
        if not path.resolve().is_relative_to(root):
            raise ValueError('Windowerフォルダ外を参照する配置先です: ' + str(path))
        original = path.read_bytes() if path.exists() else None
        replacement = startup_bytes(original or b'') if content is None else content
        if original != replacement:
            changes.append(Change(path, original, replacement))
    return changes


def backup_changes(root, changes, backups):
    backup = Path(backups) / uuid4().hex
    backup.mkdir(parents=True)
    for change in changes:
        if change.original is not None:
            target = backup / change.path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(change.original)
    (backup / 'manifest.json').write_text(json.dumps(dict(root=str(root), files=[
        dict(path=str(c.path.relative_to(root)), existed=c.original is not None)
        for c in changes]), ensure_ascii=False, indent=2), encoding='utf-8')
    return backup


def rollback(changes):
    failures = []
    for change in reversed(changes):
        try:
            if change.original is None:
                change.path.unlink(missing_ok=True)
            else:
                replace_bytes(change.path, change.original)
        except OSError as exc:
            failures.append(str(exc))
    return failures


def install(root, files, backups, commit):
    """Publish config last; roll back installed files if any ordinary step fails."""
    changes = plan(root, files)
    backup = backup_changes(root, changes, backups) if changes else None
    applied = []
    try:
        for change in changes:
            current = change.path.read_bytes() if change.path.exists() else None
            if current != change.original:
                raise OSError('配置中にファイルが変更されました: ' + str(change.path))
            replace_bytes(change.path, change.replacement)
            applied.append(change)
        commit()
    except (OSError, ValueError) as exc:
        failures = rollback(applied)
        if failures:
            raise OSError(f'導入に失敗し、一部を復元できませんでした。バックアップ: {backup}\n'
                          + '\n'.join(failures)) from exc
        raise
