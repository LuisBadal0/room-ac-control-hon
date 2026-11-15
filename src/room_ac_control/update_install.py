"""Installing a verified update on Windows.

Finds how this copy was installed, checks a downloaded MSI, and starts the helper
that swaps folders or runs the installer once the app has closed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .update_release import (
    BUNDLE_UPGRADE_CODE,
    EXECUTABLE,
    INSTALL_KEY,
    NO_WINDOW,
    UNINSTALL_KEY,
    UpdateError,
    self_test,
)


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
