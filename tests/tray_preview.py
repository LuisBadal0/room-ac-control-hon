"""Interactive, account-free tray preview for checking Windows minimize behavior."""
import sys
from pathlib import Path
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1])); sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.tray import SystemTray
from tests.ui_smoke import demo_device

root=tk.Tk()
app=App(root,demo=True)
app.tray=SystemTray()
app.connected([demo_device()])
root.title("Room AC Control · Tray test")
app.status.set("Offline test: minimize this window. It will restore automatically and close.")
deadline=root.after(90000,app.close)

def restored():
    assert root.state()=="normal"
    assert not app.tray.icon.visible
    assert not app.header.native.get_style(app.header.native.hwnd, -16) & app.header.native.CAPTION
    print("PASS: Native tray icon shown, root hidden, restore processed on Tk thread.",flush=True)
    app.tray.events.put("exit")

def watch():
    if app.closing:return
    if root.state()=="withdrawn":
        assert app.tray.icon.visible
        app.tray.events.put("restore")
        root.after(500,restored)
    else:
        root.after(200,watch)

root.after(500,watch)
root.mainloop()
assert app.closing
print("PASS: Tray Exit stopped the application.",flush=True)
