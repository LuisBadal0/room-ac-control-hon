"""Dashboard geometry checks with fictional rooms and no AC commands."""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App, WIDTH, TIMER_TOP, TILE_TOP, WINDOW_SIZE, ART, BANNER
from room_ac_control.demo import devices
from room_ac_control.inline_timers import TimerCard


root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
try:
    fixture = devices()[0]
    fixture["controls"].pop("ecoMode")
    app.connected([fixture])
    for _ in range(20): root.update(); root.after(30)  # Let the fixed-size fit finish.
    requests = []
    for card in app.inline_timers.cards.values():
        card.changed = lambda action, due: requests.append((action, due))

    for theme in ("light", "dark"):
        app.theme_preference = theme
        app.apply_theme()
        if True:  # The window has one fixed size; check it in each theme.
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
            timers = app.inline_timers
            start, end = timers.cards["on"], timers.cards["off"]
            # Timers span the canvas, split evenly, and stay between the slider card and tiles.
            assert timers.winfo_width() == round(WIDTH * scale)
            assert timers.winfo_height() == TimerCard.HEIGHT
            assert abs(start.winfo_width() - end.winfo_width()) <= 1
            assert timers.winfo_y() >= TIMER_TOP * scale - 1
            assert timers.winfo_y() + timers.winfo_height() < TILE_TOP * scale
            # The room card and power button share one row inside the body.
            assert app.device_picker.winfo_rootx() + app.device_picker.winfo_width() < app.power_button.winfo_rootx()
            assert app.power_button.winfo_rootx() + app.power_button.winfo_width() <= app.canvas.winfo_rootx() + app.canvas.winfo_width() + 1
            for card in (start, end):
                left, top, right, bottom = card.bbox("all")
                assert left >= -1 and top >= -1  # Outlined polygons report one extra pixel.
                assert right <= card.winfo_width() + 1 and bottom <= card.winfo_height() + 1
                assert card.minute.winfo_x() + card.minute.winfo_width() < card.winfo_width() - 86
                card.motion(SimpleNamespace(x=card.winfo_width()-48, y=72))
                assert card.hover
                card.motion(SimpleNamespace(x=22, y=72))
                assert not card.hover
                card.click(SimpleNamespace(x=card.winfo_width()-48, y=72))
                assert requests[-1][0] == card.action and requests[-1][1] is not None
                # Active timers and their extra Stop action also stay within the card.
                card.set_status(True, datetime.now()+timedelta(hours=1), False)
                card.edited()
                for item in card.find_all():
                    # Canvas's outlined-polygon bounds include one conservative pixel.
                    margin = 2 if card.type(item) == "polygon" else 0
                    assert card.bbox(item)[2] <= card.winfo_width() + margin
                assert card.bbox("stop")[2] <= card.winfo_width()
                card.draft = False
                card.set_status(True, None, False)
            for value in ("16", "25.5", "30"):
                app.temp.set(value)
                app.draw()
                root.update_idletasks()
                number = app.canvas.bbox("target-temperature")
                unit = app.canvas.bbox("temperature-unit")
                assert unit[0] - number[2] >= 6
                # The value stays centred between the − and + buttons.
                assert number[0] > 64 * scale and unit[2] < 456 * scale
            assert app.status_label.winfo_y() + app.status_label.winfo_height() <= app.body.winfo_height()
            # Sensor readings stay beside the unit artwork, above the airflow,
            # in English and in the longer Portuguese labels.
            for language in ("en", "pt-PT"):
                app.set_language(language)
                app.draw()
                root.update_idletasks()
                readings = app.canvas.find_withtag("reading")
                assert len(readings) >= 8, readings
                art = [value * scale for value in ART]
                for item in readings:
                    left, top, right, bottom = app.canvas.bbox(item)
                    assert right <= art[0] or left >= art[2], (language, app.canvas.bbox(item))
                    assert top >= 30 * scale and bottom <= art[3], (language, app.canvas.bbox(item))
                    assert left >= 0 and right <= app.canvas.winfo_width()
                # Each alert banner fits the strip between the unit and the
                # temperature card, with its text inside the banner.
                for alerts in ([{"kind": "error", "code": "E7"}, {"kind": "filter"}],
                               [{"kind": "defrost"}], [{"kind": "filter"}]):
                    app.selected["alerts"] = alerts
                    app.draw()
                    root.update_idletasks()
                    items = app.canvas.find_withtag("alert")
                    assert len(items) >= 4, items
                    for item in items:
                        left, top, right, bottom = app.canvas.bbox(item)
                        margin = 2 if app.canvas.type(item) == "polygon" else 0
                        assert top >= (BANNER[1] * scale) - margin and bottom <= BANNER[3] * scale + margin, (language, alerts)
                        assert left >= -margin and right <= app.canvas.winfo_width() + margin, (language, alerts)
                    assert bottom < TIMER_TOP * scale
                app.selected["alerts"] = []
                app.draw()
                assert not app.canvas.find_withtag("alert")
            app.set_language("en")
    print("Light/dark fixed-size layout, timer bounds and clicks, active Stop and temperature centring passed offline.")
finally:
    app.close()
