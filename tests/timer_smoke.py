"""Inline timer controls with offline preview and cloud-result fixtures."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.inline_timers import ACTIVE
from room_ac_control.theme import CARD

root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False,language="en")
app.connected(devices())
root.update_idletasks()
assert not hasattr(app, "timer_button")
assert not hasattr(app, "timer_job")
assert not hasattr(app, "check_timers")
card = app.inline_timers.cards["off"]
assert card.winfo_manager() == "grid"
assert card.winfo_toplevel() is root
card.hour.value = 23
card.hour.step(1)
assert card.hour.value == 0
card.minute.value = 0
card.minute.step(-1)
assert card.minute.value == 59
# Pointer dragging stages a time without saving a schedule. Background status
# repainting keeps the pointer gesture intact; device changes cancel it.
from types import SimpleNamespace
def pointer(y): return SimpleNamespace(y=y, y_root=300+y)
card.hour.press(pointer(32))
card.hour.drag(pointer(10))
assert card.hour.value == 1
assert card.draft
app.show_device(app.selected, preserve_edits=True)
assert card.hour.drag_state is not None
card.hour.release(pointer(10))
assert not app.preview_timers
app.staged("tempSel", "26")
card.run()
assert card.active
assert card.hour.surface == ACTIVE
assert app.preview_timers[app.selected["id"]]["off"] is not None
assert app.dirty == {"tempSel": "26"}
card.hour.step(1)
assert card.draft
card.run(stop=True)
assert not card.active
assert card.hour.surface == CARD
assert app.preview_timers[app.selected["id"]]["off"] is None
app.change_timer("on", datetime.now() + timedelta(hours=1))
app.show_device(app.selected, preserve_edits=True)
assert app.inline_timers.cards["on"].active
app.device_picker.current(1)
app.inline_timers.cards["on"].hour.press(pointer(32))
app.select_device()
assert not app.inline_timers.cards["on"].active
assert app.inline_timers.cards["on"].hour.drag_state is None
app.set_busy(True)
before = card.hour.value
card.hour.step(1)
assert card.hour.value == before
app.set_busy(False)
# Unsupported native scheduling cannot fall back to a PC timer or send commands.
submissions = []
def submit(coroutine, callback, operation, on_error=None):
    coroutine.close()
    submissions.append(operation)
app.worker.submit = submit
app.demo = False
app.draw()
assert not app.inline_timers.cards["on"].supported
app.change_timer("on", datetime.now() + timedelta(hours=1))
assert "Timers unavailable" in app.status.get()
assert not submissions
assert not app.dialog
# Cloud fixtures show the saved timer, preserve edits, and route failures to a
# status refresh. Coroutine recording guarantees no real request is executed.
from copy import deepcopy
new = deepcopy(app.selected)
due = datetime.now() + timedelta(hours=2)
new["timers"] = {"available": True, "values": {
    "on": {"supported": True, "due": due, "expected": ["fixture-1", "fixture-date"], "count": 1},
    "off": {"supported": True, "due": None, "expected": None, "count": 0}}}
app.show_device(new, preserve_edits=True)
assert app.inline_timers.cards["on"].active
assert app.inline_timers.cards["on"].supported
assert app.inline_timers.cards["on"].hour.surface == ACTIVE
callbacks = []
def native_submit(coroutine, callback, operation, on_error=None):
    coroutine.close()
    callbacks.append((callback, operation, on_error))
app.worker.submit = native_submit
app.staged("tempSel", "26")
app.change_timer("on", None)
assert app.busy and callbacks[-1][1] == "timer"
new["timers"]["values"]["on"].update(due=None, expected=None, count=0)
app.set_busy(False)
callbacks[-1][0](new)
assert not app.inline_timers.cards["on"].active
assert app.dirty == {"tempSel": "26"}
assert "stopped in hOn" in app.status.get()
app.change_timer("off", due)
app.worker.results.put((callbacks[-1][2], None, "fixture error", "timer"))
app.poll()
assert not app.busy
assert app.status.get() == "fixture error"
assert app.auto_job is not None
app.close()
print("Inline wheels, cloud state, active color, Stop, draft preservation and failure refresh passed offline.")
