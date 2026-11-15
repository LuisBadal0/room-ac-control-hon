"""The notification-area icon: its menu, quick actions and notifications.

pystray runs the icon on its own thread. Menu choices are queued for Tk's main thread,
where the app sends the same commands as its window does. The menu reads a small state
the app sets after each status refresh: the AC's name and reading, power, Eco and the
top presets from Everyday use.
"""

import queue
from pathlib import Path

import pystray
from PIL import Image

from .diagnostics import diagnostics


class SystemTray:
    def __init__(self, language=None):
        self.language = language
        self.events = queue.Queue()
        self.ready = False
        # Set by the app on Tk's thread and read by pystray's menu; replaced, never changed in place.
        self.state = {}
        with Image.open(Path(__file__).resolve().parent / "assets" / "app-icon.png") as source:
            image = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        self.icon = pystray.Icon("room_ac_control", image, "Room AC Control for hOn", pystray.Menu(self.items))
        self.icon.run_detached(setup=lambda icon: self.events.put("ready"))

    def text(self, value):
        return self.language.translate(value) if self.language else value

    def send(self, *event):
        return lambda icon, item: self.events.put(event if len(event) > 1 else event[0])

    def items(self):
        """The menu, built each time it opens from the latest state."""
        state = self.state
        yield pystray.MenuItem(self.text("Open Room AC Control"), self.send("restore"), default=True)
        if state:
            yield pystray.Menu.SEPARATOR
            yield pystray.MenuItem(state["summary"], None, enabled=False)
            available = not state.get("busy")
            power = "Turn off" if state.get("power") == "On" else "Turn on"
            yield pystray.MenuItem(self.text(power), self.send("power"), enabled=available)
            if state.get("eco") is not None:
                yield pystray.MenuItem(
                    self.text("Eco"),
                    self.send("eco"),
                    checked=lambda item: bool(self.state.get("eco")),
                    enabled=available and state.get("power") == "On",
                )
            presets = state.get("presets") or []
            if presets:
                yield pystray.MenuItem(
                    self.text("Presets"),
                    pystray.Menu(
                        *(
                            pystray.MenuItem(label, self.send("preset", key), enabled=available)
                            for key, label in presets
                        )
                    ),
                )
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem(self.text("Exit"), self.send("exit"))

    def set_state(self, state):
        """Show the AC's latest status in the menu; refreshes it only when something changed."""
        if state == self.state:
            return
        self.state = state
        if self.ready:
            try:
                self.icon.update_menu()
            except Exception as error:
                diagnostics.record("tray_show_failed", error)

    def refresh_language(self):
        if self.ready:
            self.icon.update_menu()

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
