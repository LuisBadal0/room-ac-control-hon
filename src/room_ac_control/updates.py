"""Signed in-app updates for the portable and the installed Windows app.

CI signs a small manifest (version, file names, SHA-256 and sizes) with the
project's own RSA key. The app accepts an update only when that signature
checks out against the public key built into it, the version is newer, and the
downloaded file matches the signed hash and size.

A portable copy unpacks the new version next to the current one, which must
pass its own self-test. Only then, after the person clicks Update, a small
helper swaps the folders once the app has closed, starts the new version, and
puts the old one back if the swap fails.

A copy installed with Setup.exe or the MSI updates with the same kind of
installer, so Windows' Installed apps list, upgrades and uninstall stay right.
The app inside the downloaded installer is unpacked to a scratch folder and
must pass the same self-test first; after the app closes, a helper runs the
installer silently (Windows Installer rolls back on failure) and starts the
new version.
"""

import queue
import shutil
import threading
from datetime import datetime

from .diagnostics import diagnostics
from .update_install import (
    HELPER,
    INSTALLER_HELPER,
    WindowsRegistry,
    check_msi,
    find_runtime,
    finish,
    install_location,
    installed_by,
    installer_scratch,
    launch_helper,
    launch_installer_helper,
    previous,
    run_installer_step,
    same_folder,
    staged,
    updates_folder,
    writable,
)
from .update_progress import launch_progress
from .update_release import (
    BUNDLE_UPGRADE_CODE,
    CHECK_EVERY_MS,
    EXECUTABLE,
    FIRST_CHECK_MS,
    INSTALL_KEY,
    INSTALLERS,
    MANIFEST_URL,
    MAX_ARCHIVE,
    MAX_INSTALLER,
    MAX_MANIFEST,
    MAX_SIGNATURE,
    MAX_UNPACKED,
    NO_WINDOW,
    PUBLIC_KEY,
    REPOSITORY,
    SIGNATURE_URL,
    UNINSTALL_KEY,
    VERSION,
    ZIP_RUNTIME,
    HttpsOnly,
    UpdateError,
    check,
    download,
    download_file,
    download_url,
    extract_runtime,
    fetch,
    installer_name,
    is_newer,
    local_step,
    open_url,
    parse_version,
    read_manifest,
    self_test,
    signed_installers,
    verify_signature,
)

# The helpers live in update_release and update_install; `updates.<name>` keeps working for
# callers and tests, and patching it here changes what the Updater uses.
__all__ = [
    "Updater",
    "BUNDLE_UPGRADE_CODE",
    "CHECK_EVERY_MS",
    "EXECUTABLE",
    "FIRST_CHECK_MS",
    "HELPER",
    "HttpsOnly",
    "INSTALLERS",
    "INSTALLER_HELPER",
    "INSTALL_KEY",
    "MANIFEST_URL",
    "MAX_ARCHIVE",
    "MAX_INSTALLER",
    "MAX_MANIFEST",
    "MAX_SIGNATURE",
    "MAX_UNPACKED",
    "NO_WINDOW",
    "PUBLIC_KEY",
    "REPOSITORY",
    "SIGNATURE_URL",
    "UNINSTALL_KEY",
    "UpdateError",
    "VERSION",
    "WindowsRegistry",
    "ZIP_RUNTIME",
    "check",
    "check_msi",
    "download",
    "download_file",
    "download_url",
    "extract_runtime",
    "fetch",
    "find_runtime",
    "finish",
    "install_location",
    "installed_by",
    "installer_name",
    "installer_scratch",
    "is_newer",
    "launch_helper",
    "launch_installer_helper",
    "launch_progress",
    "local_step",
    "open_url",
    "parse_version",
    "previous",
    "read_manifest",
    "run_installer_step",
    "same_folder",
    "self_test",
    "signed_installers",
    "staged",
    "updates_folder",
    "verify_signature",
    "writable",
]


