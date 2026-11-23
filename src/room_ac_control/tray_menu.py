"""The notification-area menu, drawn in the app's Ambient style instead of a Windows menu.

The tray icon reports a right-click with the cursor position; this opens a small frameless
window there: a row that opens the app, the AC's status card with its power switch, Eco,
the top presets as chips and Exit. It follows the app's theme and language, and closes on
a choice, Escape or a click anywhere else.
"""

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes

from .i18n import refresh_on_language, tr
from .smooth import aa_line, aa_oval, aa_text
from .theme import ACCENTS, C, accent, blend, font, icon, measure, refresh_on_theme, rounded

WIDTH = 288
PAD = 8
ROW = 40
CARD_HEIGHT = 70
CHIP_HEIGHT = 28
CHIP_GAP = 6
WATCH_MS = 50  # How often the menu checks for a click outside it.


def work_area(x, y):
    """The usable part of the monitor under (x, y), without the taskbar; None off Windows."""
    if sys.platform != "win32":
        return None

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    try:
        user = ctypes.windll.user32
        user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user.MonitorFromPoint.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        monitor = user.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # Nearest monitor.
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        if not user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        area = info.rcWork
        return area.left, area.top, area.right, area.bottom
    except (AttributeError, OSError):
        return None


def place(x, y, width, height, area):
    """The menu's top left: above and left of the cursor, kept inside the work area."""
    left, top = x - width, y - height
    if area:
        x1, y1, x2, y2 = area
        left = min(max(left, x1), x2 - width)
        top = min(max(top, y1), y2 - height)
        if y - height < y1:  # A taskbar at the top: open below the cursor.
            top = min(max(y, y1), y2 - height)
    return int(left), int(top)


def faded(color, background):
    """A disabled control's colour: 45 % of it over its background, like the mockup."""
    return blend(color, background, 0.45)


def pill_switch(c, x, y, on, tone, enabled, background):
    """The app's pill switch (widgets.switch), faded into its background while disabled."""
    fade = (lambda color: color) if enabled else (lambda color: faded(color, background))
    rounded(c, x, y, x + 40, y + 24, 12, fill=fade(tone if on else C.STRONG), outline="")
    left = x + 19 if on else x + 3
    aa_oval(c, left, y + 3, left + 18, y + 21, fill=fade(C.BG if on else C.MUTED), outline="")


