"""Verify native framing and centered dashboard layout without an account."""
import sys
import ctypes
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from tests.ui_smoke import demo_device

root = tk.Tk()
app = App(root, demo=True, enable_tray=False,language="en")
root.title("Room AC Control · Drag regression test")
for _ in range(20): root.update(); root.after(30)  # Let the fixed-size fit finish.
native = app.header.native
style = native.get_style(native.hwnd, -16)
assert not style & native.CAPTION
assert root.resizable() == (False, False)  # Fixed at the minimum size
assert style & 0x00080000  # system menu / taskbar commands
app.connected([demo_device()])
root.update()
# A dense stream of pointer samples must move, not resize/recreate the frame.
rect = ctypes.wintypes.RECT()
native.user.GetWindowRect(native.hwnd, ctypes.byref(rect))
base_x,base_y = rect.left,rect.top
initial_size = (rect.right-rect.left,rect.bottom-rect.top)
client_size = (root.winfo_width(),root.winfo_height())
app.header.drag(SimpleNamespace(x_root=rect.left+200,y_root=rect.top+25))
for frame in range(24):
    for sample in range(20):
        app.header.drag_motion(SimpleNamespace(x_root=base_x+200+(frame%2)*140+sample,
                                              y_root=base_y+25+(frame%3)*30))
    app.header.end_drag()
    root.update()
    native.user.GetWindowRect(native.hwnd, ctypes.byref(rect))
    assert (rect.right-rect.left,rect.bottom-rect.top) == initial_size
    assert (root.winfo_width(),root.winfo_height()) == client_size
    assert not native.get_style(native.hwnd,-16) & native.CAPTION
    app.header.drag(SimpleNamespace(x_root=rect.left+200,y_root=rect.top+25))
app.header.end_drag()
assert app.header.max_button is None  # No maximize: the layout is designed for one size.
# Windows clamps a window to short screens (CI runners use 1024x768).
if root.winfo_screenheight() >= 1000:
    assert (root.winfo_width(), root.winfo_height()) == (540, 920)
else:
    assert root.winfo_width() == 540 and root.winfo_height() <= root.winfo_screenheight()
assert app.body.winfo_width() == 540 and app.canvas.winfo_width() == 500
app.open_functions()
root.update()
view = app.functions_view
assert not view.header.native.get_style(view.header.native.hwnd, -16) & native.CAPTION
view.close()
app.choice_menu("machMode")
root.update()
chooser = app.choice_panel
assert not chooser.header.native.get_style(chooser.header.native.hwnd, -16) & native.CAPTION
chooser.header.close_button.invoke()
root.update()
assert not chooser.window.winfo_exists()
if "--preview" in sys.argv:
    app.status.set("Offline fast-drag regression preview. No AC commands are sent.")
    root.after(120000,app.close)
    root.mainloop()
else:
    app.header.close_button.invoke()
assert app.closing
print("Fast-drag frame stability, integrated headers, fixed window size, centered content and dialog close passed.")
