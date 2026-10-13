"""An in-app title bar with ordinary Windows taskbar and resizing behavior."""
from .i18n import localized
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import tkinter as tk

from .theme import BG, CARD, TEXT, MUTED


class WindowsFrame:
    """Remove the caption while preserving the existing Tk window and frame."""
    CAPTION = 0x00C00000

    def __init__(self, window):
        self.window = window
        self.hwnd = None
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        self.get_style = self.user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else self.user.GetWindowLongW
        self.set_style = self.user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else self.user.SetWindowLongW
        self.get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        self.get_style.restype = ctypes.c_ssize_t
        self.set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.set_style.restype = ctypes.c_ssize_t
        self.user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.SetWindowPos.restype = wintypes.BOOL
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetWindowRect.restype = wintypes.BOOL
        self.user.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT]
        self.user.RedrawWindow.restype = wintypes.BOOL

    def apply(self):
        self.hwnd = self.user.GetParent(self.window.winfo_id())
        if not self.hwnd:
            return
        style = self.get_style(self.hwnd, -16)
        if style & self.CAPTION:
            ctypes.set_last_error(0)
            self.set_style(self.hwnd, -16, style & ~self.CAPTION)
            if ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())
            # Recalculate the non-client region without moving or hiding the window.
            self.user.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x0027)
        try:
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(self.hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            # COLORREF for the existing dark-green background, including resize edges.
            border = ctypes.c_uint(0x000e0f0d)
            dwm.DwmSetWindowAttribute(self.hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        except OSError:
            pass

    def position(self):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rect.left, rect.top

    def move_to(self, x, y):
        # Move the existing native window without asking Tk to recalculate its
        # caption geometry. Discard stale copied pixels instead of accumulating
        # old frame edges when pointer events arrive faster than repainting.
        flags = 0x0001 | 0x0004 | 0x0010 | 0x0100  # NOSIZE / NOZORDER / NOACTIVATE / NOCOPYBITS
        if not self.user.SetWindowPos(self.hwnd, None, x, y, 0, 0, flags):
            raise ctypes.WinError(ctypes.get_last_error())

    def repaint(self):
        # Queue a complete repaint, including children and the resize border.
        # Do not start a synchronous nested Tk/Windows event loop.
        self.user.RedrawWindow(self.hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0400)

class WindowHeader:
    def __init__(self, window, title, close, minimize=None, maximize=True):
        self.window = window
        self.drag_origin = None
        self.drag_pending = None
        self.drag_job = None
        self.maximized = None
        self.native = WindowsFrame(window) if sys.platform == "win32" else None
        self.frame = tk.Frame(window, bg=BG, height=40)
        self.frame.pack(side="top", fill="x")
        self.frame.pack_propagate(False)
        image = tk.PhotoImage(master=window, file=str(Path(__file__).parent / "assets" / "app-mark.png"))
        self.image = image.subsample(2)
        logo = tk.Label(self.frame, image=self.image, bg=BG, bd=0)
        logo.pack(side="left", padx=(15, 8))
        label = localized(tk.Label(self.frame, text=title, bg=BG, fg=MUTED, font=("Segoe UI", 10), bd=0))
        label.pack(side="left")
        self.close_button = self.button("×", close, hover="#9b3939")
        self.max_button = self.button("□", self.toggle_maximize) if maximize else None
        self.min_button = self.button("−", minimize) if minimize else None
        for target in (self.frame, label, logo):
            target.bind("<Button-1>", self.drag)
            target.bind("<B1-Motion>", self.drag_motion)
            target.bind("<ButtonRelease-1>", self.end_drag)
            if maximize:
                target.bind("<Double-Button-1>", lambda event: self.toggle_maximize())
        window.bind("<Map>", self.mapped, add="+")
        window.bind("<Configure>", self.configured, add="+")
        window.bind("<Destroy>", self.destroyed, add="+")
        if self.native:
            window.after_idle(self.apply_frame)

    def button(self, text, command, hover=CARD):
        button = tk.Button(self.frame, text=text, command=command, bg=BG, fg=TEXT,
                           activebackground=hover, activeforeground=TEXT, bd=0, relief="flat",
                           font=("Segoe UI", 15), width=3, takefocus=True, cursor="hand2")
        button.pack(side="right", fill="y")
        button.bind("<Enter>", lambda event: button.configure(bg=hover))
        button.bind("<Leave>", lambda event: button.configure(bg=BG))
        return button

    def apply_frame(self):
        if self.window.winfo_exists() and self.native:
            self.native.apply()

    def mapped(self, event):
        if event.widget is self.window:
            self.window.after_idle(self.apply_frame)

    def configured(self, event):
        if event.widget is self.window and self.max_button:
            maximized = self.window.state() == "zoomed"
            if maximized != self.maximized:
                self.maximized = maximized
                self.max_button.configure(text="❐" if maximized else "□")

    def drag(self, event):
        self.end_drag()
        x,y = self.native.position() if self.native and self.native.hwnd else (self.window.winfo_x(),self.window.winfo_y())
        self.drag_origin = (event.x_root,event.y_root,x,y)

    def drag_motion(self, event):
        if self.drag_origin is None:
            return
        sx,sy,x,y = self.drag_origin
        if self.window.state() == "zoomed":
            fraction = (sx-x)/max(1,self.window.winfo_width())
            self.window.state("normal")
            self.window.update_idletasks()
            x = round(event.x_root-self.window.winfo_width()*fraction)
            y = event.y_root-20
            self.drag_origin = (event.x_root,event.y_root,x,y)
        else:
            x += event.x_root-sx
            y += event.y_root-sy
        self.drag_pending = (x,y)
        # Coalesce fast pointer events to at most one move per display frame.
        if self.drag_job is None:
            self.drag_job = self.window.after(16,self.flush_drag)

    def flush_drag(self):
        self.drag_job = None
        position,self.drag_pending = self.drag_pending,None
        if position is not None:
            if self.native and self.native.hwnd:
                self.native.move_to(*position)
            else:
                self.window.geometry(f"+{position[0]}+{position[1]}")

    def end_drag(self, event=None):
        if self.drag_job is not None:
            self.window.after_cancel(self.drag_job)
            self.drag_job = None
        self.flush_drag()
        moved = self.drag_origin is not None
        self.drag_origin = None
        if moved and self.native and self.native.hwnd:
            self.native.repaint()

    def destroyed(self, event):
        if event.widget is self.window:
            if self.drag_job is not None:
                self.window.after_cancel(self.drag_job)
                self.drag_job = None
            self.drag_pending = None
            self.drag_origin = None

    def toggle_maximize(self):
        self.window.state("normal" if self.window.state() == "zoomed" else "zoomed")
