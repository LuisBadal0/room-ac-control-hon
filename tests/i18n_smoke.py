"""Live English/Portuguese switching with fictional ACs and closed coroutines."""
from copy import deepcopy
from pathlib import Path
import sys
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from room_ac_control.dashboard import App
from room_ac_control.temperature_wheel import TemperatureWheel
from tests.ui_smoke import demo_device


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


root=tk.Tk()
with patch("room_ac_control.i18n.system_language",return_value="pt_PT"):
    app=App(root,demo=True,enable_tray=False)
try:
    root.update()
    assert app.i18n.preference=="system" and app.i18n.language=="pt-PT"
    assert app.login_button.cget("text")=="Entrar  →"
    callbacks=[]
    def submit(coroutine,callback,operation,on_error=None):
        coroutine.close()
        callbacks.append(callback)
    app.worker.submit=submit
    app.sign_in("fixture@example.test","fake-language-test-password")
    started=app.login_view.animation.started
    app.set_language("en")
    assert app.login_view.animation.active and app.login_view.animation.started==started
    assert app.login_view.animation.canvas.itemcget(app.login_view.animation.heading,"text")=="Signing in"
    snapshot=demo_device()
    snapshot.update(name="Cool",model="Heat",room=25.5,target=23.5)
    snapshot["controls"]["tempSel"].update(value=23.5,step=.5)
    callbacks[0]([snapshot])
    app.staged("tempSel","26.5")
    original=deepcopy(app.selected)
    app.set_language("pt-PT")
    root.update()
    assert app.selected==original and app.dirty=={"tempSel":"26.5"}
    assert app.temp.get()=="26.5" and app.mode.get()=="Cool"
    assert app.canvas.itemcget(app.canvas.find_withtag("target-temperature")[0],"text")=="26,5"
    assert app.apply_button.cget("text")=="Aplicar alterações (1)"  # One staged change is counted.
    app.staged("silentSleepStatus","1")
    root.update()
    texts={app.canvas.itemcget(item,"text"):item for item in app.canvas.find_all() if app.canvas.type(item)=="text"}
    assert app.canvas.bbox(texts["Modo"])[3] < app.canvas.bbox(texts["Arrefecer à noite"])[1]
    assert app.status_label.winfo_y()+app.status_label.winfo_height() <= app.body.winfo_height()
    for timer in app.inline_timers.cards.values():
        # Portuguese labels stay inside; outlined polygons report one extra pixel.
        assert all(timer.bbox(item)[2] <= timer.winfo_width() + (1 if timer.type(item) == "polygon" else 0)
                   for item in timer.find_all() if timer.bbox(item))
    app.staged("silentSleepStatus","0")
    device_text=[app.device_picker.itemcget(item,"text") for item in app.device_picker.find_all() if app.device_picker.type(item)=="text"]
    assert "Cool" in device_text and "Heat" in device_text  # Account names are never translated.
    app.open_functions()
    view=app.functions_view
    view.search.set("posicao 1")
    root.update()
    assert any(item.get("key")=="windDirectionVertical" for item in view.visible_items)
    view.search.set("")
    preset={"kind":"function","command":"startProgram","label":"Cool","section":"everyday",
            "form":{"category":"iot_cool","parameters":[snapshot["controls"]["tempSel"]]}}
    view.configure_function(preset)
    root.update()
    wheel=next(child for child in descendants(view.inner) if isinstance(child,TemperatureWheel))
    wheel.step(2)
    assert wheel.get()=="24.5"
    app.language_menu(view.window)
    app.language_panel.choose("en")
    root.update()
    assert view.selected_function is preset and wheel.winfo_exists() and wheel.get()=="24.5"
    assert view.settings_changes=={"tempSel":"26.5"}
    app.set_language("pt-PT")
    assert wheel.get()=="24.5"
    assert "24,5°C" in [wheel.itemcget(item,"text") for item in wheel.find_all() if wheel.type(item)=="text"]
    captured=[]
    app.action=lambda action,requested=None:captured.append((action,requested))
    button=next(child for child in descendants(view.inner) if child.winfo_class()=="TButton" and child.cget("text")=="Iniciar predefinição")
    button.invoke()
    assert captured==[("execute",{"command":"startProgram","category":"iot_cool","parameters":{"tempSel":"24.5"}})]
    assert len(callbacks)==1  # Language changes never initiate another connection or AC command.
    print("System default, live login/dashboard/preset translation, Portuguese search, draft retention and unchanged wire values passed offline.")
finally:
    app.close()
