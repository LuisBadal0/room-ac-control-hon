"""Updates window and header badge, offline: no network request, no helper,
no real install. Fixture runtimes live in a temporary folder."""
import json
import sys
import tempfile
import time
import tkinter as tk
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control import updates
from room_ac_control.smooth import texts as canvas_texts
from room_ac_control.dashboard import App
from room_ac_control.demo import devices

RELEASE = {"version": "9.9.9", "tag": "v9.9.9", "archive": "Room-AC-Control-for-hOn-9.9.9-Windows-x64.zip",
           "sha256": "0"*64, "size": 1, "url": "https://example.test/u.zip", "notes": "https://example.test/notes"}


def settle(root, until, seconds=10):
    deadline = time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        root.update()
        root.after(20)
    assert until(), "timed out"


root = tk.Tk()
app = App(root, demo=True, enable_tray=False, language="en", theme="light")
temporary = tempfile.TemporaryDirectory()
try:
    app.connected(devices())
    settle(root, lambda: float(root.attributes("-alpha")) == 1.0 and app.settings_button.winfo_ismapped())
    # One Settings button in the header; the preview never checks, so no dot.
    assert app.settings_button.winfo_ismapped() and not app.settings_button.badge
    app.settings_button.event_generate("<Button-1>")
    root.update()
    panel = app.settings_panel
    actions = lambda: [action for box, action in panel.regions]
    # The dropdown opens inside the main window, under the button, over a dimmed page.
    assert app.settings_button.pressed and panel.canvas.winfo_ismapped() and panel.canvas.master is root
    assert panel.canvas.winfo_rootx() + panel.canvas.winfo_width() <= root.winfo_rootx() + root.winfo_width()
    texts = panel.texts()
    assert "Updates are off in the preview" in texts and "Check now" in texts, texts
    assert panel.primary not in actions() and panel.toggle_automatic not in actions()  # Shown, but not clickable.
    assert "Sign out" in texts and panel.logout not in actions()  # The preview has no account to sign out of.
    # The version line opens the Updates window, which keeps What's new and Diagnostics.
    app.open_updates()
    view = app.updates_view
    settle(root, lambda: float(view.window.attributes("-alpha")) == 1.0)
    texts = [text for item, text in canvas_texts(view.card)]
    assert "Updates are off in the preview" in texts, texts
    assert view.primary.instate(["disabled"]) and view.toggle.instate(["disabled"])
    buttons = [child.cget("text") for child in view.primary.master.winfo_children() if child.winfo_class() == "TButton"]
    assert "Diagnostics" in buttons and "Close" in buttons, buttons
    view.close()
    app.settings_button.event_generate("<Button-1>")  # The button toggles the dropdown closed.
    root.update()
    assert app.updates_view is None and app.settings_panel is None and not app.settings_button.pressed

    # A portable install: Check now in Settings finds a signed release and shows the badge.
    location = Path(temporary.name) / "runtime" / "RoomACControl"
    location.mkdir(parents=True)
    app.updater = updates.Updater("0.1.23", location)
    app.updater.listen(app.updates_changed)
    app.open_settings()
    panel = app.settings_panel
    assert "Check now" in panel.texts() and panel.primary in actions()
    with patch.object(updates, "check", return_value=dict(RELEASE)):
        panel.primary()
        assert "Checking for updates…" in panel.texts()
        settle(root, lambda: app.updater.state == "available")
    assert app.settings_button.badge  # The dot marks a waiting update.
    texts = panel.texts()
    assert "Update" in texts and "Version 9.9.9 is available." in texts, texts
    bar = app.update_notice_bar
    root.update()
    assert bar.frame.winfo_ismapped() and bar.label.cget("text") == "Version 9.9.9 is available."
    assert bar.button.winfo_ismapped() and not bar.bar.winfo_ismapped()
    # The automatic-check switch is saved.
    panel.toggle_automatic()
    assert app.updater.enabled is False and app.storage.auto_update() is False
    panel.toggle_automatic()
    assert app.updater.enabled is True
    panel.close()
    app.open_updates()
    view = app.updates_view
    settle(root, lambda: float(view.window.attributes("-alpha")) == 1.0)
    assert view.primary.cget("text") == "Update" and view.notes.winfo_ismapped()

    # Portuguese, live.
    app.set_language("pt-PT")
    root.update()
    assert view.primary.cget("text") == "Atualizar", view.primary.cget("text")
    app.set_language("en")

    # Turning automatic checks off is saved.
    view.toggle.invoke()
    assert app.updater.enabled is False and app.storage.auto_update() is False
    view.toggle.invoke()
    assert app.updater.enabled is True

    # Update: download, unpack and self-test (faked), then hand over and close.
    # The bar above the bottom row shows the progress until the app restarts.
    import threading
    halfway, carry_on = threading.Event(), threading.Event()
    def fake_download(release, folder, progress, cancelled):
        progress(1, 2)
        halfway.set()
        carry_on.wait(10)
        archive = Path(temporary.name) / "u.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(updates.ZIP_RUNTIME + "RoomACControl.exe", b"exe")
        return archive
    with patch.object(updates, "updates_folder", return_value=Path(temporary.name) / "updates"), \
            patch.object(updates, "download", side_effect=fake_download), \
            patch.object(updates, "self_test"), \
            patch.object(updates, "launch_helper") as helper:
        view.primary.invoke()
        settle(root, lambda: halfway.is_set() and app.updater.progress == .5)
        root.update()
        assert bar.frame.winfo_ismapped() and bar.label.cget("text") == "Downloading version 9.9.9… 50%", bar.label.cget("text")
        assert bar.bar.winfo_ismapped() and not bar.button.winfo_ismapped() and not bar.close.winfo_ismapped()
        carry_on.set()
        settle(root, lambda: app.updater.state == "ready")
        assert bar.label.cget("text") == "Restarting to finish the update…" and bar.frame.winfo_ismapped()
        settle(root, lambda: app.closing)
    helper.assert_called_once_with(location, "9.9.9")
    assert (updates.staged(location) / "RoomACControl.exe").exists()
    print("Settings panel and Updates window, preview lock, check, header badge, update progress bar, Portuguese, automatic-check setting and update hand-over passed offline.")
finally:
    temporary.cleanup()
    if not app.closing:
        app.close()