class TrayMenu:
    """One open menu; the app keeps it in app.tray_menu until it closes."""

    def __init__(self, app, x, y):
        self.app = app
        self.cursor = (x, y)
        self.regions = []
        self.hover = None
        self.closed = False
        self.focused = False  # Lost focus closes the menu only after it had focus.
        self.watch_job = None
        # A sheet's modal grab would swallow the menu's clicks: lend it to the menu while open.
        self.previous_grab = app.root.grab_current()
        if self.previous_grab:
            self.previous_grab.grab_release()
        self.window = tk.Toplevel(app.root)
        try:
            self.build()
        except BaseException:
            self.close()
            raise

    def build(self):
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.window, width=WIDTH, height=200, highlightthickness=0, takefocus=True)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Leave>", lambda event: self.set_hover(None))
        for key, step in (("<Up>", -1), ("<Down>", 1), ("<Tab>", 1), ("<Shift-Tab>", -1)):
            self.canvas.bind(key, lambda event, step=step: self.step(step) or "break")
        self.canvas.bind("<Return>", lambda event: self.choose(self.hover))
        self.canvas.bind("<space>", lambda event: self.choose(self.hover))
        self.canvas.bind("<Escape>", lambda event: self.close())
        self.window.bind("<FocusIn>", self.focus_in)
        self.window.bind("<FocusOut>", self.focus_out)
        refresh_on_theme(self.canvas, self.refresh)
        refresh_on_language(self.canvas, self.refresh)
        self.draw()
        self.position()
        self.window.deiconify()
        self.round_corners()
        self.window.lift()
        self.window.focus_force()
        self.canvas.focus_set()
        self.watch_job = self.window.after(WATCH_MS, self.watch_clicks)

    # State

    @property
    def state(self):
        tray = self.app.tray
        return (tray.state if tray else None) or {}

    def tone(self):
        state = self.state
        if not state or state.get("power") != "On":
            return ACCENTS[C.mode]["off"]
        return accent(state.get("mode_key"))

    # Window

    def position(self):
        self.window.update_idletasks()
        width, height = WIDTH, int(self.canvas.cget("height"))
        x, y = self.cursor
        left, top = place(x, y, width, height, work_area(x, y))
        self.window.geometry(f"{width}x{height}+{left}+{top}")

    def round_corners(self):
        """Windows 11 rounds the frameless window and draws its border in the palette's edge colour."""
        if sys.platform != "win32":
            return
        try:
            self.window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            corner = ctypes.c_int(2)  # DWMWCP_ROUND
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
            red, green, blue = (int(C.EDGE[index : index + 2], 16) for index in (1, 3, 5))
            border = ctypes.c_uint(blue << 16 | green << 8 | red)
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        except (AttributeError, OSError, ValueError):
            pass  # Older Windows: square corners.

    def focus_in(self, event):
        self.focused = True

    def focus_out(self, event):
        # Focus moving between the window and its canvas is not a click elsewhere.
        self.window.after(1, self.close_if_unfocused)

    def close_if_unfocused(self):
        if self.closed or not self.focused:
            return
        try:
            focus = self.window.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        if focus is None or focus.winfo_toplevel() is not self.window:
            self.close()

    def watch_clicks(self):
        """Close on a click outside the menu, even when Windows never gave it focus."""
        self.watch_job = None
        if self.closed:
            return
        if sys.platform == "win32":
            try:
                user = ctypes.windll.user32
                pressed = any(user.GetAsyncKeyState(button) & 0x8000 for button in (0x01, 0x02, 0x04))
                point = wintypes.POINT()
                user.GetCursorPos(ctypes.byref(point))
                w = self.window
                left, top = w.winfo_rootx(), w.winfo_rooty()
                inside = left <= point.x < left + w.winfo_width() and top <= point.y < top + w.winfo_height()
                if pressed and not inside:
                    self.close()
                    return
            except (AttributeError, OSError, tk.TclError):
                pass
        self.watch_job = self.window.after(WATCH_MS, self.watch_clicks)

    def refresh(self):
        """Redraw with the latest state, theme or language, keeping the same corner."""
        if self.closed or not self.canvas.winfo_exists():
            return
        self.draw()
        self.position()
        self.round_corners()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if getattr(self.app, "tray_menu", None) is self:
            self.app.tray_menu = None
        try:
            if self.watch_job is not None:
                self.window.after_cancel(self.watch_job)
            self.window.destroy()
        except tk.TclError:
            pass
        previous = self.previous_grab
        if previous is not None:
            try:
                if previous.winfo_exists():
                    previous.grab_set()
            except tk.TclError:
                pass

    # Input

    def region_at(self, x, y):
        for key, (x1, y1, x2, y2), enabled in self.regions:
            if enabled and x1 <= x <= x2 and y1 <= y <= y2:
                return key
        return None

    def motion(self, event):
        self.set_hover(self.region_at(event.x, event.y))

    def set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.draw()

    def step(self, direction):
        keys = [key for key, _, enabled in self.regions if enabled]
        if not keys:
            return
        index = keys.index(self.hover) if self.hover in keys else (-1 if direction > 0 else 0)
        self.set_hover(keys[(index + direction) % len(keys)])

    def click(self, event):
        self.choose(self.region_at(event.x, event.y))

    def choose(self, key):
        if key is None:
            return
        self.close()
        if key == "restore":
            self.app.restore_window()
        elif key == "exit":
            self.app.close()
        elif key in {"power", "eco"}:
            self.app.tray_action((key,))
        elif key.startswith("preset:"):
            self.app.tray_action(("preset", key.split(":", 1)[1]))

    # Drawing

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.regions = []
        c.configure(bg=C.CARD)
        state = self.state
        tone = self.tone()
        available = bool(state) and not state.get("busy")
        if self.hover is not None and not self.enabled(self.hover, state, available):
            self.hover = None  # A row that just turned disabled loses its highlight.
        y = PAD
        y = self.draw_open(c, y, tone)
        if state:
            y = self.draw_status(c, y + 4, state, tone, available)
            if state.get("eco") is not None:
                y = self.draw_eco(c, y + 2, state, available)
            if state.get("presets"):
                y = self.draw_presets(c, y, state["presets"], available)
        aa_line(c, 18, y + 4, WIDTH - 18, y + 4, fill=C.TRACK)
        y = self.draw_exit(c, y + 9)
        c.configure(height=y + PAD)

    def enabled(self, key, state, available):
        if key in {"restore", "exit"}:
            return True
        if key == "eco":
            return available and state.get("power") == "On"
        return available

    def row(self, c, key, y, height=ROW, enabled=True):
        """A hoverable row; returns its hover fill (the card colour when it is not hovered)."""
        self.regions.append((key, (PAD, y, WIDTH - PAD, y + height), enabled))
        hovered = enabled and self.hover == key
        fill = C.HOVER if C.mode == "light" else C.SURFACE
        if hovered:
            rounded(c, PAD, y, WIDTH - PAD, y + height, 10, fill=fill, outline="")
        return fill if hovered else C.CARD

    def label(self, c, x, y, value, size=-13, weight="semibold", color=None, anchor="w", width=None):
        """Text as given: translate fixed wording with tr() first, never the AC's own names."""
        text = value
        if width is not None:
            text = self.fit(c, text, size, weight, width)
        return aa_text(c, x, y, text=text, anchor=anchor, fill=color or C.TEXT, font=font(size, weight))

    def fit(self, c, text, size, weight, width):
        """Shorten text with an ellipsis so it fits width."""
        if measure(c, text, size, weight) <= width:
            return text
        while text and measure(c, text + "…", size, weight) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def draw_open(self, c, y, tone):
        self.row(c, "restore", y)
        middle = y + ROW / 2
        rounded(c, 18, middle - 11, 40, middle + 11, 7, fill=tone, outline="")
        icon(c, "snow", 29, middle, color=C.CARD, scale=0.55, bg=tone)
        self.label(c, 50, middle, tr(c, "Open Room AC Control"), weight="black", width=WIDTH - 50 - 46)
        # An "open in a window" mark: a box with an arrow leaving its corner.
        x, top, color = WIDTH - 36, middle - 8, C.MUTED
        aa_line(
            c, x + 6, top, x + 2, top, x, top + 2, x, top + 14, x + 2, top + 16, x + 14, top + 16, fill=color, width=1.6
        )
        aa_line(c, x + 14, top + 16, x + 16, top + 14, x + 16, top + 10, fill=color, width=1.6, capstyle="round")
        aa_line(c, x + 10, top, x + 16, top, x + 16, top + 6, fill=color, width=1.6, capstyle="round")
        aa_line(c, x + 16, top, x + 8, top + 8, fill=color, width=1.6, capstyle="round")
        return y + ROW

    def draw_status(self, c, y, state, tone, available):
        x1, x2 = PAD + 2, WIDTH - PAD - 2
        card = blend(tone, C.CARD, 0.12)
        rounded(c, x1, y, x2, y + CARD_HEIGHT, 14, fill=card, outline="")
        self.label(c, x1 + 14, y + 20, state.get("name", ""), -12, "bold", C.MUTED, width=x2 - x1 - 86)
        reading = state.get("reading") or "—"
        self.label(c, x1 + 14, y + 47, reading, -26, "black")
        left = x1 + 14 + measure(c, reading, -26, "black") + 8
        mode = (state.get("mode") or "") if state.get("power") == "On" else tr(c, "Off")
        mode = self.fit(c, mode, -11, "black", max(20, x2 - 66 - left - 16))
        pill = measure(c, mode, -11, "black") + 16
        rounded(c, left, y + 43, left + pill, y + 61, 9, fill=blend(tone, C.CARD, 0.18), outline="")
        self.label(c, left + pill / 2, y + 52, mode, -11, "black", tone, "center")
        # The power switch; its whole right end is the target.
        on = state.get("power") == "On"
        sx, sy = x2 - 52, y + (CARD_HEIGHT - 24) / 2
        if available and self.hover == "power":
            rounded(c, sx - 6, sy - 6, sx + 46, sy + 30, 15, fill=blend(tone, C.CARD, 0.22), outline="")
        pill_switch(c, sx, sy, on, tone, available, card)
        self.regions.append(("power", (x2 - 64, y, x2, y + CARD_HEIGHT), available))
        return y + CARD_HEIGHT

    def draw_eco(self, c, y, state, available):
        enabled = available and state.get("power") == "On"
        bg = self.row(c, "eco", y, enabled=enabled)
        middle = y + ROW / 2
        fade = (lambda color: color) if enabled else (lambda color: faded(color, bg))
        icon(c, "leaf", 29, middle, color=fade(C.ECO), scale=0.75, bg=bg)
        self.label(c, 50, middle, tr(c, "Eco"), color=fade(C.TEXT))
        if state.get("power") != "On":
            self.label(
                c, WIDTH - 72, middle, tr(c, "Waits until on"), -11, "semibold", fade(C.FAINT), "e", width=WIDTH - 162
            )
        pill_switch(c, WIDTH - 62, middle - 12, bool(state.get("eco")), C.ECO, enabled, bg)
        return y + ROW

    def draw_presets(self, c, y, presets, available):
        self.label(c, 18, y + 14, tr(c, "Presets").upper(), -10, "black", C.FAINT)
        y += 24
        x, limit = 18, WIDTH - 18
        for key, text, mode in presets:
            text = self.fit(c, text, -12, "bold", limit - 18 - 33)
            width = measure(c, text, -12, "bold") + 33
            if x + width > limit and x > 18:
                x, y = 18, y + CHIP_HEIGHT + CHIP_GAP
            dot = accent(mode) if available else faded(accent(mode), C.SURFACE)
            hovered = available and self.hover == f"preset:{key}"
            fill = blend(dot, C.CARD, 0.18) if hovered else C.SURFACE
            rounded(c, x, y, x + width, y + CHIP_HEIGHT, CHIP_HEIGHT / 2, fill=fill, outline="")
            aa_oval(c, x + 10, y + 10.5, x + 17, y + 17.5, fill=dot, outline="")
            self.label(
                c, x + 23, y + CHIP_HEIGHT / 2, text, -12, "bold", C.TEXT if available else faded(C.TEXT, C.SURFACE)
            )
            self.regions.append((f"preset:{key}", (x, y, x + width, y + CHIP_HEIGHT), available))
            x += width + CHIP_GAP
        return y + CHIP_HEIGHT + 8

    def draw_exit(self, c, y):
        bg = self.row(c, "exit", y)
        middle = y + ROW / 2
        color = C.DANGER if self.hover == "exit" else C.MUTED
        icon(c, "power", 29, middle, color=color, scale=0.62, bg=bg)
        self.label(c, 50, middle, tr(c, "Exit"))
        return y + ROW
