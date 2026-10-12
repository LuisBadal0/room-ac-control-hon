"""Inline timer controls: preview only until a persistent hOn endpoint is verified."""
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
app = App(root, demo=True, enable_tray=False)
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
app.select_device()
assert not app.inline_timers.cards["on"].active
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
assert "cannot save or cancel" in app.status.get()
assert not submissions
assert not app.dialog
app.close()
print("Inline time wheels, one-time preview, active color, Stop and unavailable native backend checks passed.")
