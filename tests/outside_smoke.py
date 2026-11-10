"""The readings row takes outside weather for values the AC does not measure, and opens the
Outside sheet. Offline preview with fictional weather; nothing is requested from hOn."""

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.dashboard.layout import READINGS_HEIGHT, READINGS_TOP, WIDTH
from room_ac_control.demo import devices
from room_ac_control.smooth import texts as canvas_texts

root = tk.Tk()
root.withdraw()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
app.connected(devices())
root.update()


def texts(canvas):
    return " ".join(text for item, text in canvas_texts(canvas))


def clouds():
    """Weather markers drawn in the readings row."""
    return [
        tag
        for item in app.canvas.find_withtag("reading")
        for tag in app.canvas.gettags(item)
        if tag.startswith("icon-")
    ]


def click_reading(index):
    gap = 8
    width = (WIDTH - gap * 3) / 4
    scale = app.scale()
    x = (index * (width + gap) + width / 2) * scale
    y = (READINGS_TOP + READINGS_HEIGHT / 2) * scale
    app.click(type("Event", (), {"x": x, "y": y})())
    root.update()


# Living room: the AC measures humidity and air quality itself, so nothing is marked.
assert app.selected["name"] == "Living room"
assert not clouds(), clouds()

# Bedroom: no humidity sensor and air quality level 0, so both come from the weather.
app.device_picker.current(1)
app.selected = app.devices[1]
app.show_device(app.devices[1])
root.update()
assert len(set(clouds())) == 2, clouds()

# Selecting a reading opens the Outside sheet with every weather value; Close closes it.
click_reading(2)
sheet = app.sheets.sheet
assert sheet is not None
shown = texts(sheet["canvas"])
for expected in ("Outside", "Cloudy", "27°", "46%", "Fair", "10%", "6.2", "14 km/h", "1016 hPa", "Close"):
    assert expected in shown, (expected, shown)
assert "The AC's outdoor unit reads 31°." in shown, shown
assert sheet["height"] <= root.winfo_height() or sheet["height"] < 760, sheet["height"]
sheet["canvas"].update()
close = next(box for box, action in sheet["hits"] if action == app.sheets.close_sheet)
app.sheets.sheet_click(type("Event", (), {"x": (close[0] + close[2]) / 2, "y": (close[1] + close[3]) / 2})())
assert app.sheets.sheet is None

# The Room chip opens nothing; Portuguese labels fit; no weather means no sheet.
click_reading(0)
assert app.sheets.sheet is None
app.set_language("pt-PT")
app.open_outside_sheet()
shown = texts(app.sheets.sheet["canvas"])
for expected in ("Exterior", "Nublado", "Humidade", "Razoável", "Probabilidade de chuva", "Fechar"):
    assert expected in shown, (expected, shown)
if len(sys.argv) > 1:  # A picture for review: python tests/outside_smoke.py <file.png>
    from PIL import ImageGrab

    root.deiconify()
    root.update()
    app.sheets.sheet["draw"]()
    root.after(400, root.quit)
    root.mainloop()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(sys.argv[1])
app.sheets.close_sheet()
app.set_language("en")
quiet = dict(app.selected, weather={})
app.show_device(quiet)
app.open_outside_sheet()
assert app.sheets.sheet is None
app.close()
print("Outside weather readings, markers, the Outside sheet, its Portuguese labels and Close passed offline.")
