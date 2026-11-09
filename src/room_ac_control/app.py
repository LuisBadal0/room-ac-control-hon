"""Launch the source or portable Windows application."""

import argparse
import ctypes
import json
import tkinter as tk
from pathlib import Path

from . import __version__
from .dashboard import App


def check(condition):
    """Self-test check that still runs when Python optimizations strip asserts."""
    if not condition:
        raise RuntimeError("Self-test check failed")


def self_test(output):
    """Check the frozen runtime without loading an account or contacting hOn."""
    root = None
    app = None
    try:
        from .secure_state import protect

        root = tk.Tk()
        root.withdraw()
        app = App(root, demo=True, enable_tray=False, language="en", theme="light")
        root.update_idletasks()
        encrypted = protect(b"offline-package-check")
        check(protect(encrypted, decrypt=True) == b"offline-package-check")
        check(app.unit_image.width() > 200)
        app.login_view.set_loading(True)
        root.update_idletasks()
        check(app.login_view.animation.active and app.login_view.animation.job is not None)
        app.login_view.set_loading(False)
        check(app.login_view.animation.job is None)
        from .demo import devices

        app.connected(devices())
        root.update_idletasks()
        check(set(app.inline_timers.cards) == {"off"} and app.settings_button.winfo_exists())
        from .temperature_wheel import TemperatureWheel

        wheel = TemperatureWheel(root, {"min": 16, "max": 30, "step": 0.5}, 23.5)
        check(wheel.get() == "23.5")
        wheel.step(1)
        check(wheel.get() == "24")
        app.set_language("pt-PT")
        check(app.all_button.label() == "Todas as funções")
        check(app.i18n.number("23.5") == "23,5")
        check(wheel.get() == "24")
        app.set_language("en")
        check(app.all_button.label() == "All functions")
        from .theme import C

        app.theme_preference = "dark"
        check(app.apply_theme() and C.mode == "dark" and app.canvas.cget("bg") == C.BG)
        app.theme_preference = "light"
        check(app.apply_theme() and C.mode == "light")
        wheel.destroy()
        from .cloud_timers import select_timers

        timers, _ = select_timers({"scheduledPrograms": [], "scheduleRunningProgramEnd": []})
        check(all(value["due"] is None for value in timers.values()))
        # The self-test starts no tray icon and connects to nothing, so check that the
        # libraries for both are in this build: pystray picks its Windows backend on import.
        import pystray
        from awsiot import mqtt5_client_builder

        check(pystray.Icon.__module__ == "pystray._win32")
        check(callable(mqtt5_client_builder.websockets_with_custom_authorizer))
        # The updater's signature check must work in this build before it may replace another.
        from awscrt.crypto import RSA

        from . import updates

        check(RSA.new_public_key_from_pem_data(updates.PUBLIC_KEY) is not None)
        try:
            updates.read_manifest(b'{"schema": 1}', b"not-a-signature")
            check(False)
        except updates.UpdateError:
            pass
        result = {
            "ok": True,
            "version": __version__,
            "updates": True,
            "assets": True,
            "encryption": True,
            "tray": True,
            "mqtt": True,
            "timers": True,
            "login_animation": True,
            "temperature_wheel": True,
            "multilingual": True,
            "themes": True,
        }
    except Exception as error:
        result = {"ok": False, "error": type(error).__name__}
    finally:
        if app:
            app.close()
        elif root:
            root.destroy()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Room AC Control for hOn")
    parser.add_argument("--preview", choices=["login", "dashboard"], help="Open an offline design preview")
    parser.add_argument("--self-test", metavar="JSON_FILE", help="Write an offline runtime check report")
    parser.add_argument(
        "--language", choices=["system", "en", "pt-PT"], help="Choose the interface language for this launch"
    )
    parser.add_argument("--theme", choices=["system", "light", "dark"], help="Choose the appearance for this launch")
    args = parser.parse_args(argv)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RoomACControl.Desktop")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    if args.self_test:
        raise SystemExit(self_test(args.self_test))
    instance = None
    if not args.preview:
        # A second start shows the running app instead of opening another copy.
        from .single_instance import SingleInstance

        instance = SingleInstance()
        if not instance.first:
            instance.show_running()
            instance.close()
            return
    root = tk.Tk()
    app = App(root, demo=bool(args.preview), language=args.language, theme=args.theme)
    app.instance = instance
    if args.preview:
        root.title("Room AC Control for hOn · Offline preview")
        if args.preview == "dashboard":
            from .demo import devices

            app.connected(devices())
        app.status.set("Offline preview · No AC commands are sent.")
    root.mainloop()


if __name__ == "__main__":
    main()
