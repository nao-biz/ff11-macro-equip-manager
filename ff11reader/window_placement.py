"""Place child windows within the parent's monitor work area."""
import sys


def bounded_rect(width, height, parent, area):
    left, top, right, bottom = area
    width, height = min(width, right-left), min(height, bottom-top)
    x = min(max(left, (parent[0]+parent[2]-width)//2), right-width)
    y = min(max(top, (parent[1]+parent[3]-height)//2), bottom-height)
    return x, y, width, height


def native_window(window):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    api.GetAncestor.restype = wintypes.HWND
    return api, api.GetAncestor(window.winfo_id(), 2)


def work_area(parent):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        api, handle = native_window(parent)
        api.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        api.MonitorFromWindow.restype = wintypes.HANDLE
        api.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
        info = MonitorInfo(); info.size = ctypes.sizeof(info)
        if api.GetMonitorInfoW(api.MonitorFromWindow(handle, 2), ctypes.byref(info)):
            r = info.work
            return r.left, r.top, r.right, r.bottom
    return 0, 0, parent.winfo_screenwidth(), parent.winfo_screenheight()


def visible_area(parent):
    left, top, right, bottom = work_area(parent)
    x, y = parent.winfo_rootx(), parent.winfo_rooty()
    return (max(0, left-x), max(0, top-y),
            max(1, min(parent.winfo_width(), right-x)-max(0, left-x)),
            max(1, min(parent.winfo_height(), bottom-y)-max(0, top-y)))


def place(window):
    if not window.winfo_exists():
        return
    parent = window.master.winfo_toplevel()
    area = work_area(parent)
    bounds = (parent.winfo_rootx(), parent.winfo_rooty(),
              parent.winfo_rootx()+parent.winfo_width(), parent.winfo_rooty()+parent.winfo_height())
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        api, handle = native_window(window)
        rect = wintypes.RECT()
        api.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        if api.GetWindowRect(handle, ctypes.byref(rect)):
            x, y, width, height = bounded_rect(rect.right-rect.left, rect.bottom-rect.top, bounds, area)
            api.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT)
            api.SetWindowPos(handle, None, x, y, width, height, 0x14)
            return
    x, y, width, height = bounded_rect(window.winfo_width(), window.winfo_height(), bounds, area)
    window.geometry(f'{width}x{height}+{x}+{y}')


def fit_to_screen(window):
    def schedule():
        after_idle_alive(window, lambda: place(window))
    if window.winfo_viewable():
        schedule()
    else:
        def mapped(event):
            if event.widget is window:
                window.unbind('<Map>', binding)
                schedule()
        binding = window.bind('<Map>', mapped, add='+')


def after_idle_alive(widget, callback):
    """Cancel deferred UI work when its owning widget is destroyed."""
    root = widget._root()
    job = None
    binding = None
    def destroy(event):
        nonlocal job
        if event.widget is widget and job is not None:
            root.after_cancel(job)
            job = None
    def invoke():
        nonlocal job
        job = None
        if widget.winfo_exists():
            widget.unbind('<Destroy>', binding)
            callback()
    binding = widget.bind('<Destroy>', destroy, add='+')
    job = root.after_idle(invoke)
    return job
