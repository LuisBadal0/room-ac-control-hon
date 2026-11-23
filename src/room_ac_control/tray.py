"""The notification-area icon: its clicks, quick-action state and notifications.

pystray runs the icon on its own thread. A left-click asks Tk's main thread to show the
window; a right-click sends the cursor position, and the app opens its own Ambient menu
there (tray_menu.py) instead of a Windows menu. The menu reads a small state the app sets
after each status refresh: the AC's name, reading and mode, power, Eco and the top presets
from Everyday use.
"""

import ctypes
import queue
from ctypes import wintypes
from pathlib import Path

import pystray
from PIL import Image

from .diagnostics import diagnostics

WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205


class Icon(pystray.Icon):  # type: ignore[valid-type,misc]
    """pystray's Windows icon, with its clicks sent to the app instead of a Windows menu."""

    def __init__(self, events, *args, **kwargs):
        self.events = events
        super().__init__(*args, **kwargs)

    def _on_notify(self, wparam, lparam):
        if lparam == WM_LBUTTONUP:
            self.events.put("restore")
        elif lparam == WM_RBUTTONUP:
            # The shell lets the icon's owner take the foreground now, so the menu can take focus.
            ctypes.windll.user32.SetForegroundWindow(self._hwnd)
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            self.events.put(("menu", point.x, point.y))


class SystemTray:
    def __init__(self, language=None):
        self.language = language
        self.events = queue.Queue()
        self.ready = False
        # Set by the app on Tk's thread and read by the menu; replaced, never changed in place.
        self.state = {}
        with Image.open(Path(__file__).resolve().parent / "assets" / "app-icon.png") as source:
            image = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        self.icon = Icon(self.events, "room_ac_control", image, "Room AC Control for hOn")
        self.icon.run_detached(setup=lambda icon: self.events.put("ready"))

    def set_state(self, state):
        """Keep the AC's latest status for the menu; True when something changed."""
        if state == self.state:
            return False
        self.state = state
        return True

    def show(self):
        if not self.ready:
            return False
        try:
            self.icon.visible = True
            return True
        except Exception as error:
            diagnostics.record("tray_show_failed", error)
            return False

    def notify(self, title, message):
        """A Windows notification from the tray icon; only while the icon is shown."""
        if not self.ready or not self.icon.visible:
            return False
        try:
            self.icon.notify(message, title)
            return True
        except Exception as error:
            diagnostics.record("tray_notify_failed", error)
            return False

    def hide(self):
        if self.ready:
            self.icon.visible = False

    def close(self):
        self.icon.stop()
