"""System tray callbacks are queued for Tk's main thread."""
import queue
from PIL import Image
from pathlib import Path
import pystray
from .diagnostics import diagnostics


class SystemTray:
    def __init__(self):
        self.events = queue.Queue()
        self.ready = False
        with Image.open(Path(__file__).resolve().parent / "assets" / "app-icon.png") as source:
            image = source.convert("RGBA").resize((64,64), Image.Resampling.LANCZOS)
        menu = pystray.Menu(pystray.MenuItem("Open Room AC Control",lambda icon,item:self.events.put("restore"),default=True),
                            pystray.MenuItem("Exit",lambda icon,item:self.events.put("exit")))
        self.icon = pystray.Icon("room_ac_control", image, "Room AC Control for hOn", menu)
        self.icon.run_detached(setup=lambda icon:self.events.put("ready"))

    def show(self):
        if not self.ready:
            return False
        try:
            self.icon.visible = True
            return True
        except Exception as error:
            diagnostics.record("tray_show_failed", error)
            return False

    def hide(self):
        if self.ready:
            self.icon.visible = False

    def close(self):
        self.icon.stop()
