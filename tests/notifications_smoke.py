"""Windows notifications from the notification area, and their switch in Settings.

Offline preview with a fake tray icon: nothing is shown in Windows and no AC is contacted."""

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.smooth import texts as canvas_texts


class FakeTray:
    def __init__(self):
        self.shown = []

    def notify(self, title, message):
        self.shown.append((title, message))
        return True


root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
app.connected(devices())
root.update()
app.tray = FakeTray()
living = app.devices[0]

# With the window hidden in the notification area, the AC turning off is announced.
app.show_device(dict(living, power="Off"))
assert app.tray.shown == [("Living room turned off", "Turned off outside this app.")], app.tray.shown

# A new error code and a filter reminder, in Portuguese.
app.set_language("pt-PT")
app.show_device(dict(living, power="Off", alerts=[{"kind": "error", "code": "E5"}, {"kind": "filter"}]))
assert ("Living room: erro do AC", "O AC comunica o erro E5. Verifique-o na app hOn.") in app.tray.shown, app.tray.shown
assert (
    "Living room: limpe o filtro de ar",
    "O ar condicionado indica que o filtro precisa de limpeza.",
) in app.tray.shown
app.set_language("en")

# A visible window shows banners instead; nothing is announced.
app.tray.shown.clear()
root.deiconify()
root.update()
app.show_device(dict(living, power="On"))
assert app.tray.shown == [], app.tray.shown
root.withdraw()
root.update()

# Settings › Notifications turns them off.
app.open_settings()
root.update()
panel = app.settings_panel
shown = " ".join(text for item, text in canvas_texts(panel.canvas))
assert "NOTIFICATIONS" in shown and "Windows notifications" in shown, shown
box = next(box for box, action in panel.regions if action == panel.toggle_notifications)
panel.click(type("Event", (), {"x": (box[0] + box[2]) / 2, "y": (box[1] + box[3]) / 2})())
assert app.notifications is False
assert app.storage.notifications() is False
panel.close()
app.show_device(dict(living, power="Off"))
assert app.tray.shown == [], app.tray.shown
app.tray = None
app.close()
print(
    "Tray notifications for power, errors and the filter, Portuguese, visible-window silence and the Settings switch passed offline."
)
