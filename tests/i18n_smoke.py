"""Live English/Portuguese switching with fictional ACs and closed coroutines."""

import sys
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import WINDOW_SIZE, App
from room_ac_control.smooth import texts as canvas_texts
from room_ac_control.temperature_wheel import TemperatureWheel
from tests.ui_smoke import demo_device


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


root = tk.Tk()
with patch("room_ac_control.i18n.system_language", return_value="pt_PT"):
    app = App(root, demo=True, enable_tray=False)
try:
    root.update()
    assert app.i18n.preference == "system" and app.i18n.language == "pt-PT"
    assert app.login_button.cget("text") == "Entrar  →"
    callbacks = []

    def submit(coroutine, callback, operation, on_error=None):
        coroutine.close()
        callbacks.append(callback)

    app.worker.submit = submit
    app.sign_in("fixture@example.test", "fake-language-test-password")
    started = app.login_view.animation.started
    app.set_language("en")
    assert app.login_view.animation.active and app.login_view.animation.started == started
    assert dict(canvas_texts(app.login_view.animation.canvas))[app.login_view.animation.heading] == "Signing in"
    snapshot = demo_device()
    snapshot.update(name="Cool", model="Heat", room=25.5, target=23.5)
    snapshot["controls"]["tempSel"].update(value=23.5, step=0.5)
    callbacks[0]([snapshot])
    app.staged("tempSel", "26.5")
    original = deepcopy(app.selected)
    app.set_language("pt-PT")
    root.update()
    assert app.selected == original and app.dirty == {"tempSel": "26.5"}
    assert app.temp.get() == "26.5" and app.mode.get() == "Cool"
    assert dict(canvas_texts(app.canvas))[app.canvas.find_withtag("target-temperature")[0]] == "26,5"
    assert app.apply_button.label() == "Aplicar" and app.apply_button.badge == 1  # One staged change is counted.
    app.staged("silentSleepStatus", "1")
    root.update()
    texts = {text: item for item, text in canvas_texts(app.canvas)}
    # Sleep with Cool is Cool Night: the mode bar keeps Cool and the Sleep tile says On.
    assert "Arrefecer" in texts and "A ARREFECER ATÉ" in texts
    assert app.canvas.bbox(texts["Sono"])[3] < app.canvas.bbox(texts["Ligado"])[1]
    for label, item in texts.items():  # Longer Portuguese labels stay on the canvas.
        left, top, right, bottom = app.canvas.bbox(item)
        assert left >= 0 and right <= app.canvas.winfo_width(), label
    # Windows caps a window at about the screen height; short screens (CI runners use
    # 1024x768) cannot show the full window, so the fit is checked only where it can.
    if root.winfo_screenheight() >= WINDOW_SIZE[1] + 80:
        assert app.status_label.winfo_y() + app.status_label.winfo_height() <= app.body.winfo_height()
        for timer in app.inline_timers.cards.values():
            # Portuguese labels stay inside; outlined polygons report one extra pixel.
            assert all(
                timer.bbox(item)[2] <= timer.winfo_width() + (2 if timer.type(item) in {"polygon", "image"} else 0)
                for item in timer.find_all()
                if timer.bbox(item)
            )
    app.staged("silentSleepStatus", "0")
    device_text = [text for item, text in canvas_texts(app.device_picker)]
    # Account names and models are never translated.
    assert "Cool" in device_text and any(text.startswith("Heat · ") for text in device_text), device_text
    app.open_functions()
    view = app.functions_view
    view.search.set("posicao 1")
    root.update()
    assert any(item.get("key") == "windDirectionVertical" for item in view.visible_items)
    view.search.set("")
    preset = {
        "kind": "function",
        "command": "startProgram",
        "label": "Cool",
        "section": "everyday",
        "form": {"category": "iot_cool", "parameters": [snapshot["controls"]["tempSel"]]},
    }
    view.configure_function(preset)
    root.update()
    wheel = next(widget for widget in view.sheet["widgets"] if isinstance(widget, TemperatureWheel))
    wheel.step(2)
    assert wheel.get() == "24.5"
    app.language_menu(view.window)
    app.language_panel.choose("en")
    root.update()
    assert view.selected_function is preset and wheel.winfo_exists() and wheel.get() == "24.5"
    assert app.dirty == {"tempSel": "26.5"}
    app.set_language("pt-PT")
    assert wheel.get() == "24.5"
    assert "24,5°" in [text for item, text in canvas_texts(wheel)]
    captured = []
    app.action = lambda action, requested=None: captured.append((action, requested))
    texts = [text for item, text in canvas_texts(view.sheet["canvas"])]
    assert {"Iniciar predefinição", "Voltar", "Guardar"} <= set(texts), texts
    view.sheet["hits"][-1][1]()  # Start preset.
    assert captured == [
        ("execute", {"command": "startProgram", "category": "iot_cool", "parameters": {"tempSel": "24.5"}})
    ]
    assert len(callbacks) == 1  # Language changes never initiate another connection or AC command.
    print(
        "System default, live login/dashboard/preset translation, Portuguese search, draft retention and unchanged wire values passed offline."
    )
finally:
    app.close()
