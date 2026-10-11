"""Exercise dashboard and advanced views without contacting an account."""
import asyncio
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.controller import describe
from tests.test_controller import make_device
from pyhon.commands import HonCommand
from room_ac_control.functions_view import section_items
from room_ac_control.choice_widgets import matches


def demo_device():
    device, api = make_device()
    asyncio.run(device.update(force=True))
    categories = {}
    for name, mode in (("iot_cool", "1"), ("iot_heat", "4"), ("iot_self_clean", "1")):
        categories[name] = HonCommand("startProgram", {"parameters": {"onOffStatus": {"typology": "fixed", "fixedValue": "1"}, "machMode": {"typology": "fixed", "fixedValue": mode}}}, device, categories=categories, category_name="PROGRAM." + name.upper())
    device.commands["startProgram"] = categories["iot_cool"]
    snapshot = describe(device)
    snapshot["id"] = "design-preview"
    return snapshot


if __name__ == "__main__":
    root=tk.Tk()
    if "--preview" not in sys.argv:root.withdraw()
    app=App(root,demo=True)
    from room_ac_control.demo import devices as preview_devices
    app.connected(preview_devices())
    app.device_picker.open()
    picker=app.device_picker.choice_panel
    assert len(picker.tiles)==2
    picker.choose(1)
    assert app.selected["id"]=="preview-bedroom"
    assert app.selected["power"]=="Off"
    app.set_busy(True)
    assert not app.device_picker.enabled
    app.set_busy(False)
    assert app.password.cget("show")=="•"
    assert matches({"machMode":"1","silentSleepStatus":"0"},{"machMode":1.0,"silentSleepStatus":0.0})
    app.connected([demo_device()])
    root.update_idletasks()
    assert app.mode.get()=="Cool"
    assert app.airflow.tone=="cool"
    assert app.fan.get()=="Low"
    app.step_temp(1)
    assert float(app.temp.get())==24
    assert app.dirty=={"tempSel":"24.0"}
    app.staged("ecoMode","0")
    assert app.dirty["ecoMode"]=="0"
    app.open_functions()
    root.update_idletasks()
    assert app.dialog.winfo_exists()
    view = app.functions_view
    everyday = section_items(app.selected, "everyday")
    maintenance = section_items(app.selected, "maintenance")
    assert len(everyday) == 4
    assert {item["label"] for item in everyday if item["kind"] == "night"} == {"Cool Night", "Heat Night"}
    assert len(maintenance) == 1
    assert maintenance[0]["form"]["category"] == "iot_self_clean"
    view.section = "everyday"
    view.render_section()
    root.update_idletasks()
    assert len(view.card_widgets) == 4
    view.configure_function(everyday[0])
    root.update_idletasks()
    assert view.selected_function["form"]["category"] == "iot_cool"
    view.section = "maintenance"
    view.render_section()
    root.update_idletasks()
    assert len(view.card_widgets) == 1
    assert app.unit_image.width() > 200
    app.dialog.destroy();app.dialog=None
    app.set_busy(True)
    assert str(app.all_button.cget("state"))=="disabled"
    assert app.hits==[]
    app.set_busy(False)
    app.choice_menu("machMode")
    root.update_idletasks()
    chooser=app.choice_panel
    assert len(chooser.tiles)==7
    night=next(option for option in chooser.options if option["label"]=="Heat Night")
    chooser.choose(night["value"])
    assert app.mode.get()=="Heat Night"
    assert app.dirty["machMode"]=="4"
    assert app.dirty["silentSleepStatus"]=="1"
    assert app.airflow.tone=="cool"  # pending Heat Night does not imply reported heating
    app.choice_menu("machMode")
    app.choice_panel.choose(next(option["value"] for option in app.choice_panel.options if option["label"]=="Cool"))
    assert app.mode.get()=="Cool"
    assert "silentSleepStatus" not in app.dirty
    print("Dashboard, temperature staging, Eco, all-functions view and busy states passed.")
    if "--preview" in sys.argv:
        app.show_device(demo_device())
        app.status.set("Offline design preview. No AC commands are sent.")
        root.mainloop()
    else:app.close()
