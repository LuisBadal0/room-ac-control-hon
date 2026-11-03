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
    settle(root, lambda: root.winfo_width() > 1)
    # The preview never checks: no badge, and the window says so.
    assert not app.updater.supported and not app.update_button.winfo_ismapped()
    app.open_functions()
    root.update()
    footer = {child.cget("text"): child for child in app.functions_view.footer.winfo_children() if child.winfo_class() == "TButton"}
    footer["Updates"].invoke()
    view = app.updates_view
    settle(root, lambda: float(view.window.attributes("-alpha")) == 1.0)
    texts = [view.card.itemcget(item, "text") for item in view.card.find_all() if view.card.type(item) == "text"]
    assert "Updates are off in the preview" in texts, texts
    assert view.primary.instate(["disabled"]) and view.toggle.instate(["disabled"])
    view.close()
    root.update()
    assert app.updates_view is None
    assert app.functions_view.window.grab_current() is not None  # All functions keeps its grab.
    app.functions_view.close()

    # A portable install: a check finds a signed release and shows the badge.
    location = Path(temporary.name) / "runtime" / "RoomACControl"
    location.mkdir(parents=True)
    app.updater = updates.Updater("0.1.23", location)
    app.updater.listen(app.updates_changed)
    app.open_updates()
    view = app.updates_view
    assert view.primary.cget("text") == "Check now" and not view.notes.winfo_ismapped()
    with patch.object(updates, "check", return_value=dict(RELEASE)):
        view.primary.invoke()
        settle(root, lambda: app.updater.state == "available")
    assert app.update_button.winfo_ismapped()
    assert app.update_button.winfo_rootx() < app.theme_button.winfo_rootx()  # Left of Appearance.
    assert view.primary.cget("text") == "Update" and view.notes.winfo_ismapped()
    texts = [view.card.itemcget(item, "text") for item in view.card.find_all() if view.card.type(item) == "text"]
    assert "Version 9.9.9 is available." in texts, texts

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
    def fake_download(release, folder, progress, cancelled):
        progress(1, 2)
        archive = Path(temporary.name) / "u.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(updates.ZIP_RUNTIME + "RoomACControl.exe", b"exe")
        return archive
    with patch.object(updates, "updates_folder", return_value=Path(temporary.name) / "updates"), \
            patch.object(updates, "download", side_effect=fake_download), \
            patch.object(updates, "self_test"), \
            patch.object(updates, "launch_helper") as helper:
        view.primary.invoke()
        settle(root, lambda: app.closing)
    helper.assert_called_once_with(location, "9.9.9")
    assert (updates.staged(location) / "RoomACControl.exe").exists()
    print("Updates window, preview lock, check, header badge, Portuguese, automatic-check setting and update hand-over passed offline.")
finally:
    temporary.cleanup()
    if not app.closing:
        app.close()
