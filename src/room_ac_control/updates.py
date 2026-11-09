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

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime
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
MAX_INSTALLER = 400 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
# How this copy was installed -> the manifest field naming that installer.
INSTALLERS = {"msi": "installer", "setup": "setup"}
INSTALL_KEY = r"Software\RoomACControl\Installer"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
# packaging/installer/Setup.wxs; a Setup.exe install registers this bundle for the user.
BUNDLE_UPGRADE_CODE = "{3CE84886-4F75-40A5-B136-E82F9D22EA78}"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
    if (
        manifest.get("tag") != f"v{version}"
        or archive != f"Room-AC-Control-for-hOn-{version}-Windows-x64.zip"
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 < size <= MAX_ARCHIVE
    ):
        raise UpdateError("The update information is not valid.")
    return {
        "version": version,
        "tag": manifest["tag"],
        "archive": archive,
        "sha256": digest,
        "size": size,
        "url": download_url(manifest["tag"], archive),
        "notes": f"https://github.com/{REPOSITORY}/releases/tag/{manifest['tag']}",
        "installers": signed_installers(manifest, version),
    }


def download_url(tag, name):
    return f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"


def installer_name(kind, version):
    suffix = ".msi" if kind == "msi" else "-Setup.exe"
    return f"Room-AC-Control-for-hOn-{version}-Windows-x64{suffix}"


def signed_installers(manifest, version):
    """The optional signed MSI and Setup.exe entries; releases before 0.6.0 have none."""
    found = {}
    for kind, field in INSTALLERS.items():
        entry = manifest.get(field)
        if entry is None:
            continue
        name = installer_name(kind, version)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        size = entry.get("size") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or entry.get("name") != name
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 < size <= MAX_INSTALLER
        ):
            raise UpdateError("The update information is not valid.")
        found[kind] = {"name": name, "sha256": digest, "size": size, "url": download_url(manifest["tag"], name)}
    return found


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
    item = {"name": release["archive"], **{key: release[key] for key in ("url", "size", "sha256")}}
    return download_file(item, folder, progress, cancelled, opener)


@contextmanager
def local_step():
    """Disk work for an update. A failure here is this computer's (a full disk, a folder
    that cannot be written), so it must not be reported as a network problem."""
    try:
        yield
    except (OSError, zipfile.BadZipFile, shutil.Error) as error:
        diagnostics.record("update_failed", error)
        raise UpdateError(
            "The update could not be saved on this computer. Check free disk space and try again."
        ) from None


def download_file(release, folder, progress=lambda done, total: None, cancelled=lambda: False, opener=open_url):
    """Stream one signed release file (name, url, size, sha256) to disk."""
    with local_step():
        folder.mkdir(parents=True, exist_ok=True)
    target = folder / release["name"]
    partial = target.with_name(target.name + ".part")
    digest, done = hashlib.sha256(), 0
    try:
        with opener(release["url"], timeout=60) as response:
            with local_step():
                handle = partial.open("wb")
            with handle:
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
                    with local_step():
                        handle.write(chunk)
                    progress(done, release["size"])
        if done != release["size"] or digest.hexdigest() != release["sha256"]:
            raise UpdateError("The downloaded update does not match its signature. It was not installed.")
        with local_step():
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
            relative = PurePosixPath(info.filename[len(ZIP_RUNTIME) :])
            mode = (info.external_attr >> 16) & 0o170000
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or any(":" in part or "\\" in part for part in relative.parts)
                or mode == 0o120000
            ):
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
            result = run(
                [str(runtime / EXECUTABLE), "--self-test", str(report)],
                timeout=120,
                creationflags=NO_WINDOW,
            )
            outcome = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            outcome, result = {}, None
    if not (
        result is not None
        and result.returncode == 0
        and outcome.get("ok") is True
        and outcome.get("version") == version
        and outcome.get("updates") is True
    ):
        raise UpdateError("The new version did not pass its checks. Nothing was changed.")


def updates_folder():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RoomACControl" / "updates"


class WindowsRegistry:
    """Read-only access to the current user's registry hive."""

    def value(self, key, name):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                return winreg.QueryValueEx(handle, name)[0]
        except (ImportError, OSError):
            return None

    def subkeys(self, key):
        try:
            import winreg

            names = []
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                while True:
                    try:
                        names.append(winreg.EnumKey(handle, len(names)))
                    except OSError:
                        return names
        except (ImportError, OSError):
            return []


