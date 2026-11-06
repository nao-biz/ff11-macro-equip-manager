"""Versioned JSON catalog adapter with concurrency checks and recoverable writes."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .catalog import CATALOG, SOURCES, loads


class SpecError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details

    def data(self):
        return {"code": self.code, "message": str(self), "details": self.details}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def revision(raw):
    return digest({path: hashlib.sha256(data).hexdigest() for path, data in raw.items()})


def decode(raw):
    return raw.decode("utf-8-sig").replace("\r\n", "\n")


def atomic_write(path, data):
    descriptor, name = tempfile.mkstemp(prefix=".spec-manager-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class JsonStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)

    def path(self, relative):
        path = self.root / relative
        if path.resolve() != path or not path.is_relative_to(self.root):
            raise SpecError("unsafe_path", "管理対象のパスが別の場所を指しています。", relative)
        return path

    @contextmanager
    def locked(self):
        state = self.path(".spec-manager")
        state.mkdir(exist_ok=True)
        with self.path(".spec-manager/lock").open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise SpecError("busy", "別の仕様管理処理が実行中です。") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def read(self):
        if self.path(".spec-manager/pending.json").exists():
            raise SpecError("recovery_required", "未完了の更新があります。recoverで元の文書へ復旧してください。")
        try:
            raw = {name: self.path(name).read_bytes() for name in SOURCES}
            for name, data in raw.items():
                if self.path(name).read_bytes() != data:
                    raise SpecError("conflict", "読込中に文書が更新されました。再取得してください。", name)
            data = loads(decode(raw[CATALOG]))
            documents = {name: decode(value) for name, value in raw.items() if name != CATALOG}
        except (OSError, UnicodeError, ValueError) as exc:
            raise SpecError("read_failed", "管理対象のUTF-8文書を読み込めません。", str(exc)) from exc
        return raw, data, documents

    def write(self, before, after):
        pending = self.path(".spec-manager/pending.json")
        current, _, _ = self.read()
        if current != before:
            raise SpecError("conflict", "プレビュー後に文書が更新されました。変更案を作り直してください。")
        changes = {name: {"before": before[name].hex(), "after": data.hex()}
                   for name, data in after.items() if data != before[name]}
        if set(changes) - {CATALOG}:
            raise SpecError("invalid_target", "更新対象は構造化した正本です。")
        if not changes:
            return
        journal = {"version": 1, "changes": changes}
        atomic_write(pending, json.dumps(journal).encode("utf-8"))
        try:
            for name, change in changes.items():
                path = self.path(name)
                if path.read_bytes() != bytes.fromhex(change["before"]):
                    raise SpecError("conflict", "適用中に対象の文書が更新されました。", name)
                atomic_write(path, bytes.fromhex(change["after"]))
            for name, change in changes.items():
                if self.path(name).read_bytes() != bytes.fromhex(change["after"]):
                    raise SpecError("conflict", "適用結果が別の更新と競合しました。", name)
            pending.unlink()
        except Exception as exc:
            try:
                self.recover()
            except Exception as recovery:
                raise SpecError("recovery_required", "更新の復旧が未完了です。pending.jsonを保持しました。",
                                {"write": str(exc), "recovery": str(recovery)}) from exc
            raise SpecError("write_failed", "更新に失敗し、対象文書を元に戻しました。", str(exc)) from exc

    def recover(self):
        """Rollback only known before/after bytes; leave unrelated external edits intact."""
        pending = self.path(".spec-manager/pending.json")
        if not pending.exists():
            return {"recovered": False, "files": []}
        try:
            journal = json.loads(pending.read_text(encoding="utf-8"))
            if (set(journal) != {"version", "changes"} or journal["version"] != 1
                    or not isinstance(journal["changes"], dict) or not journal["changes"]):
                raise ValueError("復旧記録の形式が不正です。")
            changes = journal["changes"]
            for name, change in changes.items():
                if name != CATALOG:
                    raise ValueError("復旧対象が管理対象外です。")
                if set(change) != {"before", "after"}:
                    raise ValueError("復旧内容の形式が不正です。")
                before, after = bytes.fromhex(change["before"]), bytes.fromhex(change["after"])
                if self.path(name).read_bytes() not in (before, after):
                    raise SpecError("recovery_conflict", "対象に別の変更があります。復旧記録と比較してください。", name)
            for name, change in changes.items():
                before, after = bytes.fromhex(change["before"]), bytes.fromhex(change["after"])
                path = self.path(name)
                current = path.read_bytes()
                if current not in (before, after):
                    raise SpecError("recovery_conflict", "復旧中に別の変更が入りました。", name)
                if current != before:
                    atomic_write(path, before)
            pending.unlink()
            return {"recovered": True, "files": sorted(changes)}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise SpecError("recovery_failed", "復旧記録を保持しました。", str(exc)) from exc
