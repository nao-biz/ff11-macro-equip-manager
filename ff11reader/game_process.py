"""Windows game process detection shared by launch, monitoring and save guards."""
import os
import ctypes


def game_running():
    if os.name != 'nt':
        raise RuntimeError('ゲーム起動確認はWindowsのみ対応しています。')
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),
                    ('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),
                    ('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('name',w.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]
    api.CreateToolhelp32Snapshot.restype=w.HANDLE
    api.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
    api.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
    api.CloseHandle.argtypes=[w.HANDLE]
    handle=api.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry)
        if not api.Process32FirstW(handle,ctypes.byref(entry)):raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if entry.name.lower() in ('pol.exe','polboot.exe','ffxi.exe'):
                return True
            if not api.Process32NextW(handle,ctypes.byref(entry)):
                if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
                break
        return False
    finally:api.CloseHandle(handle)
