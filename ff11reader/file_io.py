"""Shared file fingerprints, read locks and verified atomic replacement."""
from contextlib import contextmanager
from pathlib import Path
import ctypes
import hashlib
import os
from uuid import uuid4


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_game_closed():
    from .game_process import game_running
    if game_running():
        raise RuntimeError('FF11とPlayOnlineを終了してから保存してください。')


@contextmanager
def locked_read(path, replaceable=False):
    # Deny writers; allow our atomic rename on the one target file.
    if os.name != 'nt':
        with path.open('rb') as stream:
            yield stream.read()
        return
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateFileW(str(path), 0x80000000, 1 | (4 if replaceable else 0),
                             None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield path.read_bytes()
    finally:
        api.CloseHandle(handle)


def atomic_replace(target, data):
    # tempfile.mkstemp can retry PermissionError indefinitely on Windows when
    # os.access incorrectly reports Program Files as writable. Fail immediately.
    name = target.parent / ('.ff11-fix-' + uuid4().hex + '.tmp')
    try:
        with name.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if Path(name).read_bytes() != data:
            raise OSError('一時ファイルの検証に失敗しました。')
        os.replace(name, target)
    finally:
        if name.exists():
            name.unlink()
