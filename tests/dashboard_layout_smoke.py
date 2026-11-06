"""Dashboard geometry and dial/mode/End at interaction checks with fictional rooms and no AC commands."""
from datetime import datetime, timedelta
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import (App, WIDTH, DIAL, DIAL_START, DIAL_SWEEP, MODES_TOP, MODES_HEIGHT, TILE_TOP,
                                       TILE_HEIGHT, TIMER_TOP, READINGS_TOP, READINGS_HEIGHT, WINDOW_SIZE, BANNER)
from room_ac_control.demo import devices
from room_ac_control.inline_timers import EndAtCard


root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
try:
    fixture = devices()[0]
    app.connected([fixture])
    for _ in range(20): root.update(); root.after(30)  # Let the fixed-size fit finish.
    requests = []
    card = app.inline_timers.cards["off"]
    card.changed = lambda action, due: requests.append((action, due))

    for theme in ("light", "dark"):
        app.theme_preference = theme
        app.apply_theme()
        root.update()
        assert root.resizable() == (False, False)
        # Windows caps a window at about the screen height, so short screens
        # (CI runners use 1024x768) cannot show the full 920 px.
        size = (root.winfo_width(), root.winfo_height(), root.winfo_screenheight())
        if root.winfo_screenheight() >= WINDOW_SIZE[1] + 80:
            assert size[:2] == WINDOW_SIZE, size
        else:
            assert size[0] == WINDOW_SIZE[0] and size[1] <= WINDOW_SIZE[1], size
        scale = app.canvas.winfo_width() / WIDTH
        point = lambda x, y: SimpleNamespace(x=x*scale, y=y*scale, delta=0)
        # The End at row spans the canvas below the tiles.
        timers = app.inline_timers
        assert set(timers.cards) == {"off"}
        assert timers.winfo_width() == round(WIDTH * scale)
        assert timers.winfo_height() == EndAtCard.HEIGHT
        assert timers.winfo_y() >= TIMER_TOP * scale - 1
        assert timers.winfo_y() > (TILE_TOP + TILE_HEIGHT) * scale
        # The room name and power button share one row inside the body.
        assert app.device_picker.winfo_rootx() + app.device_picker.winfo_width() < app.power_button.winfo_rootx()
        assert app.power_button.winfo_rootx() + app.power_button.winfo_width() <= app.canvas.winfo_rootx() + app.canvas.winfo_width() + 1
        # Wheels, the repeat chip and Set never overlap, and everything stays in the card.
        width = card.winfo_width()
        assert card.minute.winfo_x() + card.minute.winfo_width() < card.chip_box[0]
        assert card.chip_box[2] < width - 10 - EndAtCard.BUTTON
        for item in card.find_all():
            margin = 2 if card.type(item) in {"polygon", "image"} else 0
            left, top, right, bottom = card.bbox(item)
            assert left >= -1 and top >= -1 and right <= width + margin and bottom <= card.winfo_height() + margin
        button = SimpleNamespace(x=width - 10 - EndAtCard.BUTTON/2, y=42)
        card.motion(button)
        assert card.hover
        card.motion(SimpleNamespace(x=30, y=40))
        assert not card.hover
        card.click(button)
        assert requests[-1][0] == "off" and requests[-1][1] is not None
        # An active timer with an edited time keeps a separate Stop action inside the card.
        card.set_status(True, datetime.now()+timedelta(hours=1), False)
        card.edited()
        assert card.bbox("stop")[2] <= width and card.bbox("stop")[3] <= card.winfo_height()
        card.draft = False
        card.set_status(True, None, False)
        # The value stays centred inside the ring, between − and +.
        for value in ("16", "25.5", "30"):
            app.temp.set(value)
            app.draw()
            root.update_idletasks()
            number = app.canvas.bbox("target-temperature")
            unit = app.canvas.bbox("temperature-unit")
            assert unit[0] >= number[2] - 1  # °C follows the number, as in the mockup.
            assert number[0] > (DIAL[0] - DIAL[2]) * scale and unit[2] < (DIAL[0] + DIAL[2]) * scale
        assert app.status_label.winfo_y() + app.status_label.winfo_height() <= app.body.winfo_height()
        # Dial: clicking the top of the ring picks the middle value; dragging past the
        # ends stops at the limits; the wheel and keys step.
        app.discard()
        cx, cy, r = DIAL
        app.click(point(cx, cy - r))
        assert float(app.temp.get()) == 24, app.temp.get()
        assert app.dial_drag
        app.drag_temperature(point(cx - r, cy + r))  # Below the left end.
        assert float(app.temp.get()) == 16
        angle = math.radians(DIAL_START + DIAL_SWEEP)
        app.drag_temperature(point(cx + r*math.cos(angle) + 30, cy + r*math.sin(angle) + 30))
        assert float(app.temp.get()) == 32
        app.canvas.event_generate("<ButtonRelease-1>")
        root.update()
        assert not app.dial_drag
        app.wheel_temperature(SimpleNamespace(x=cx*scale, y=cy*scale, delta=-120))
        assert float(app.temp.get()) == 31
        app.click(point(cx, cy))  # The centre is not the ring.
        assert float(app.temp.get()) == 31
        assert app.dirty == {"tempSel": "31.0"}
        # Mode bar: the five standard modes; choosing Heat stages it and recolours.
        modes = [option["label"] for option in app.mode_options()]
        assert modes == ["Auto", "Cool", "Dry", "Heat", "Fan"], modes
        segment = (WIDTH - 8 - 4*4) / 5  # Five modes, 4 px apart, inside a 4 px inset.
        app.click(point(4 + 3*(segment+4) + segment/2, MODES_TOP + MODES_HEIGHT/2))
        assert app.dirty["machMode"] == "4" and app.mode.get() == "Heat"
        app.discard()
        assert not app.dirty and app.mode.get() == "Cool"
        # Readings stay inside their strip, in English and the longer Portuguese labels;
        # each alert banner fits the strip below the unit, above the readings.
        for language in ("en", "pt-PT"):
            app.set_language(language)
            app.draw()
            root.update_idletasks()
            readings = app.canvas.find_withtag("reading")
            assert len(readings) >= 12, readings
            for item in readings:
                left, top, right, bottom = app.canvas.bbox(item)
                margin = 2 if app.canvas.type(item) in {"polygon", "image"} else 0
                assert top >= READINGS_TOP * scale - margin and bottom <= (READINGS_TOP + READINGS_HEIGHT) * scale + margin
                assert left >= -margin and right <= app.canvas.winfo_width() + margin
            for alerts in ([{"kind": "error", "code": "E7"}, {"kind": "filter"}], [{"kind": "defrost"}], [{"kind": "filter"}]):
                app.selected["alerts"] = alerts
                app.draw()
                root.update_idletasks()
                items = app.canvas.find_withtag("alert")
                assert len(items) >= 4, items
                for item in items:
                    left, top, right, bottom = app.canvas.bbox(item)
                    margin = 2 if app.canvas.type(item) in {"polygon", "image"} else 0
                    assert top >= (BANNER[1] * scale) - margin and bottom <= BANNER[3] * scale + margin, (language, alerts)
                    assert left >= -margin and right <= app.canvas.winfo_width() + margin, (language, alerts)
                    assert bottom < READINGS_TOP * scale
            app.selected["alerts"] = []
            app.draw()
            assert not app.canvas.find_withtag("alert")
        app.set_language("en")
    print("Light/dark fixed-size layout, dial, mode bar, End at bounds and clicks, readings and alerts passed offline.")
finally:
    app.close()
