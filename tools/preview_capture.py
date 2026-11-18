"""Open the offline design preview, save a picture of the window and close it.

Lets a person or an agent look at a UI change without an account or an AC:
it uses the fictional rooms in room_ac_control.demo and sends no commands.

    .venv\\Scripts\\python.exe tools/preview_capture.py dashboard.png
    .venv\\Scripts\\python.exe tools/preview_capture.py login.png --screen login --theme dark --language pt-PT
"""

import argparse
import ctypes
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App


def capture(output, screen="dashboard", language="en", theme="light", room=0, settle_ms=600):
    from PIL import ImageGrab

    try:  # Match the app's DPI awareness so the picture has the real pixel size.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    app = App(root, demo=True, enable_tray=False, language=language, theme=theme)
    try:
        if screen == "dashboard":
            from room_ac_control.demo import devices

            rooms = devices()
            app.connected(rooms)
            if room:
                app.show_device(rooms[room])
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)  # Nothing else may cover the window in the picture.
        root.update()
        root.after(settle_ms, root.quit)  # Let animations and late layout finish.
        root.mainloop()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        box = (x, y, x + root.winfo_width(), y + root.winfo_height())
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(box, all_screens=True).save(output)
    finally:
        app.close()
    return Path(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Save a picture of the offline design preview")
    parser.add_argument("output", help="PNG file to write")
    parser.add_argument("--screen", choices=["dashboard", "login"], default="dashboard")
    parser.add_argument("--language", choices=["en", "pt-PT"], default="en")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument(
        "--room", type=int, choices=[0, 1], default=0, help="0: Living room (on), 1: Bedroom (off, filter alert)"
    )
    args = parser.parse_args(argv)
    path = capture(args.output, args.screen, args.language, args.theme, args.room)
    print(f"Saved {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
