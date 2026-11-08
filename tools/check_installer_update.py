"""End-to-end check that an installed copy updates through its installer.

Usage (CI, on a clean Windows runner):
    python tools/check_installer_update.py --kind msi --old OLD.msi --new NEW.msi --version X.Y.Z
    python tools/check_installer_update.py --kind setup --old OLD-Setup.exe --new NEW-Setup.exe --version X.Y.Z

It installs the old release for the current user, runs the app's own installer
helper with the new installer exactly as an in-app update would (without
starting the app), then checks that Windows lists one "Room AC Control for hOn"
at the new version, that the installed app passes its self-test, and that
uninstalling leaves nothing behind. It refuses to run where Room AC Control is
already installed, so it never touches a real installation.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from room_ac_control import updates  # noqa: E402

NAME = "Room AC Control for hOn"


def program_entries():
    """Visible Installed apps entries for the app: (key, version, uninstall command)."""
    registry = updates.WindowsRegistry()
    found = []
    for key in registry.subkeys(updates.UNINSTALL_KEY):
        path = f"{updates.UNINSTALL_KEY}\\{key}"
        if registry.value(path, "DisplayName") != NAME or registry.value(path, "SystemComponent") == 1:
            continue
        command = registry.value(path, "QuietUninstallString") or registry.value(path, "UninstallString")
        found.append((key, registry.value(path, "DisplayVersion"), command))
    return found


def run(command, what):
    print(f"> {what}", flush=True)
    result = subprocess.run(command, timeout=900)
    if result.returncode not in (0, 3010):
        raise SystemExit(f"{what} failed with exit code {result.returncode}.")


def install(kind, installer, log):
    if kind == "msi":
        run(f'msiexec.exe /i "{installer}" /qn /norestart /l*v "{log}"', f"Install {installer.name}")
    else:
        run(f'"{installer}" /quiet /norestart /log "{log}"', f"Install {installer.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", choices=sorted(updates.INSTALLERS), required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This check installs Windows packages.")
    registry = updates.WindowsRegistry()
    if registry.value(updates.INSTALL_KEY, "InstallFolder") or program_entries():
        raise SystemExit("Room AC Control is already installed here; run this check on a clean machine only.")

    work = Path(tempfile.mkdtemp(prefix="installer-update-"))
    install(args.kind, args.old.resolve(), work / "old.log")
    folder = Path(registry.value(updates.INSTALL_KEY, "InstallFolder"))
    location = folder / "runtime" / "RoomACControl"
    detected = updates.installed_by(location)
    print(f"Installed {[version for _, version, _ in program_entries()]}, detected as {detected!r}.", flush=True)
    if detected != args.kind:
        raise SystemExit(f"Expected the app to report a {args.kind} install, got {detected!r}.")

    # The app's own helper, with a stand-in process for the app that is closing.
    closing = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
    helper = updates.launch_installer_helper(
        location,
        args.kind,
        args.new.resolve(),
        args.version,
        folder=work / "updates",
        pid=closing.pid,
        popen=subprocess.Popen,
        extra={"UPDATE_LAUNCH": "0"},
    )
    started = time.monotonic()
    code = helper.wait(timeout=900)
    closing.wait()
    message = updates.finish(location, args.version, work / "updates")
    print(f"Helper exit {code} after {time.monotonic() - started:.0f}s: {message}", flush=True)
    if code != 0 or message != f"Updated to version {args.version}.":
        log = work / "updates" / "install.log"
        if log.exists():
            print(log.read_text(encoding="utf-16", errors="replace")[-6000:])
        raise SystemExit("The installer update did not succeed.")

    entries = program_entries()
    print(f"Installed apps now lists: {entries}", flush=True)
    if [version for _, version, _ in entries] != [args.version]:
        raise SystemExit(f"Expected exactly one {NAME} entry at {args.version}.")
    report = work / "self-test.json"
    subprocess.run([str(location / updates.EXECUTABLE), "--self-test", str(report)], timeout=300)
    outcome = json.loads(report.read_text(encoding="utf-8"))
    if not (outcome.get("ok") and outcome.get("version") == args.version):
        raise SystemExit(f"The updated app failed its self-test: {outcome}")

    _, _, command = entries[0]
    if args.kind == "msi":
        run(f'msiexec.exe /x "{args.new.resolve()}" /qn /norestart', "Uninstall")
    else:
        run(f"{command} /quiet" if "/quiet" not in command.lower() else command, "Uninstall")
    for _ in range(30):
        if not program_entries() and not folder.exists():
            break
        time.sleep(1)
    if program_entries() or folder.exists() or registry.value(updates.INSTALL_KEY, "InstallFolder"):
        raise SystemExit("Uninstalling left the app, its folder or its registry record behind.")
    print(f"{args.kind}: {args.old.name} -> {args.new.name} updated in place and uninstalled cleanly.")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
