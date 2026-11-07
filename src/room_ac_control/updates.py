"""Signed in-place updates for the portable Windows app.

CI signs a small manifest (version, archive name, SHA-256 and size) with the
project's own RSA key. The app accepts an update only when that signature
checks out against the public key built into it, the version is newer, and the
downloaded ZIP matches the signed hash and size. The new version is unpacked
next to the current one and must pass its own self-test. Only then, after the
person clicks Update, a small helper swaps the folders once the app has
closed, starts the new version, and puts the old one back if the swap fails.
"""
import hashlib
import json
import os
import queue
from datetime import datetime
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .diagnostics import diagnostics

REPOSITORY = "LuisBadal0/room-ac-control-hon"
MANIFEST_URL = f"https://github.com/{REPOSITORY}/releases/latest/download/update.json"
SIGNATURE_URL = MANIFEST_URL + ".sig"
EXECUTABLE = "RoomACControl.exe"
ZIP_RUNTIME = "Room AC Control/runtime/RoomACControl/"
MAX_MANIFEST = 16 * 1024
MAX_SIGNATURE = 4096
MAX_ARCHIVE = 400 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
CHECK_EVERY_MS = 24 * 60 * 60 * 1000
FIRST_CHECK_MS = 20 * 1000

# The matching private key is held only as the UPDATE_SIGNING_KEY secret in CI
# (packaging/update-signing-key.pub is the same key, for the release workflow).
PUBLIC_KEY = b"""-----BEGIN RSA PUBLIC KEY-----
MIIBigKCAYEArk9pJ2YW7Vsg30XWNkMoX+4WdNmzf29XJtsg3LrX5uT0gU2LV0Ef
UBMyyBUj5rmcJflTbnCyFbVfgwOsKelCfeonINm6kmeLEUoMJ6QVwWsbbpeRAwjI
8Hm+2UStXE2QnaL2ktccvvT0vwqmEdEk3RPaG/oVX//fvrtPUZut14j7YOyvc4DX
ZRbCFUvGp4gyZwXRCJY4ELbfLBlXSodO0t7JEYN043BdLn6Ue7o8cXJj2YXRERtO
LoGMkRF5Ezkk/+U/XTo34CnFxfsHxTFrsQzKNFAqNyBUg4acrtplzGNhvziBzKFf
0h+2z8PIcDJKLID7aqrk1krOCId43+fAym5yh7GhlWc4xf0fAMh4rleT2kRBhcRv
Ndz34jlaHsgDAOWhas432b7NfSfDvrTgp5ywuBBl2+Qp1Fe+z6Hakb3Wrqrk1cpW
LD5/uU8JkMciKvQbxz5C3AP18PUGxqQn4915oxJCqu6gOR7UHGySkf3l2ffEVHMn
IOrVxbYpqqELAgMBAAE=
-----END RSA PUBLIC KEY-----
"""

VERSION = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})$")


class UpdateError(Exception):
    """A user-facing reason the update stopped; the installed app is unchanged."""


def parse_version(text):
    match = VERSION.match(text) if isinstance(text, str) else None
    if not match:
        raise UpdateError("The update information is not valid.")
    return tuple(int(part) for part in match.groups())


def verify_signature(data, signature, public_key=PUBLIC_KEY):
    """RSA-PSS SHA-256, checked with awscrt, which the app already ships for MQTT."""
    from awscrt.crypto import RSA, RSASignatureAlgorithm
    try:
        key = RSA.new_public_key_from_pem_data(public_key)
        valid = key.verify(RSASignatureAlgorithm.PSS_SHA256, hashlib.sha256(data).digest(), signature)
    except (ValueError, RuntimeError):
        valid = False
    if not valid:
        raise UpdateError("The update is not signed by Room AC Control. It was not installed.")


def read_manifest(data, signature, public_key=PUBLIC_KEY):
    """Verify, then validate every field; nothing unsigned is ever parsed."""
    verify_signature(data, signature, public_key)
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise UpdateError("The update information is not valid.") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise UpdateError("This update needs a newer Room AC Control. Download it from the releases page.")
    version = manifest.get("version")
    parse_version(version)
    archive, digest, size = manifest.get("archive"), manifest.get("sha256"), manifest.get("size")
    if (manifest.get("tag") != f"v{version}"
            or archive != f"Room-AC-Control-for-hOn-{version}-Windows-x64.zip"
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_ARCHIVE):
        raise UpdateError("The update information is not valid.")
    return {"version": version, "tag": manifest["tag"], "archive": archive, "sha256": digest, "size": size,
            "url": f"https://github.com/{REPOSITORY}/releases/download/{manifest['tag']}/{archive}",
            "notes": f"https://github.com/{REPOSITORY}/releases/tag/{manifest['tag']}"}


def is_newer(release, current):
    return parse_version(release["version"]) > parse_version(current)


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if not url.lower().startswith("https://"):
            raise UpdateError("The update download was redirected to an insecure address.")
        return super().redirect_request(request, fp, code, message, headers, url)


_opener = urllib.request.build_opener(HttpsOnly)


