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
    app=App(root,demo=True,language="en")
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
    app.airflow_menu()
    assert len(app.choice_panel.tiles)==6
    position5=next(option for option in app.choice_panel.options if option["label"]=="Position 5")
    app.choice_panel.choose(position5["value"])
    assert app.dirty["windDirectionVertical"]=="7"
    app.choice_menu("machMode")
    main_modes=app.choice_panel.options
    app.choice_panel.close()
    # Dashboard tiles step through their options, as in the mockup.
    app.dirty={}
    app.show_device(app.selected)
    before=app.fan.get()
    app.cycle_fan()
    assert app.fan.get()!=before and "windSpeed" in app.dirty
    app.cycle_airflow()
    assert "windDirectionVertical" in app.dirty
    app.toggle_sleep()
    assert app.dirty["silentSleepStatus"]=="1"
    app.discard()
    assert not app.dirty
    app.open_functions()
    view=app.functions_view
    root.update()
    # Mode tiles, fan speed and the airflow sheet stage on the dashboard; Apply shows the count.
    heat=next(option for option in app.mode_options() if option["label"]=="Heat")
    view.stage_mode(heat)
    assert app.dirty["machMode"]=="4" and view.footer.winfo_manager()
    assert view.apply_button.badge==len(app.dirty)
    view.toggle_feature("silentSleepStatus")
    assert app.dirty["silentSleepStatus"]=="1" and app.mode.get()=="Heat Night"
    view.open_airflow_sheet()
    assert view.sheet and view.sheet_choice
    position1=next(value for label,value in app.selected["controls"]["windDirectionVertical"]["options"].items() if label=="Position 1")
    view.sheet_choice["windDirectionVertical"]=position1
    view.sheet["hits"][-1][1]()  # Set value
    assert app.dirty["windDirectionVertical"]==position1 and view.sheet is None
    view.discard()
    assert not app.dirty and not view.footer.winfo_manager()
    # The Schedules tab lists the preview schedules inside All functions.
    view.navigate(3)
    root.update()
    assert view.section=="schedules" and view.rows is not None
    view.edit_schedule(None)
    schedules=app.schedules_view
    assert schedules and schedules.window.winfo_exists() and schedules.in_editor
    assert str(schedules.window.wm_transient())==str(view.window)
    schedules.close()
    assert view.window.grab_current() is not None and view.rows is not None
    view.close()
    # Settings: theme and language choices apply at once; Sign out is off in the preview.
    app.open_settings()
    panel=app.settings_panel
    root.update()
    panel.pick_look("dark")
    assert app.theme_preference=="dark"
    panel.pick_language("pt-PT")
    assert app.i18n.preference=="pt-PT" and app.all_button.label()=="Todas as funções"
    panel.step_language(-1)
    panel.step_look(-2)
    assert app.i18n.preference=="en" and app.theme_preference=="system"
    assert panel.logout not in [action for box,action in panel.regions]
    panel.close()
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
    view.search.set("silent mode")
    assert any(item.get("key") == "muteStatus" and item["section"] == "settings" for item in view.visible_items)
    silent = app.selected["controls"]["muteStatus"]
    view.edit_setting(silent, None)
    assert view.choice_panel.options[1]["description"] == silent["description"]
    view.choice_panel.choose("1")
    assert app.dirty["muteStatus"] == "1"
    assert "echoStatus" not in app.dirty
    view.search.set("buzzer")
    assert {item.get("key") for item in view.visible_items} == {"echoStatus"}
    view.toggle_feature("echoStatus")
    assert app.dirty["echoStatus"] == "1" and app.dirty["muteStatus"] == "1"
    assert "silentSleepStatus" not in app.dirty
    view.search.set("")
    everyday = section_items(app.selected, "everyday")
    maintenance = section_items(app.selected, "maintenance")
    assert len(everyday) == 4
    assert {item["label"] for item in everyday if item["kind"] == "night"} == {"Cool Night", "Heat Night"}
    assert len(maintenance) == 1
    assert maintenance[0]["form"]["category"] == "iot_self_clean"
    view.search.set("  NIGHT  ")
    root.update_idletasks()
    assert {item["label"] for item in view.visible_items} == {"Cool Night", "Heat Night"}
    assert all(item["section"] == "everyday" for item in view.visible_items)
    assert app.dirty["tempSel"] == "24.0"
    view.search.set("heat night")
    assert len(view.visible_items) == 1
    view.configure_function(view.visible_items[0])
    assert str(view.search_entry.cget("state")) == "disabled"
    view.refresh_status()
    assert view.selected_function["label"] == "Heat Night" and view.sheet
    view.close_sheet()
    assert view.search.get() == "heat night"
    assert len(view.visible_items) == 1
    assert str(view.search_entry.cget("state")) == "normal"
    view.search.set("clean")
    assert len(view.visible_items) == 1
    assert view.visible_items[0]["section"] == "maintenance"
    view.configure_function(view.visible_items[0])
    root.update_idletasks()
    texts=[view.sheet["canvas"].itemcget(item,"text") for item in view.sheet["canvas"].find_all() if view.sheet["canvas"].type(item)=="text"]
    assert "Start maintenance routine" in texts, texts
    view.close_sheet()
    view.search.set("zzzz-no-such-function")
    assert not view.visible_items
    view.reset_search()
    assert view.search.get() == ""
    assert view.visible_items
    view.navigate(1)
    root.update_idletasks()
    assert len(view.visible_items) == 4
    # Each preset card lists what it applies.
    color, glyph, description, features = view.preset_details(next(item for item in view.visible_items if item["kind"] == "night"))
    assert [label for label, *rest in features][:2] == ["Mode", "Temperature"] and ("Sleep", "On", "moon", True) in features
    view.configure_function(next(item for item in everyday if item["kind"] == "function"))
    root.update_idletasks()
    assert view.selected_function["form"]["category"] == "iot_cool"
    view.close_sheet()
    view.navigate(2)
    root.update_idletasks()
    assert len(view.visible_items) == 1
    assert app.unit_image.width() == 270
    view.close()
    app.set_busy(True)
    assert not app.all_button.enabled
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
    else:
        app.close()
        # Keep timer UI coverage in the existing CI UI entry point.
        import subprocess
        subprocess.run([sys.executable, str(Path(__file__).with_name("timer_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("functions_scroll_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("dashboard_layout_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("temperature_wheel_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("i18n_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("theme_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("schedules_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("window_header_smoke.py"))], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("updates_smoke.py"))], check=True)
