"""Repeating schedules in the offline preview, plus cloud wiring through a fake worker."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.schedules import EVERY_DAY, WEEKDAYS, WEEKEND, preview_record
from room_ac_control.schedules_view import DayPicker, ScheduleRow, SIZE

answers = []
messagebox.askyesno = lambda *args, **kwargs: answers.pop(0)

root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
try:
    app.connected(devices())
    sent = []
    real_submit = app.worker.submit
    app.worker.submit = lambda coroutine, *args, **kwargs: (coroutine.close(), sent.append(args))
    root.update()
    device = app.selected["id"]

    # The dashboard's three action buttons fit their labels in both languages.
    for language in ("en", "pt-PT"):
        app.set_language(language)
        root.update()
        for button in (app.apply_button, app.schedules_button, app.all_button):
            assert button.winfo_reqwidth() <= button.winfo_width() + 2, (language, button.cget("text"))
    app.set_language("en")

    # A Start at card with a repeat saves a repeating schedule, then returns to Once.
    card = app.inline_timers.cards["on"]
    app.timer_repeat_menu(card)
    app.repeat_panel.choose("weekend")
    assert card.repeat == WEEKEND and card.draft
    root.update()
    assert "repeat" in card.gettags(card.find_withtag("repeat")[0])
    card.hour.value, card.minute.value = 9, 30
    card.run()
    records = app.preview_records[device]
    assert len(records) == 1 and records[0]["days"] == [5, 6] and "setupStart" in records[0], records
    assert card.repeat == () and not card.draft
    assert "Offline timer preview" in app.status.get()
    # An End at card with chosen days stores an end-only schedule.
    picked = []
    picker = DayPicker(root, (0,), picked.append)
    picker.chips.toggle(0)  # The last selected day cannot be cleared.
    assert picker.chips.days == {0}
    picker.chips.toggle(2)
    picker.done()
    assert picked == [(0, 2)]
    end_card = app.inline_timers.cards["off"]
    end_card.set_repeat(picked[0])
    end_card.run()
    assert records[-1]["days"] == [0, 2] and "setupEnd" in records[-1] and "setupStart" not in records[-1]

    # The Schedules window lists them, pauses, edits, warns on overlap and deletes.
    app.open_schedules()
    view = app.schedules_view
    root.update()
    assert (view.window.winfo_width(), view.window.winfo_height()) == SIZE or root.winfo_screenheight() < SIZE[1] + 80
    assert len(view.rows) == 2
    for theme in ("light", "dark"):
        app.set_theme(theme)
        for language in ("en", "pt-PT"):
            app.set_language(language)
            root.update()
            for row in view.inner.winfo_children():
                assert isinstance(row, ScheduleRow)
                for item in row.find_all():
                    left, top, right, bottom = row.bbox(item)
                    assert left >= -2 and right <= row.winfo_width() + 2, (theme, language, row.itemcget(item, "text") if row.type(item) == "text" else item)
                # Texts on the left never run into the actions on the right.
                actions = [row.bbox(item)[0] for tag in ("edit", "delete", "toggle") for item in row.find_withtag(tag)]
                for item in row.find_all():
                    if row.type(item) == "text" and not set(row.gettags(item)) & {"edit", "delete", "toggle"}:
                        assert row.bbox(item)[2] < min(actions), (theme, language, row.itemcget(item, "text"))
    app.set_language("en")
    app.set_theme("light")
    first = view.rows[0]
    row_widget = view.inner.winfo_children()[0]
    row_widget.on_toggle()
    assert not next(item for item in view.rows if item["id"] == first["id"])["active"]
    row_widget = view.inner.winfo_children()[[item["id"] for item in view.rows].index(first["id"])]
    row_widget.on_toggle()
    assert next(item for item in view.rows if item["id"] == first["id"])["active"]

    view.edit(view.rows[0])
    assert view.in_editor and view.new_button.cget("text") == "Save schedule"
    view.times["off"][0].set(True)
    view.times["off"][1][0].value, view.times["off"][1][1].value = 23, 15
    view.day_chips.set(EVERY_DAY)
    view.save()
    assert not view.in_editor and view.new_button.cget("text") == "New schedule"
    edited = next(item for item in view.rows if item["id"] == first["id"])
    assert edited["end"] == (23, 15) and edited["days"] == EVERY_DAY, edited

    view.edit(None)
    view.times["on"][1][0].value, view.times["on"][1][1].value = 9, 30
    view.day_chips.set((5,))
    answers.append(False)  # Overlaps the weekend 09:30 start; decline.
    count = len(view.rows)
    view.save()
    assert len(view.rows) == count and not view.busy and "Not saved" in view.note.get()
    answers.append(True)
    view.save()
    assert len(view.rows) == count + 1

    for expected in range(count, -1, -1):
        answers.append(True)
        view.inner.winfo_children()[0].on_delete()
        assert len(view.rows) == expected
    root.update()
    assert view.empty.winfo_ismapped() and "No schedules yet" in view.empty.cget("text")
    view.edit(None)
    view.times["on"][0].set(False)
    view.save()
    assert "Choose a start time" in view.note.get()
    view.close()
    assert sent == []  # The preview never reaches the worker.

    # Cloud wiring: an overlap is confirmed before a second request allows it.
    app.demo = False
    calls, results = [], []
    def fake_submit(coroutine, callback, operation, on_error=None):
        coroutine.close()
        calls.append(operation)
        callback(results.pop(0))
    app.worker.submit = fake_submit
    snapshot = dict(app.selected, power="Off")
    conflict = {"row": {"id": "x"}, "time": (7, 0), "days": (0,)}
    results.extend([{"saved": False, "rows": [], "conflicts": [conflict]},
                    {"saved": True, "rows": ["saved"], "conflicts": [], "snapshot": snapshot}])
    answers.append(True)
    done = []
    app.save_schedule(None, (7, 0), None, (0,), {}, done.append, done.append)
    assert calls == ["schedule", "schedule"] and done == [["saved"]]
    assert app.selected["power"] == "Off"  # The refreshed status reaches the dashboard.
    results.append({"saved": False, "rows": [], "conflicts": [conflict]})
    answers.append(False)
    cancelled = []
    app.save_schedule(None, (7, 0), None, (0,), {}, done.append, done.append, cancelled=lambda: cancelled.append(1))
    assert cancelled == [1] and len(calls) == 3
    app.demo = True
    app.worker.submit = real_submit
    assert answers == []
    print("Repeat chips, day picker, schedule list, pause, edit, overlap warning, delete and cloud wiring passed offline.")
finally:
    app.close()
