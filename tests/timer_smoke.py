"""Timer UI and background dispatch checked without network or real credentials."""
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices

root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False)
fixtures = devices()
for device in fixtures:
    device.update(can_on=True, can_off=True)
app.connected(fixtures)
app.staged("tempSel", "26")
app.open_functions()
view = app.functions_view
view.search.set("schedule")
assert [item["kind"] for item in view.visible_items] == ["timer"]
view.close()
app.open_timers()
editor = app.timer_view
editor.fields["on"]["enabled"].set(True)
editor.fields["on"]["time"].set("25:00")
editor.save()
assert "24-hour" in editor.note.get()
assert not app.timers.get(app.memory.account, fixtures[0]["id"])["on"]["enabled"]
editor.fields["on"]["time"].set("08:00")
editor.fields["off"]["enabled"].set(True)
editor.save()
assert "Timers saved" in editor.note.get()
assert "Next:" in editor.saved_labels["on"].get()
app.show_device(app.selected, preserve_edits=True)
assert app.dirty["tempSel"] == "26"
editor.disable()
assert not app.timers.get(app.memory.account, fixtures[0]["id"])["on"]["enabled"]
editor.close()

# Background timer targets an unselected device without consuming the UI draft.
account = app.memory.account
now = datetime.now()
due = now.replace(second=0, microsecond=0).strftime("%H:%M")
app.timers.save(account, fixtures[1]["id"], {
    "on": {"enabled": True, "time": due, "repeat": "once"},
    "off": {"enabled": False, "time": "22:00", "repeat": "daily"}}, now)
# Set a deterministic due marker regardless of the wall-clock minute.
records = app.storage.schedules(account)
records[fixtures[1]["id"]]["on"]["next"] = now.replace(second=0, microsecond=0).isoformat()
app.storage.save_schedules(account, records)
submissions = []
def submit(coroutine, callback, operation, on_error=None):
    coroutine.close()
    submissions.append((callback, operation, on_error))
app.worker.submit = submit
app.demo = False
app.check_timers()
assert submissions[-1][1] == "timer-command"
assert app.busy
assert app.selected["id"] == fixtures[0]["id"]
submissions[-1][0]("Fixture accepted")
assert not app.busy
assert app.dirty == {"tempSel": "26"}
assert app.auto_job is not None
assert app.timers.get(account, fixtures[1]["id"])["on"]["last_result"] == "accepted"
count = len(submissions)
app.check_timers()
assert len(submissions) == count
# Scheduled errors use their callback, without a modal or a lost refresh.
app.busy = True
app.worker.results.put((submissions[-1][2], None, "Fixture timeout", "timer-command"))
app.poll()
assert not app.busy
assert "outcome is unknown" in app.status.get()
assert app.timers.get(account, fixtures[1]["id"])["on"]["last_result"] == "failed"
assert app.dirty == {"tempSel": "26"}
app.close()
print("Timer editor, search, disable, background dispatch and draft preservation passed.")
