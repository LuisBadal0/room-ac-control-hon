"""Temperature editors and preset drafts exercised without real commands."""
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.temperature_wheel import TemperatureWheel
from tests.ui_smoke import demo_device


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


root = tk.Tk()
app = App(root, demo=True, enable_tray=False,language="en")
try:
    snapshot = demo_device()
    snapshot["controls"]["tempSel"]["step"] = .5
    app.connected([snapshot])
    requests = []
    app.action = lambda action, values=None: requests.append((action, values))
    app.open_functions()
    view = app.functions_view
    view.edit_setting(snapshot["controls"]["tempSel"], None)
    root.update()
    popup = next(child for child in view.window.winfo_children() if isinstance(child, tk.Toplevel))
    wheel = next(child for child in descendants(popup) if isinstance(child, TemperatureWheel))
    assert not any(child.winfo_class() == "TLabel" and child.cget("text") == "Target temperature" for child in descendants(popup))
    assert wheel.get() == "23"
    wheel.event_generate("<MouseWheel>", delta=120)
    root.update()
    assert wheel.get() == "23.5"
    assert not view.settings_changes and not requests
    next(child for child in descendants(popup) if child.winfo_class() == "TButton" and child.cget("text") == "Set value").invoke()
    assert view.settings_changes["tempSel"] == "23.5" and not requests

    preset = {"kind":"function", "command":"startProgram", "label":"Offline cool",
              "section":"everyday", "form":{"category":"iot_cool", "parameters":[snapshot["controls"]["tempSel"]]}}
    view.configure_function(preset)
    root.update()
    wheel = next(child for child in descendants(view.inner) if isinstance(child, TemperatureWheel))
    assert any(child.winfo_class() == "TLabel" and child.cget("text") == "Target temperature" for child in descendants(view.inner))
    before = view.scroll.yview()
    wheel.event_generate("<MouseWheel>", delta=120)
    root.update()
    assert wheel.get() == "23.5" and view.scroll.yview() == before
    wheel.press(SimpleNamespace(y=54, y_root=300))
    wheel.release(SimpleNamespace(y=-66, y_root=180))
    assert wheel.get() == "25.5" and not requests
    next(child for child in descendants(view.inner) if child.winfo_class() == "TButton" and child.cget("text") == "Start preset").invoke()
    assert requests == [("execute", {"command":"startProgram", "category":"iot_cool", "parameters":{"tempSel":"25.5"}})]
    assert not app.dirty  # The main dashboard value is not changed by scrolling.
    print("Temperature setting confirmation, decimal preset drafts and wheel/page-scroll isolation passed offline.")
finally:
    app.close()
