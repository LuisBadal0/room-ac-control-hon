"""Live light/dark/Follow Windows switching with fictional rooms and no AC commands."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.demo import devices
from room_ac_control.secure_state import SecureState
from room_ac_control.theme import C, PALETTES

OPTIONS = ("background", "foreground", "highlightbackground", "insertbackground", "activebackground",
           "disabledbackground", "selectbackground")


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def stale_colours(root, previous):
    """Colours that only the previous palette uses must not survive a switch."""
    current = {value.lower() for value in PALETTES[C.mode].values()}
    stale = {value.lower() for value in PALETTES[previous].values()} - current
    found = []
    for widget in [root, *descendants(root)]:
        if not widget.winfo_exists():
            continue
        for option in OPTIONS:
            try:
                value = str(widget.cget(option)).lower()
            except tk.TclError:
                continue
            if value in stale:
                found.append((str(widget), option, value))
        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                for option in ("fill", "outline"):
                    try:
                        value = str(widget.itemcget(item, option)).lower()
                    except tk.TclError:
                        continue
                    if value in stale:
                        found.append((str(widget), widget.type(item), option, value))
    return found


with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "state.dpapi"
    root = tk.Tk()
    app = App(root, demo=True, state=SecureState(path), enable_tray=False, language="en", theme="light")
    submissions = []
    app.worker.submit = lambda coroutine, *args, **kwargs: (coroutine.close(), submissions.append(args))
    try:
        assert C.mode == "light" and root.cget("bg") == C.BG
        app.connected(devices())
        app.staged("tempSel", "21")
        app.open_functions()
        view = app.functions_view
        view.change_setting("windSpeed", "3")
        root.update()
        drafts = (dict(app.dirty), dict(view.settings_changes))

        app.theme_menu(view.window)
        assert [tile for tile in app.theme_panel.tiles] and len(app.theme_panel.tiles) == 3
        app.theme_panel.choose("dark")
        root.update()
        assert C.mode == "dark" and app.theme_preference == "dark"
        assert SecureState(path).theme() == "dark"
        assert view.window.winfo_exists() and (dict(app.dirty), dict(view.settings_changes)) == drafts
        assert app.canvas.cget("bg") == C.BG and app.status_label.cget("bg") == C.SOFT
        assert view.search_entry.cget("bg") == C.CARD and view.hero.cget("bg") == C.BG
        assert ttk.Style(root).lookup("TFrame", "background") == C.BG
        assert ttk.Style(root).lookup("Accent.TButton", "foreground") == C.ON_BRAND
        leftovers = stale_colours(root, "light")
        assert not leftovers, leftovers[:10]

        # Follow Windows reads the app mode now and notices a later change from the poll loop.
        with patch("room_ac_control.theme.windows_mode", return_value="light"):
            app.set_theme("system")
            assert C.mode == "light" and SecureState(path).theme() == "system"
            root.update()
            leftovers = stale_colours(root, "dark")
            assert not leftovers, leftovers[:10]
        with patch("room_ac_control.theme.windows_mode", return_value="dark"):
            app.theme_checks = 19
            app.poll()
            root.update()
            assert C.mode == "dark"
        # An explicit choice is never overridden by Windows.
        with patch("room_ac_control.theme.windows_mode", return_value="light"):
            app.set_theme("dark")
            app.theme_checks = 19
            app.poll()
            assert C.mode == "dark"

        # Language switching still works in the dark palette, with drafts intact.
        app.set_language("pt-PT")
        root.update()
        assert app.apply_button.cget("text") == "Aplicar alterações (1)"
        assert view.window.winfo_exists() and (dict(app.dirty), dict(view.settings_changes)) == drafts
        app.set_language("en")
        view.close()
        assert not submissions  # Theme changes never contact the cloud or send AC commands.
        print("Live light/dark switching, no stale colours, saved preference, Follow Windows polling and kept drafts passed offline.")
    finally:
        app.close()