def same_folder(left, right):
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))
    except (OSError, ValueError):
        return False


def installed_by(location, registry=None):
    """ "setup" or "msi" when Windows installed this copy, None for a portable copy."""
    if location is None:
        return None
    registry = registry or WindowsRegistry()
    recorded = registry.value(INSTALL_KEY, "InstallFolder")
    if not isinstance(recorded, str) or not recorded.strip() or not same_folder(recorded, location.parent.parent):
        return None
    for name in registry.subkeys(UNINSTALL_KEY):
        codes = registry.value(f"{UNINSTALL_KEY}\\{name}", "BundleUpgradeCode")
        codes = [codes] if isinstance(codes, str) else codes if isinstance(codes, list) else []
        if any(str(code).upper() == BUNDLE_UPGRADE_CODE for code in codes):
            return "setup"
    return "msi"


def run_installer_step(run, command):
    """Run msiexec or Setup.exe without a window; any failure stops the update."""
    try:
        result = run(command, timeout=600, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is None or result.returncode != 0:
        raise UpdateError("The downloaded installer could not be opened. Nothing was changed.")


def find_runtime(image):
    for executable in sorted(image.rglob(EXECUTABLE)):
        if executable.parent.name == "RoomACControl" and executable.parent.parent.name == "runtime":
            return executable.parent
    raise UpdateError("The update is incomplete. It was not installed.")


def installer_scratch():
    """A short folder for unpacking installers: Windows Installer refuses paths over 259
    characters, and the unpacked app nests about 125 characters deep below it."""
    return updates_folder().parent / "u"


def check_msi(msi, version, scratch=None, run=subprocess.run):
    """Unpack the app from a downloaded MSI without installing it, then self-test it.

    msiexec /a copies the MSI's files to a folder without registering anything and
    needs no administrator rights. Setup.exe embeds this same MSI, so a Setup.exe
    update is checked with the signed MSI from the same release."""
    scratch = scratch or installer_scratch()
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        image = scratch / "a"
        # Built by hand: msiexec needs PROPERTY="value" quoting, which list arguments would break.
        run_installer_step(run, f'msiexec.exe /a "{msi}" /qn TARGETDIR="{image}"')
        self_test(find_runtime(image), version, run)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def install_location(executable=None, frozen=None):
    """The runtime folder this app runs from (portable or installed), or None for a source checkout."""
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
    environment = {
        **os.environ,
        "UPDATE_PID": str(pid or os.getpid()),
        "UPDATE_CURRENT": str(location),
        "UPDATE_STAGED": str(staged(location)),
        "UPDATE_OLD": str(previous(location)),
        "UPDATE_RESULT": str(folder / "result.json"),
        "UPDATE_VERSION": version,
        **(extra or {}),
    }
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    comspec = os.environ.get("ComSpec", "cmd.exe")
    # Use a relative path with a dot prefix: cmd then finds the script even when NoDefaultCurrentDirectoryInExePath is set.
    return popen(
        [comspec, "/d", "/c", ".\\" + script.name],
        cwd=str(folder),
        env=environment,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# Runs the signed installer once the app has exited. Windows Installer rolls back
# a failed install, so the previous version stays. Exit codes: 0 done, 3010/1641
# done but Windows wants a restart, 1618 another installation was running.
# UPDATE_FAKE_EXIT stands in for the installer in tests, so no test installs anything.
INSTALLER_HELPER = r"""@echo off
setlocal DisableDelayedExpansion
set /a WAITED=0
:wait
tasklist /FI "PID eq %UPDATE_PID%" /NH 2>nul | find " %UPDATE_PID% " >nul
if not errorlevel 1 (
    if %WAITED% geq 120 goto gave_up
    set /a WAITED+=1
    ping -n 2 127.0.0.1 >nul
    goto wait
)
if defined UPDATE_FAKE_EXIT (
    set UPDATE_CODE=%UPDATE_FAKE_EXIT%
    goto installed
)
if "%UPDATE_KIND%"=="setup" goto setup
start "" /wait msiexec.exe /i "%UPDATE_INSTALLER%" /qn /norestart INSTALLFOLDER="%UPDATE_FOLDER%" /l*v "%UPDATE_LOG%"
set UPDATE_CODE=%errorlevel%
goto installed
:setup
start "" /wait "%UPDATE_INSTALLER%" /quiet /norestart /log "%UPDATE_LOG%"
set UPDATE_CODE=%errorlevel%
:installed
if "%UPDATE_CODE%"=="0" goto done
if "%UPDATE_CODE%"=="3010" goto done
if "%UPDATE_CODE%"=="1641" goto done
set UPDATE_REASON=failed
if "%UPDATE_CODE%"=="1618" set UPDATE_REASON=installer-busy
> "%UPDATE_RESULT%" echo {"ok": false, "version": "%UPDATE_VERSION%", "reason": "%UPDATE_REASON%", "code": "%UPDATE_CODE%"}
if not "%UPDATE_LAUNCH%"=="0" start "" "%UPDATE_APP%"
exit /b 1
:done
> "%UPDATE_RESULT%" echo {"ok": true, "version": "%UPDATE_VERSION%"}
if not "%UPDATE_LAUNCH%"=="0" start "" "%UPDATE_APP%"
exit /b 0
:gave_up
> "%UPDATE_RESULT%" echo {"ok": false, "version": "%UPDATE_VERSION%", "reason": "timeout"}
exit /b 1
"""


def launch_installer_helper(
    location, kind, installer, version, folder=None, pid=None, popen=subprocess.Popen, extra=None
):
    """Start the installer helper; it waits for this process to exit before installing.

    `extra` adds environment settings for tests (UPDATE_LAUNCH=0, UPDATE_FAKE_EXIT)."""
    folder = folder or updates_folder()
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "install-update.cmd"
    script.write_text(INSTALLER_HELPER.replace("\n", "\r\n"), encoding="ascii", newline="")
    (folder / "result.json").unlink(missing_ok=True)
    environment = {
        **os.environ,
        "UPDATE_PID": str(pid or os.getpid()),
        "UPDATE_KIND": kind,
        "UPDATE_INSTALLER": str(installer),
        # No trailing backslash: it would escape the closing quote on msiexec's command line.
        "UPDATE_FOLDER": str(location.parent.parent).rstrip("\\"),
        "UPDATE_APP": str(location / EXECUTABLE),
        "UPDATE_LOG": str(folder / "install.log"),
        "UPDATE_RESULT": str(folder / "result.json"),
        "UPDATE_VERSION": version,
        **(extra or {}),
    }
    flags = NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    comspec = os.environ.get("ComSpec", "cmd.exe")
    return popen(
        [comspec, "/d", "/c", ".\\" + script.name],
        cwd=str(folder),
        env=environment,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def finish(location, current, folder=None):
    """After a start: report the last update's outcome and tidy up its files."""
    folder = folder or updates_folder()
    message = None
    succeeded = False
    result = folder / "result.json"
    try:
        outcome = json.loads(result.read_text(encoding="utf-8"))
        if outcome.get("ok") and outcome.get("version") == current:
            message, succeeded = f"Updated to version {current}.", True
        elif outcome.get("reason") == "busy":
            # Windows would not move the app folder: another copy or window still had it open.
            message = (
                "The update could not be installed because the app folder was in use. Close every "
                "Room AC Control window, including the one in the notification area, then try again."
            )
        elif outcome.get("reason") == "installer-busy":
            message = (
                "The update could not be installed because another installation was running in Windows. "
                "Try again in a few minutes."
            )
        else:
            message = f"The update could not be installed. Room AC Control is still on version {current}."
    except (OSError, ValueError, AttributeError):
        pass
    result.unlink(missing_ok=True)
    if location is not None:
        for leftover in (previous(location), staged(location)):
            shutil.rmtree(leftover, ignore_errors=True)
    if folder.exists():
        for download in folder.glob("Room-AC-Control-for-hOn-*"):
            download.unlink(missing_ok=True)
        if succeeded:
            # A failed installer's log stays for troubleshooting until the next update.
            (folder / "install.log").unlink(missing_ok=True)
    return message


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

    def apply(self):
        """Hand over to the helper; the caller closes the app straight after."""
        if self.state != "ready" or self.applied:
            return False
        if self.installer:
            launch_installer_helper(self.location, self.installed, self.installer, self.release["version"])
        else:
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
                    self.state, self.installer = "ready", payload
        if changed:
            self.notify()
        return changed
