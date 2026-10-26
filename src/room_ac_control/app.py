"""Launch the source or portable Windows application."""
import argparse
import ctypes
import json
from pathlib import Path
import tkinter as tk

from .dashboard import App
from . import __version__


def check(condition):
    """Self-test check that still runs when Python optimizations strip asserts."""
    if not condition:
        raise RuntimeError("Self-test check failed")


def self_test(output):
    """Check the frozen runtime without loading an account or contacting hOn."""
    root = None
    app = None
    try:
        import pystray
        from awscrt import mqtt5
        from awsiot import mqtt5_client_builder
        from .secure_state import protect
        root = tk.Tk()
        root.withdraw()
        app = App(root,demo=True,enable_tray=False,language="en")
        root.update_idletasks()
        encrypted = protect(b"offline-package-check")
        check(protect(encrypted,decrypt=True) == b"offline-package-check")
        check(app.unit_image.width()>200)
        app.login_view.set_loading(True)
        root.update_idletasks()
        check(app.login_view.animation.active and app.login_view.animation.job is not None)
        app.login_view.set_loading(False)
        check(app.login_view.animation.job is None)
        from .demo import devices
        app.connected(devices())
        root.update_idletasks()
        check(set(app.inline_timers.cards) == {"on", "off"})
        from .temperature_wheel import TemperatureWheel
        wheel = TemperatureWheel(root, {"min":16, "max":30, "step":.5}, 23.5)
        check(wheel.get() == "23.5")
        wheel.step(1)
        check(wheel.get() == "24")
        app.set_language("pt-PT")
        check(app.all_button.cget("text") == "Todas as funções")
        check(app.i18n.number("23.5") == "23,5")
        check(wheel.get() == "24")
        app.set_language("en")
        check(app.all_button.cget("text") == "All functions")
        wheel.destroy()
        from .cloud_timers import select_timers
        timers, _ = select_timers({"scheduledPrograms": [], "scheduleRunningProgramEnd": []})
        check(all(value["due"] is None for value in timers.values()))
        result = {"ok":True,"version":__version__,"assets":True,"encryption":True,"tray":True,"mqtt":True,"timers":True,"login_animation":True,"temperature_wheel":True,"multilingual":True}
    except Exception as error:
        result = {"ok":False,"error":type(error).__name__}
    finally:
        if app:app.close()
        elif root:root.destroy()
    Path(output).write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["ok"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Room AC Control for hOn")
    parser.add_argument("--preview",choices=["login","dashboard"],help="Open an offline design preview")
    parser.add_argument("--self-test",metavar="JSON_FILE",help="Write an offline runtime check report")
    parser.add_argument("--language",choices=["system","en","pt-PT"],help="Choose the interface language for this launch")
    args = parser.parse_args(argv)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RoomACControl.Desktop")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):
        pass
    if args.self_test:
        raise SystemExit(self_test(args.self_test))
    root = tk.Tk()
    app = App(root,demo=bool(args.preview),language=args.language)
    if args.preview:
        root.title("Room AC Control for hOn · Offline preview")
        if args.preview == "dashboard":
            from .demo import devices
            app.connected(devices())
        app.status.set("Offline preview · No AC commands are sent.")
    root.mainloop()


if __name__ == "__main__":
    main()
