"""Quick actions in the notification-area menu: the AC's status, power, Eco and top presets.

Offline preview with a fake tray icon; the app's command method is recorded, not run."""

import queue
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.tray import SystemTray, pystray


class FakeTray:
    def __init__(self):
        self.events = queue.Queue()
        self.state = {}
        self.ready = True

    def set_state(self, state):
        self.state = state

    def refresh_language(self):
        pass

    def notify(self, title, message):
        return True


root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
app.tray = FakeTray()
app.connected(devices())
root.update()
sent = []
app.action = lambda action, requested=None: sent.append((action, requested))

# The menu shows the room, its reading and mode, power, Eco and the top presets.
state = app.tray.state
assert state["summary"] == "Living room · 23.0° · Cool", state
assert state["power"] == "On" and state["eco"] is False and not state["busy"], state
labels = dict(state["presets"])
assert labels, state
assert "coolnight" in labels and labels["coolnight"] == "Cool Night", labels

# Each choice sends what the window would send.
for event in (("power",), ("eco",), ("preset", "coolnight")):
    app.tray.events.put(event)
app.handle_tray_events()
assert sent[0] == ("off", {}), sent
assert sent[1] == ("apply", {"ecoMode": "1"}), sent
action, request = sent[2]
assert action == "on" and request["machMode"] == "1" and request["silentSleepStatus"] == "1", sent[2]

# An AC that is off turns on with its remembered settings; Eco waits until it is on.
sent.clear()
bedroom = app.devices[1]
app.selected = bedroom
app.show_device(bedroom)
assert app.tray.state["summary"].startswith("Bedroom") and app.tray.state["summary"].endswith("Off")
app.tray.events.put(("eco",))
app.tray.events.put(("power",))
app.handle_tray_events()
assert [action for action, _ in sent] == ["on"], sent

# While a command is busy, choices wait; Portuguese labels follow the language.
sent.clear()
app.set_busy(True)
assert app.tray.state["busy"]
app.tray.events.put(("power",))
app.handle_tray_events()
assert sent == []
app.set_busy(False)
app.set_language("pt-PT")
assert app.tray.state["summary"] == "Bedroom · 22,0° · Desligado", app.tray.state

# The real menu: built from that state without starting an icon.
tray = SystemTray.__new__(SystemTray)
tray.language, tray.events, tray.state = app.i18n, queue.Queue(), dict(app.tray.state, power="On", eco=True)
items = list(tray.items())
texts = [item.text for item in items if item is not pystray.Menu.SEPARATOR]
assert "Desligar" in texts and "Eco" in texts and "Predefinições" in texts, texts
tray.state = {}
assert [item.text for item in tray.items() if item is not pystray.Menu.SEPARATOR] == [texts[0], texts[-1]]
app.set_language("en")
app.tray = None
app.close()
print("Tray menu status, power, Eco, top presets, busy state, Portuguese and the real menu passed offline.")
