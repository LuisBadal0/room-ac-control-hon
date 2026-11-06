"""Real Tk scrolling checks for All functions with fictional AC data and no cloud commands."""
from copy import deepcopy
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.functions_view import SIZE, SheetWheel
from tests.ui_smoke import demo_device


root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en")
try:
    snapshot = demo_device()
    for key, label in (("selfCleaningStatus", "Self cleaning"), ("selfCleaning56Status", "56°C self cleaning")):
        snapshot["controls"][key] = {"key": key, "label": label, "kind": "enum",
                                     "options": {"Off": "0", "On": "1"}, "value": "0", "reported": True}
    forms = snapshot["commands"]["startProgram"]["forms"]
    form = deepcopy(next(form for form in forms if form["group"] == "maintenance"))
    form.update(category="iot_self_clean_56", label="Self clean 56")
    forms.append(form)
    app.connected([snapshot])
    app.open_functions()
    view = app.functions_view
    for _ in range(20): root.update(); root.after(30)  # Let the fixed-size fit finish.
    assert view.window.resizable() == (False, False)
    size = (view.window.winfo_width(), view.window.winfo_height())
    assert size == SIZE or (size[0] == SIZE[0] and root.winfo_screenheight() < SIZE[1] + 80), size

    def wheel(widget, delta=-120):
        widget.event_generate("<MouseWheel>", delta=delta)
        root.update()

    # Settings is taller than the window: the list scrolls, the header, search and tabs do not.
    assert view.scrollable
    view.content.yview_moveto(0)
    wheel(view.content)
    first = view.content.yview()[0]
    assert first > 0
    for widget in (view.top, view.tabs, view.search_entry):
        before = view.content.yview()
        wheel(widget)
        assert view.content.yview() == before, widget

    # High-resolution wheel deltas accumulate instead of being dropped.
    view.content.yview_moveto(0)
    for _ in range(4): wheel(view.content, -30)
    assert view.content.yview()[0] == first
    for _ in range(60): wheel(view.content)
    assert view.content.yview()[1] == 1
    for _ in range(60): wheel(view.content, 120)
    assert view.content.yview()[0] == 0

    # A short tab stays at the top.
    view.navigate(2)
    root.update()
    assert len(view.visible_items) == 4, view.visible_items
    if not view.scrollable:
        for delta in (120, -120):
            wheel(view.content, delta)
            assert view.content.yview()[0] == 0
    view.navigate(0)
    root.update()
    view.search.set("no-such-function")
    root.update()
    assert not view.scrollable and view.content.yview()[0] == 0 and not view.visible_items
    view.search.set("")
    root.update()
    assert view.scrollable

    # With a preset sheet open, the page stays put and the temperature wheel keeps its own scrolling.
    preset = {"kind": "function", "command": "startProgram", "label": "Offline preset", "section": "everyday",
              "form": {"category": "offline", "parameters": [snapshot["controls"]["tempSel"]]}}
    view.open_preset(preset)
    root.update()
    wheel_widget = next(widget for widget in view.sheet["widgets"] if isinstance(widget, SheetWheel))
    before_page, before_value = view.content.yview(), wheel_widget.value
    wheel(wheel_widget, 120)
    assert view.content.yview() == before_page and wheel_widget.value == before_value + 1
    wheel(view.sheet["canvas"])
    assert view.content.yview() == before_page
    view.close_sheet()
    view.close()
    app.open_functions()
    view = app.functions_view
    root.update()
    wheel(view.content)
    assert view.content.yview()[0] > 0
    print("Wheel routing, content-fit limits, search, fixed window size and preset wheel isolation passed offline.")
finally:
    app.close()