def open_url(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "RoomACControl-Updater"})
    return _opener.open(request, timeout=timeout)


def fetch(url, limit, opener=open_url):
    with opener(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("The update information is not valid.")
    return data


def check(current, opener=open_url, public_key=PUBLIC_KEY):
    """Return the signed release if it is newer than `current`, else None."""
    data = fetch(MANIFEST_URL, MAX_MANIFEST, opener)
    signature = fetch(SIGNATURE_URL, MAX_SIGNATURE, opener)
    release = read_manifest(data, signature, public_key)
    return release if is_newer(release, current) else None


def download(release, folder, progress=lambda done, total: None, cancelled=lambda: False, opener=open_url):
    """Stream the ZIP to disk, enforcing the signed size and SHA-256."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / release["archive"]
    partial = target.with_name(target.name + ".part")
    digest, done = hashlib.sha256(), 0
    try:
        with opener(release["url"], timeout=60) as response, partial.open("wb") as handle:
            while True:
                if cancelled():
                    raise UpdateError("The update was cancelled.")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > release["size"]:
                    raise UpdateError("The downloaded update does not match its signature. It was not installed.")
                digest.update(chunk)
                handle.write(chunk)
                progress(done, release["size"])
        if done != release["size"] or digest.hexdigest() != release["sha256"]:
            raise UpdateError("The downloaded update does not match its signature. It was not installed.")
        os.replace(partial, target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def extract_runtime(archive, target):
    """Unpack only runtime/RoomACControl from the release ZIP into `target`."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    unpacked = 0
    with zipfile.ZipFile(archive) as bundle:
        members = [info for info in bundle.infolist() if info.filename.startswith(ZIP_RUNTIME)]
        for info in members:
            relative = PurePosixPath(info.filename[len(ZIP_RUNTIME):])
            mode = (info.external_attr >> 16) & 0o170000
            if (not relative.parts or relative.is_absolute() or ".." in relative.parts
                    or any(":" in part or "\\" in part for part in relative.parts) or mode == 0o120000):
                raise UpdateError("The update contains unsafe file names. It was not installed.")
            unpacked += info.file_size
            if unpacked > MAX_UNPACKED:
                raise UpdateError("The update is larger than expected. It was not installed.")
            destination = target.joinpath(*relative.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, destination.open("wb") as handle:
                shutil.copyfileobj(source, handle, 1024 * 1024)
    if not (target / EXECUTABLE).is_file():
        raise UpdateError("The update is incomplete. It was not installed.")


def self_test(runtime, version, run=subprocess.run):
    """The new version must start, pass its offline checks and report its version."""
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "self-test.json"
        try:
            result = run([str(runtime / EXECUTABLE), "--self-test", str(report)], timeout=120,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            outcome = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            outcome, result = {}, None
    if not (result is not None and result.returncode == 0 and outcome.get("ok") is True
            and outcome.get("version") == version and outcome.get("updates") is True):
        raise UpdateError("The new version did not pass its checks. Nothing was changed.")


def updates_folder():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RoomACControl" / "updates"


def install_location(executable=None, frozen=None):
    """The runtime folder this portable app runs from, or None for a source checkout."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return None
    folder = Path(executable or sys.executable).resolve().parent
    if folder.name != "RoomACControl" or folder.parent.name != "runtime" or not (folder / EXECUTABLE).is_file():
        return None
    return folder


def writable(folder):
    try:
        with tempfile.NamedTemporaryFile(dir=folder.parent, prefix=".write-check-"):
            return True
    except OSError:
        return False


def staged(location):
    return location.with_name(location.name + ".new")


def previous(location):
    return location.with_name(location.name + ".old")


# The helper is static ASCII; paths reach it only through environment
# variables, so spaces, accents and symbols in folder names are safe.
HELPER = r"""@echo off
setlocal DisableDelayedExpansion
if not defined UPDATE_TRIES set UPDATE_TRIES=15
set /a WAITED=0
:wait
tasklist /FI "PID eq %UPDATE_PID%" /NH 2>nul | find " %UPDATE_PID% " >nul
if not errorlevel 1 (
    if %WAITED% geq 120 goto gave_up
    set /a WAITED+=1
    ping -n 2 127.0.0.1 >nul
    goto wait
)
if exist "%UPDATE_OLD%" rmdir /s /q "%UPDATE_OLD%"
set /a TRIES=0
:swap
move "%UPDATE_CURRENT%" "%UPDATE_OLD%" >nul 2>&1
if not errorlevel 1 goto place
if %TRIES% geq %UPDATE_TRIES% goto failed
set /a TRIES+=1
ping -n 2 127.0.0.1 >nul
goto swap
:place
move "%UPDATE_STAGED%" "%UPDATE_CURRENT%" >nul 2>&1
if not errorlevel 1 goto done
move "%UPDATE_OLD%" "%UPDATE_CURRENT%" >nul 2>&1
goto failed
:done
> "%UPDATE_RESULT%" echo {"ok": true, "version": "%UPDATE_VERSION%"}
if not "%UPDATE_LAUNCH%"=="0" start "" "%UPDATE_CURRENT%\RoomACControl.exe"
exit /b 0
:failed
> "%UPDATE_RESULT%" echo {"ok": false, "version": "%UPDATE_VERSION%", "reason": "busy"}
if not "%UPDATE_LAUNCH%"=="0" start "" "%UPDATE_CURRENT%\RoomACControl.exe"
exit /b 1
:gave_up
> "%UPDATE_RESULT%" echo {"ok": false, "version": "%UPDATE_VERSION%", "reason": "timeout"}
exit /b 1
"""


def launch_helper(location, version, folder=None, pid=None, popen=subprocess.Popen, extra=None):
    """Start the swap helper; it waits for this process to exit before acting.

    `extra` adds environment settings for tests (UPDATE_LAUNCH=0, UPDATE_TRIES)."""
    folder = folder or updates_folder()
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "apply-update.cmd"
    script.write_text(HELPER.replace("\n", "\r\n"), encoding="ascii", newline="")
    (folder / "result.json").unlink(missing_ok=True)
    environment = {**os.environ, "UPDATE_PID": str(pid or os.getpid()), "UPDATE_CURRENT": str(location),
                   "UPDATE_STAGED": str(staged(location)), "UPDATE_OLD": str(previous(location)),
                   "UPDATE_RESULT": str(folder / "result.json"), "UPDATE_VERSION": version, **(extra or {})}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    comspec = os.environ.get("ComSpec", "cmd.exe")
    # Use a relative path with a dot prefix: cmd then finds the script even when NoDefaultCurrentDirectoryInExePath is set.
    return popen([comspec, "/d", "/c", ".\\" + script.name], cwd=str(folder), env=environment,
                 creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def finish(location, current, folder=None):
    """After a start: report the last update's outcome and tidy up its files."""
    folder = folder or updates_folder()
    message = None
    result = folder / "result.json"
    try:
        outcome = json.loads(result.read_text(encoding="utf-8"))
        if outcome.get("ok") and outcome.get("version") == current:
            message = "Updated to version {version}.".format(version=current)
        elif outcome.get("reason") == "busy":
            # Windows would not move the app folder: another copy or window still had it open.
            message = ("The update could not be installed because the app folder was in use. Close every "
                       "Room AC Control window, including the one in the notification area, then try again.")
        else:
            message = "The update could not be installed. Room AC Control is still on version {version}.".format(version=current)
    except (OSError, ValueError, AttributeError):
        pass
    result.unlink(missing_ok=True)
    if location is not None:
        for leftover in (previous(location), staged(location)):
            shutil.rmtree(leftover, ignore_errors=True)
    if folder.exists():
        for download in folder.glob("Room-AC-Control-for-hOn-*.zip*"):
            download.unlink(missing_ok=True)
    return message


class Updater:
    """Update state for the UI. Network and disk work runs on a background
    thread; `poll()` applies results on the Tk thread and notifies listeners."""

    def __init__(self, current, location, enabled=True, demo=False):
        self.current, self.location, self.demo = current, location, demo
        self.enabled = enabled
        self.state = "idle"  # idle, checking, current, available, downloading, verifying, ready, failed
        self.release = None
        self.progress = 0.0
        self.error = None
        self.listeners = []
        self.events = queue.Queue()
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
                self.events.put(("failed", "Could not reach the update service. Check your internet connection and try again."))
        self.thread = threading.Thread(target=target, name="room-ac-update", daemon=True)
        self.thread.start()

    def check(self, quiet=False):
        if not self.supported or self.busy or self.state == "ready":
            return False
        self.state, self.error, self.quiet = "checking", None, quiet
        self.notify()
        self.run(lambda: ("checked", check(self.current)))
        return True

    def install(self):
        """Download, verify, unpack and self-test; the swap waits for `apply`."""
        if not self.supported or self.busy or not self.release:
            return False
        if not writable(self.location):
            self.state, self.error = "failed", "Room AC Control cannot write to its folder. Move it to a folder you own, or download the update from the releases page."
            self.notify()
            return False
        release, location = self.release, self.location
        self.state, self.error, self.progress = "downloading", None, 0.0
        self.cancel.clear()
        self.notify()

        def work():
            folder = updates_folder()
            archive = download(release, folder, lambda done, total: self.events.put(("progress", done / total)),
                               self.cancel.is_set)
            self.events.put(("verifying", None))
            try:
                extract_runtime(archive, staged(location))
                self_test(staged(location), release["version"])
            except BaseException:
                shutil.rmtree(staged(location), ignore_errors=True)
                raise
            finally:
                archive.unlink(missing_ok=True)
            return ("installed", None)
        self.run(work)
        return True

    def apply(self):
        """Hand over to the helper; the caller closes the app straight after."""
        if self.state != "ready" or self.applied:
            return False
        launch_helper(self.location, self.release["version"])
        self.applied = True
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
                    self.release = payload or self.release
                    self.state = "available" if payload else "current"
                    self.checked = datetime.now()
                elif result == "installed":
                    self.state = "ready"
        if changed:
            self.notify()
        return changed
