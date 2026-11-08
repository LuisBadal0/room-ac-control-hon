"""Verify native framing and centered dashboard layout without an account."""

import ctypes
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from tests.ui_smoke import demo_device

root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en")
root.title("Room AC Control · Drag regression test")
for _ in range(20):
    root.update()
    root.after(30)  # Let the fixed-size fit finish.
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
base_x, base_y = rect.left, rect.top
initial_size = (rect.right - rect.left, rect.bottom - rect.top)
client_size = (root.winfo_width(), root.winfo_height())
app.header.drag(SimpleNamespace(x_root=rect.left + 200, y_root=rect.top + 25))
for frame in range(24):
    for sample in range(20):
        app.header.drag_motion(
            SimpleNamespace(x_root=base_x + 200 + (frame % 2) * 140 + sample, y_root=base_y + 25 + (frame % 3) * 30)
        )
    app.header.end_drag()
    root.update()
    native.user.GetWindowRect(native.hwnd, ctypes.byref(rect))
    assert (rect.right - rect.left, rect.bottom - rect.top) == initial_size
    assert (root.winfo_width(), root.winfo_height()) == client_size
    assert not native.get_style(native.hwnd, -16) & native.CAPTION
    app.header.drag(SimpleNamespace(x_root=rect.left + 200, y_root=rect.top + 25))
app.header.end_drag()
assert app.header.max_button is None  # No maximize: the layout is designed for one size.
# Windows caps a window at about the screen height, so short screens
# (CI runners use 1024x768) cannot show the full 920 px.
size = (root.winfo_width(), root.winfo_height(), root.winfo_screenheight())
if root.winfo_screenheight() >= 1000:
    assert size[:2] == (540, 920), size
else:
    assert size[0] == 540 and size[1] <= 920, size
assert app.body.winfo_width() == 540 and app.canvas.winfo_width() == 500


def opened_cleanly(header, size):
    """The dialog stays hidden until its frame and size are final, then shows
    once with no caption, no dialog edge (the white border) and its exact size."""
    window = header.window
    shown = []

    def watch():
        if not window.winfo_exists():
            return
        if float(window.attributes("-alpha")) == 1.0:
            shown.append(
                (
                    window.winfo_width(),
                    window.winfo_height(),
                    header.native.get_style(header.native.hwnd, -16) & native.CAPTION,
                )
            )
        root.after(5, watch)

    watch()
    for _ in range(40):
        root.update()
        root.after(15)
    assert shown, "the dialog never became visible"
    assert shown[0] == (*size, 0), shown[0]  # First visible frame is already final.
    assert not header.native.get_style(header.native.hwnd, -20) & header.native.EDGES
    # Centred over the main window.
    centre = lambda widget: (
        widget.winfo_rootx() + widget.winfo_width() // 2,
        widget.winfo_rooty() + widget.winfo_height() // 2,
    )
    assert all(abs(a - b) <= 2 for a, b in zip(centre(window), centre(root))), (centre(window), centre(root))


from room_ac_control.schedules_view import SIZE as SCHEDULES_SIZE

app.open_functions()
view = app.functions_view
from room_ac_control.functions_view import SIZE as FUNCTIONS_SIZE

if root.winfo_screenheight() >= FUNCTIONS_SIZE[1] + 80:
    opened_cleanly(view.header, FUNCTIONS_SIZE)  # The main window's size, opened over it.
else:  # Short CI screens cap the height, as for the main window.
    for _ in range(40):
        root.update()
        root.after(15)
    assert view.window.winfo_width() == FUNCTIONS_SIZE[0]
view.close()
app.open_schedules()
opened_cleanly(app.schedules_view.header, SCHEDULES_SIZE)
app.schedules_view.close()
root.update()
app.choice_menu("machMode")
root.update()
chooser = app.choice_panel
assert not chooser.header.native.get_style(chooser.header.native.hwnd, -16) & native.CAPTION
chooser.header.close_button.invoke()
root.update()
assert not chooser.window.winfo_exists()
if "--preview" in sys.argv:
    app.status.set("Offline fast-drag regression preview. No AC commands are sent.")
    root.after(120000, app.close)
    root.mainloop()
else:
    app.header.close_button.invoke()
assert app.closing
print("Fast-drag frame stability, integrated headers, fixed window size, centered content and dialog close passed.")
