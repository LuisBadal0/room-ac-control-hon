"""Exercise refresh callbacks, retries and UI drafts without network calls."""
import copy
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from tests.ui_smoke import demo_device


root = tk.Tk()
root.withdraw()
app = App(root, demo=True,language="en")
app.connected([demo_device()])
app.staged("tempSel", "26")
app.staged("ecoMode", "0")
app.open_functions()
view = app.functions_view
view.change_setting("silentSleepStatus", "1")
new = copy.deepcopy(app.selected)
new.update(room=25.5, target=21, fan="High", power="Off")
new["controls"]["tempSel"]["value"] = 21
new["controls"]["windSpeed"]["value"] = "1"
new["controls"]["healthMode"]["value"] = "1"
app.show_device(new, preserve_edits=True)
root.update_idletasks()
assert app.selected["room"] == 25.5
assert app.selected["power"] == "Off"
assert app.airflow.tone is None
assert view.airflow.tone is None
assert app.temp.get() == "26"
assert app.fan.get() == "High"
assert app.dirty == {"tempSel": "26", "ecoMode": "0"}
assert view.settings_changes["silentSleepStatus"] == "1"
assert view.setting_value(new["controls"]["healthMode"]) == "1"
view.close()

# Replace submission with an offline recorder. Close coroutines to avoid leaks.
submissions = []
def submit(coroutine, callback, operation, on_error=None):
    coroutine.close()
    submissions.append((callback, operation, on_error))
app.worker.submit = submit
app.demo = False
app.auto_refresh()
assert app.auto_inflight
assert not app.busy
assert len(submissions) == 1
assert submissions[-1][1] == "auto-refresh"
app.auto_refresh()
assert len(submissions) == 1  # no overlapping refresh
app.busy = True  # a foreground command has begun while status is in flight
submissions[0][0](new)
assert app.busy  # background results cannot enable controls during a command
app.busy = False

# Cloud messages are coalesced into one scheduled refresh, including during edits.
app.worker.changes.put(new["id"])
app.worker.changes.put(new["id"])
app.poll()
assert app.auto_job is not None
assert app.auto_pending
assert app.dirty["tempSel"] == "26"

app.auto_refresh()
submissions[-1][2]("offline")
assert not app.auto_inflight
assert "Retrying automatically" in app.connection.get()
assert app.auto_job is not None

# Results from a previous device/session must not restore its stale state.
app.auto_refresh()
old_callback = submissions[-1][0]
app.reset_auto()
newer = copy.deepcopy(new)
newer["room"] = 30
app.show_device(newer, preserve_edits=True)
old_callback(new)
assert app.selected["room"] == 30

# An accepted fan selection survives old refresh callbacks and delayed cloud
# reports. It is separate from an unsent draft and never automatically resent.
newer["fan"]="Auto"
newer["controls"]["windSpeed"]["value"]=5
app.show_device(newer)
app.auto_refresh()
stale=submissions[-1][0]
app.staged("windSpeed","3.0")
assert app.fan.get()=="Low"
app.action("apply")
submissions[-1][0]("Accepted offline")
assert app.fan.get()=="Low" and app.pending_changes=={"windSpeed":"3.0"}
assert not app.dirty and str(app.apply_button.cget("state"))=="disabled"
stale(newer)
assert app.fan.get()=="Low"
waiting=copy.deepcopy(newer)
waiting["pending_changes"]={"windSpeed":"3"}
app.show_device(waiting,preserve_edits=True)
assert app.fan.get()=="Low" and app.selected["fan"]=="Auto"
app.open_functions()
assert app.functions_view.setting_value(waiting["controls"]["windSpeed"])=="3"
app.functions_view.close()
app.staged("windSpeed","5")
assert app.dirty=={"windSpeed":"5"}  # The user can explicitly replace the pending request.
app.dirty={}
confirmed=copy.deepcopy(newer)
confirmed.update(fan="Low")
confirmed["controls"]["windSpeed"]["value"]=3
app.show_device(confirmed,preserve_edits=True)
assert app.fan.get()=="Low" and not app.pending_changes
expired=copy.deepcopy(newer)
expired["confirmation_expired"]=True
app.show_device(expired,preserve_edits=True)
assert app.fan.get()=="Auto" and "not confirmed" in app.status.get()

app.close()
print("Automatic refresh, edit preservation, event coalescing, retry and stale-result checks passed.")
