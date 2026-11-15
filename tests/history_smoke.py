"""The Room chip opens History: a day or a week of room readings kept on this computer, and
energy use from hOn, with their empty, loading and failed states, in both languages and
both themes. Offline preview data only; nothing is requested from hOn."""

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.smooth import texts as canvas_texts

root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
app.connected(devices())
root.update()


def texts():
    return " ".join(text for item, text in canvas_texts(app.sheets.sheet["canvas"]))


def press(label):
    sheet = app.sheets.sheet
    for (x1, y1, x2, y2), action in sheet["hits"]:
        found = sheet["canvas"].find_overlapping(x1 + 2, y1 + 2, x2 - 2, y2 - 2)
        if any(text == label for item, text in canvas_texts(sheet["canvas"]) if item in found):
            action()
            root.update()
            return
    raise AssertionError(f"No button {label!r}")


# The preview keeps a fictional week of readings, so both periods draw a chart.
assert len(app.memory.readings("preview-living-room", 24)) >= 140
app.open_history_sheet()
shown = texts()
for expected in (
    "History",
    "Temperature",
    "Energy",
    "24 hours",
    "7 days",
    "Lowest",
    "Average",
    "Highest",
    "Room",
    "Outside",
    "AC on",
):
    assert expected in shown, (expected, shown)
assert ":00" in shown, shown  # Times under a day's chart.
press("7 days")
assert app.sheets.history_hours == 168
assert "Mon" in texts() or "Tue" in texts() or "Sun" in texts(), texts()
assert app.sheets.sheet["height"] < 900, app.sheets.sheet["height"]

# Portuguese and dark mode redraw the open sheet.
app.set_language("pt-PT")
app.sheets.sheet["draw"]()
for expected in ("Histórico", "Temperatura", "Energia", "Mínima", "Média", "Máxima", "AC ligado", "Fechar"):
    assert expected in texts(), (expected, texts())
app.theme_preference = "dark"
app.apply_theme()
app.sheets.sheet["draw"]()
app.set_language("en")
app.sheets.sheet["draw"]()
press("Close")
assert app.sheets.sheet is None

# An AC with no readings yet shows how the chart fills in.
app.memory.history.data.clear()
app.open_history_sheet()
assert "No readings yet" in texts(), texts()
assert "Lowest" not in texts()
app.sheets.close_sheet()

# Energy: the preview's living room reports its use; tiles choose the bars shown.
app.open_history_sheet()
press("Energy")
shown = texts()
for expected in ("This week", "This month", "This year", "kWh", "Highest"):
    assert expected in shown, (expected, shown)
press("This month")
assert app.sheets.energy_period == "month"
press("This year")
assert app.sheets.energy_period == "year"
app.sheets.close_sheet()

# The bedroom, like many ACs, has no energy data in hOn; the sheet says so.
app.selected = app.devices[1]
app.show_device(app.devices[1])
app.open_history_sheet("energy")
assert "No energy data from hOn" in texts(), texts()
# Loading and a failed load with Try again (which asks again).
app.sheets.energy_states["preview-bedroom"] = {"status": "loading"}
app.sheets.sheet["draw"]()
assert "Loading energy use…" in texts(), texts()
app.sheets.energy_states["preview-bedroom"] = {"status": "failed", "values": None}
app.sheets.sheet["draw"]()
assert "Energy use could not be loaded" in texts(), texts()
press("Try again")
assert app.sheets.energy_states["preview-bedroom"]["status"] == "ready"
app.set_language("pt-PT")
app.sheets.sheet["draw"]()
assert "Sem dados de energia do hOn" in texts(), texts()
app.set_language("en")
app.sheets.close_sheet()
app.selected = app.devices[0]
app.show_device(app.devices[0])
app.sheets.history_tab = "temperature"

# A refresh keeps a reading no more often than every ten minutes.
history = app.memory.history
assert history.record(app.memory.account, "preview-living-room", app.selected, now=time.time())
assert not history.record(app.memory.account, "preview-living-room", app.selected, now=time.time() + 60)
app.close()
print(
    "History sheet, temperature periods, energy tiles and states, Portuguese, dark mode and reading spacing passed offline."
)
