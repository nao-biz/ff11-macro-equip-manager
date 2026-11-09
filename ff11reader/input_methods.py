"""Native input composition checks shared by editable widgets."""
def ime_composing(entry):
    """Leave conversion Return/Escape to the Windows IME."""
    import os
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    imm=ctypes.windll.imm32
    imm.ImmGetContext.argtypes=[wintypes.HWND]
    imm.ImmGetContext.restype=wintypes.HANDLE
    imm.ImmGetCompositionStringW.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    imm.ImmReleaseContext.argtypes=[wintypes.HWND,wintypes.HANDLE]
    hwnd=entry.winfo_id();context=imm.ImmGetContext(hwnd)
    if not context:return False
    try:return imm.ImmGetCompositionStringW(context,8,None,0)>0
    finally:imm.ImmReleaseContext(hwnd,context)