class Updater:
    """Update state for the UI. Network and disk work runs on a background
    thread; `poll()` applies results on the Tk thread and notifies listeners."""

    def __init__(self, current, location, enabled=True, demo=False, registry=None):
        self.current, self.location, self.demo = current, location, demo
        # "setup" or "msi" for a copy Windows installed, None for a portable one.
        self.installed = None if demo else installed_by(location, registry)
        self.installer = None  # The verified installer `apply` runs, once ready.
        self.enabled = enabled
        self.state = "idle"  # idle, checking, current, available, downloading, verifying, ready, failed
        self.release = None
        self.progress = 0.0
        self.error = None
        self.listeners = []
        self.events: queue.Queue[tuple] = queue.Queue()
        self.thread = None
        self.cancel = threading.Event()
        self.applied = False
        self.quiet = False
        self.checked = None  # When a check last finished, for "Last checked today at 09:12".

    @property
    def supported(self):
        return self.location is not None and not self.demo

    @property
    def busy(self):
        return self.state in {"checking", "downloading", "verifying"}

    def listen(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback) if callback in self.listeners else None

    def notify(self):
        for callback in list(self.listeners):
            callback()

    def run(self, work):
        def target():
            try:
                self.events.put(("done", work()))
            except UpdateError as error:
                self.events.put(("failed", str(error)))
            except Exception as error:
                diagnostics.record("update_failed", error)
                self.events.put(
                    ("failed", "Could not reach the update service. Check your internet connection and try again.")
                )

        self.thread = threading.Thread(target=target, name="room-ac-update", daemon=True)
        self.thread.start()

    def check(self, quiet=False):
        if not self.supported or self.busy or self.state == "ready":
            return False
        self.state, self.error, self.quiet = "checking", None, quiet
        self.notify()
        self.run(lambda: ("checked", check(self.current)))
        return True

    def installer_plan(self, release):
        """Files to download for an installed copy: the signed MSI, which is self-tested,
        plus Setup.exe for a Setup.exe install. None means a folder swap from the ZIP."""
        installers = release.get("installers") or {}
        if self.installed not in INSTALLERS or "msi" not in installers or self.installed not in installers:
            return None
        return [installers["msi"]] + ([installers["setup"]] if self.installed == "setup" else [])

    def install(self):
        """Download, verify, unpack and self-test; the swap or installer waits for `apply`."""
        if not self.supported or self.busy or not self.release:
            return False
        if not writable(self.location):
            self.state, self.error = (
                "failed",
                "Room AC Control cannot write to its folder. Move it to a folder you own, or download the update from the releases page.",
            )
            self.notify()
            return False
        release, location = self.release, self.location
        plan, kind = self.installer_plan(release), self.installed
        self.state, self.error, self.progress, self.installer = "downloading", None, 0.0, None
        self.cancel.clear()
        self.notify()

        def work_installer():
            folder = updates_folder()
            total, base, files = sum(item["size"] for item in plan), 0, []
            try:
                for item in plan:
                    files.append(
                        download_file(
                            item,
                            folder,
                            lambda done, _total, base=base: self.events.put(("progress", (base + done) / total)),
                            self.cancel.is_set,
                        )
                    )
                    base += item["size"]
                self.events.put(("verifying", None))
                check_msi(files[0], release["version"])
            except BaseException:
                for path in files:
                    path.unlink(missing_ok=True)
                raise
            if kind == "setup":
                files[0].unlink(missing_ok=True)  # Only needed for the check; Setup.exe embeds it.
            return ("installed", files[-1])

        def work():
            folder = updates_folder()
            archive = download(
                release, folder, lambda done, total: self.events.put(("progress", done / total)), self.cancel.is_set
            )
            self.events.put(("verifying", None))
            try:
                with local_step():
                    extract_runtime(archive, staged(location))
                self_test(staged(location), release["version"])
            except BaseException:
                shutil.rmtree(staged(location), ignore_errors=True)
                raise
            finally:
                archive.unlink(missing_ok=True)
            return ("installed", None)

        self.run(work_installer if plan else work)
        return True

    def apply(self, progress=None):
        """Hand over to the helper; the caller closes the app straight after.

        `progress` is (texts, colors, icon) for the window that shows the update
        while the app is closed; see `launch_progress`."""
        if self.state != "ready" or self.applied or self.release is None:
            return False
        version = self.release["version"]
        if self.installer:
            helper = launch_installer_helper(self.location, self.installed, self.installer, version)
        else:
            helper = launch_helper(self.location, version)
        self.applied = True
        if progress is not None:
            texts, colors, icon = progress
            try:
                launch_progress(version, getattr(helper, "pid", 0), texts, colors, icon=icon)
            except OSError as error:
                # Only the window is missing; the update itself goes ahead.
                diagnostics.record("update_progress_failed", error)
        return True

    def close(self):
        self.cancel.set()

    def poll(self):
        changed = False
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "progress":
                self.progress = value
            elif kind == "verifying":
                self.state = "verifying"
            elif kind == "failed":
                quiet = self.state == "checking" and self.quiet
                self.state, self.error = ("idle", None) if quiet else ("failed", value)
            elif kind == "done":
                result, payload = value
                if result == "checked":
                    self.release = payload
                    self.state = "available" if payload else "current"
                    self.checked = datetime.now()
                elif result == "installed":
                    self.state, self.installer = "ready", payload
        if changed:
            self.notify()
        return changed
