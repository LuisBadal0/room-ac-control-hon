"""Dashboard geometry checks with fictional rooms and no AC commands."""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices


root = tk.Tk()
app = App(root, demo=True, enable_tray=False,language="en")
try:
    fixture = devices()[0]
    fixture["controls"].pop("ecoMode")
    app.connected([fixture])
    requests = []
    for card in app.inline_timers.cards.values():
        card.changed = lambda action, due: requests.append((action, due))

    for geometry in ("540x920", "560x960", "900x1100", "540x920"):
        root.geometry(geometry)
        root.update()
        scale = app.canvas.winfo_width() / 520
        timers = app.inline_timers
        start, end = timers.cards["on"], timers.cards["off"]
        assert timers.winfo_width() == round(512 * scale)
        assert timers.winfo_height() == 114
        assert abs(start.winfo_width() - end.winfo_width()) <= 1
        assert abs(start.winfo_rootx() - app.apply_button.winfo_rootx()) <= 1
        assert abs(end.winfo_rootx() - app.all_button.winfo_rootx()) <= 1
        assert abs(start.winfo_width() - app.apply_button.winfo_width()) <= 1
        assert abs(end.winfo_width() - app.all_button.winfo_width()) <= 1
        assert timers.winfo_y() + timers.winfo_height() < 513 * scale
        for card in (start, end):
            left, top, right, bottom = card.bbox("all")
            assert left >= 0 and top >= 0
            assert right <= card.winfo_width() and bottom <= card.winfo_height()
            assert card.minute.winfo_x() + card.minute.winfo_width() < card.winfo_width() - 84
            card.motion(SimpleNamespace(x=card.winfo_width()-48, y=60))
            assert card.hover
            card.motion(SimpleNamespace(x=22, y=60))
            assert not card.hover
            card.click(SimpleNamespace(x=card.winfo_width()-48, y=60))
            assert requests[-1][0] == card.action and requests[-1][1] is not None
            # Active timers and their extra Stop action also stay within the card.
            card.set_status(True, datetime.now()+timedelta(hours=1), False)
            card.edited()
            for item in card.find_all():
                # Canvas's outlined-polygon bounds include one conservative pixel.
                margin = 1 if card.type(item) == "polygon" else 0
                assert card.bbox(item)[2] <= card.winfo_width() + margin
            assert card.bbox("stop")[2] <= card.winfo_width()
            card.set_status(True, None, False)
        for value in ("16", "25.5", "30"):
            app.temp.set(value)
            app.draw()
            root.update_idletasks()
            number = app.canvas.bbox("target-temperature")
            unit = app.canvas.bbox("temperature-unit")
            assert unit[0] - number[2] >= 6
            assert unit[2] < 283 * scale  # Temperature stays clear of Eco.
        assert app.status_label.winfo_y() + app.status_label.winfo_height() <= app.body.winfo_height()
    print("Minimum/default/wide dashboard alignment, timer bounds and clicks, active Stop and decimal temperature spacing passed offline.")
finally:
    app.close()
