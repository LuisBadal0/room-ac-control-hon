"""Quick actions in the notification-area menu: the AC's status, power, Eco and top presets.

Offline preview with a fake tray icon; the app's command method is recorded, not run."""

import queue
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.smooth import texts as canvas_texts
from room_ac_control.tray import WM_LBUTTONUP, WM_RBUTTONUP, Icon
from room_ac_control.tray_menu import WIDTH, place


class FakeTray:
    def __init__(self):
        self.events = queue.Queue()
        self.state = {}
        self.ready = True

    def set_state(self, state):
        changed = state != self.state
        self.state = state
        return changed

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
assert (state["name"], state["reading"], state["mode"], state["mode_key"]) == ("Living room", "23.0°", "Cool", "Cool")
assert state["power"] == "On" and state["eco"] is False and not state["busy"], state
labels = {key: label for key, label, mode in state["presets"]}
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
assert app.tray.state["name"] == "Bedroom" and app.tray.state["power"] == "Off", app.tray.state
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

assert app.tray.state["reading"] == "22,0°", app.tray.state


def menu_text():
    return " ".join(text for item, text in canvas_texts(app.tray_menu.canvas))


def regions():
    return {key: enabled for key, box, enabled in app.tray_menu.regions}


# A right-click opens the app's own menu at the cursor; it follows the language and state.
app.tray.events.put(("menu", 900, 900))
app.handle_tray_events()
root.update()
menu = app.tray_menu
assert menu and menu.window.winfo_ismapped(), "menu not shown"
assert menu.window.winfo_width() == WIDTH
shown = menu_text()
for label in ("Abrir Room AC Control", "Bedroom", "22,0°", "Desligado", "Só quando ligado", "PREDEFINIÇÕES", "Sair"):
    assert label in shown, (label, shown)
# Off: Eco waits; power, presets, Open and Exit work.
assert regions()["eco"] is False and regions()["power"] and regions()["restore"] and regions()["exit"], regions()
# A status change redraws the open menu; busy disables everything but Open and Exit.
app.set_busy(True)
root.update()
assert app.tray_menu is menu
assert {key for key, enabled in regions().items() if enabled} == {"restore", "exit"}, regions()
app.set_busy(False)
app.set_language("en")
root.update()
assert "Open Room AC Control" in menu_text() and "Waits until on" in menu_text(), menu_text()
# Keyboard: Down moves through the rows, Escape closes.
menu.step(1)
assert menu.hover == "restore", menu.hover
menu.canvas.event_generate("<Escape>")
root.update()
assert app.tray_menu is None and menu.closed

# Choosing a preset sends it once and closes the menu.
sent.clear()
app.open_tray_menu(900, 900)
root.update()
preset = next(key for key in regions() if key.startswith("preset:"))
app.tray_menu.choose(preset)
assert app.tray_menu is None and [action for action, _ in sent] == ["on"], sent
# Power from the menu, on the selected AC.
sent.clear()
app.open_tray_menu(900, 900)
root.update()
app.tray_menu.choose("power")
assert sent == [("on", {})], sent

# A row that turns disabled while hovered loses its highlight.
app.open_tray_menu(900, 900)
root.update()
app.tray_menu.set_hover("power")
app.set_busy(True)
root.update()
assert app.tray_menu.hover is None, app.tray_menu.hover
app.set_busy(False)
app.tray_menu.close()

# A modal sheet's grab is lent to the menu, so its clicks work, and taken back when it closes.
sheet = tk.Toplevel(root)
sheet.grab_set()
root.update()
app.open_tray_menu(900, 900)
root.update()
assert root.grab_current() is None, root.grab_current()
app.tray_menu.close()
assert root.grab_current() is sheet, root.grab_current()
sheet.grab_release()
sheet.destroy()

# The menu opens above and left of the cursor, inside the screen's work area.
assert place(1900, 1040, 288, 300, (0, 0, 1920, 1040)) == (1612, 740)
assert place(100, 1040, 288, 300, (0, 0, 1920, 1040)) == (0, 740)
assert place(1900, 10, 288, 300, (0, 48, 1920, 1080)) == (1612, 48)  # Taskbar at the top.
assert place(-500, 900, 288, 300, (-1920, 0, 0, 1040)) == (-788, 600)  # A monitor on the left.

# The icon: a left-click shows the window, a right-click asks for the menu at the cursor.
clicks = queue.Queue()
icon = SimpleNamespace(events=clicks, _hwnd=0)
Icon._on_notify(icon, 0, WM_LBUTTONUP)
Icon._on_notify(icon, 0, WM_RBUTTONUP)
assert clicks.get_nowait() == "restore"
kind, x, y = clicks.get_nowait()
assert kind == "menu" and isinstance(x, int) and isinstance(y, int)

app.tray = None
app.close()
print("Tray status, power, Eco, top presets, busy state, Portuguese and the Ambient menu passed offline.")
