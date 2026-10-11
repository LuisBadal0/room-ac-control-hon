"""Account-free visual review of the login or reported HVAC modes."""
import argparse
import ctypes
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from tests.ui_smoke import demo_device

parser = argparse.ArgumentParser()
parser.add_argument("--login", action="store_true")
parser.add_argument("--mode", default="Cool", choices=["Cool", "Heat", "Fan", "Auto", "Off"])
args = parser.parse_args()
ctypes.windll.shcore.SetProcessDpiAwareness(1)
root = tk.Tk()
app = App(root, demo=True, enable_tray=False)
root.title("Room AC Control · Login preview" if args.login else "Room AC Control · Animation preview")
if not args.login:
    device = demo_device()
    device["mode"] = args.mode
    device["power"] = "Off" if args.mode == "Off" else "On"
    if args.mode != "Off":
        device["controls"]["machMode"]["value"] = {"Auto": "0", "Cool": "1", "Heat": "4", "Fan": "6"}[args.mode]
    app.connected([device])
app.status.set("Offline design preview.")
root.after(180000, app.close)
root.mainloop()
