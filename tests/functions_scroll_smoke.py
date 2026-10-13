"""Real Tk scrolling checks with fictional AC data and no cloud commands."""
from copy import deepcopy
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from tests.ui_smoke import demo_device


root = tk.Tk()
app = App(root, demo=True, enable_tray=False)
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
    view.window.geometry("740x900")
    root.update()

    def wheel(widget, delta=-120):
        widget.event_generate("<MouseWheel>", delta=delta)
        root.update()

    assert view.scrollable and view.bar.winfo_manager() == "pack"
    # A blank frame, the surrounding canvas, cards and scrollbar route one wheel event.
    positions = []
    for widget in (view.inner, view.scroll, view.card_widgets[0], view.bar):
        view.scroll.yview_moveto(0)
        wheel(widget)
        positions.append(view.scroll.yview()[0])
    assert all(position > 0 for position in positions)
    assert len(set(positions)) == 1, positions  # Card bindings must not double-scroll.
    before = view.scroll.yview()
    wheel(view.search_entry)
    assert view.scroll.yview() == before

    # High-resolution wheel deltas accumulate instead of being dropped.
    view.scroll.yview_moveto(0)
    for _ in range(4): wheel(view.inner, -30)
    assert view.scroll.yview()[0] == positions[0]
    for _ in range(30): wheel(view.scroll)
    assert view.scroll.yview()[1] == 1
    for _ in range(30): wheel(view.scroll, 120)
    assert view.scroll.yview()[0] == 0

    view.section = "maintenance"
    view.render_section()
    root.update()
    assert len(view.card_widgets) == 4
    assert not view.scrollable and not view.bar.winfo_manager()
    for widget in (view.inner, view.scroll, view.card_widgets[0]):
        wheel(widget, 120)
        wheel(widget, -120)
        assert view.scroll.yview() == (0, 1)
    view.scroll_to("moveto", 1)
    assert view.scroll.yview() == (0, 1)

    view.section = "settings"
    view.render_section()
    root.update()
    wheel(view.inner)
    assert view.scroll.yview()[0] > 0
    view.search.set("no-such-function")
    root.update()
    assert not view.scrollable and view.scroll.yview() == (0, 1)
    view.search.set("")
    root.update()
    assert view.scrollable
    view.window.geometry("740x1450")
    root.update()
    assert not view.scrollable and view.scroll.yview() == (0, 1)
    view.window.geometry("740x700")
    root.update()
    assert view.scrollable

    # Nested preset labels scroll the pane; numeric inputs keep their own behavior.
    preset = {"kind": "function", "command": "startProgram", "label": "Offline preset",
              "section": "everyday", "form": {"category": "offline", "parameters": [
                  {**snapshot["controls"]["tempSel"], "key": f"offlineTemperature{index}"}
                  for index in range(12)]}}
    view.configure_function(preset)
    root.update()
    detail = view.inner.winfo_children()[0]
    nested = next(child for child in detail.winfo_children() if child.winfo_class() == "TFrame")
    label = next(child for child in nested.winfo_children() if child.winfo_class() == "TLabel")
    spinbox = next(child for child in nested.winfo_children() if child.winfo_class() == "TSpinbox")
    assert view.scrollable
    wheel(label)
    assert view.scroll.yview()[0] > 0
    before = view.scroll.yview()
    wheel(spinbox)
    assert view.scroll.yview() == before
    view.close()
    app.open_functions()
    view = app.functions_view
    root.update()
    wheel(view.inner)
    assert view.scroll.yview()[0] > 0
    print("Blank-space wheel routing, content-fit limits, search, resizing and preset input isolation passed offline.")
finally:
    app.close()
