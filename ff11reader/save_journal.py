"""Interrupted game-write detection; never stores or restores an edit session."""
import json
import os
from pathlib import Path
from .saving import digest


class SaveJournal:
    def __init__(self, path, installation):
        self.path = Path(path)
        self.installation = installation

    def begin(self, plan):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'version': 1, 'installation': self.installation,
            'files': [{'path': str(Path(f.target).resolve()),
                       'before': digest(f.original), 'after': digest(f.replacement)} for f in plan.files],
        }
        # Keep this handle open during the write. On Windows it also prevents
        # another app instance from deleting an active record during recovery.
        stream = self.path.open('x', encoding='utf-8')
        try:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        except Exception:
            stream.close()
            self.path.unlink()
            raise
        return stream

    def finish(self):
        self.path.unlink()

    def recover(self, snapshot, legacy_path):
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('installation') != self.installation:
            raise ValueError('ゲーム保存の復旧記録とインストール先が一致しません。')
        current = {str(Path(s['path']).resolve()): s['sha256'] for s in snapshot.sources}
        if data.get('version') == 1 and 'files' in data:
            files = data['files']
            if not isinstance(files, list) or not files or any(
                    set(f) != {'path', 'before', 'after'} or f['path'] not in current for f in files):
                raise ValueError('ゲーム保存の復旧記録を確認できません。')
            complete = all(current[f['path']] == f['after'] for f in files)
            original = all(current[f['path']] == f['before'] for f in files)
        else:
            # Older versions wrote the whole draft as a pending record. Inspect
            # source fingerprints only; its edits and history are never resumed.
            before = json.loads(Path(legacy_path).read_text(encoding='utf-8')) if Path(legacy_path).exists() else {}
            def matches(record):
                sources = record.get('sources')
                return bool(sources) and {str(Path(p).resolve()): h for p, h in sources} == current
            complete, original = matches(data), matches(before)
        if not complete and not original:
            raise ValueError('ゲームへの書き戻しが途中で止まっています。バックアップと復旧記録を確認してください。')
        self.finish()
