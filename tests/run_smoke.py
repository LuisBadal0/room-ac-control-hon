"""Run every offline Windows UI smoke check, each in its own process, and fail if any fails.

CI and contributors run this one script; it never contacts an account or an AC."""

import os
import subprocess
import sys
import time
from pathlib import Path


def main(names=None):
    if os.environ.get("ROOM_AC_SMOKE_RUNNER"):
        print("run_smoke.py is already running; it does not start itself again.", flush=True)
        return 1
    os.environ["ROOM_AC_SMOKE_RUNNER"] = "1"  # Inherited by every check this starts.
    folder = Path(__file__).resolve().parent
    failed = []
    # Every tests/*_smoke.py, so a new check cannot be left out; never this runner itself.
    found = sorted(path.name for path in folder.glob("*_smoke.py") if path.name != Path(__file__).name)
    for name in names or found:
        if name == Path(__file__).name:
            continue
        started = time.monotonic()
        result = subprocess.run([sys.executable, str(folder / name)])
        status = "passed" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
        print(f"== {name}: {status} in {time.monotonic() - started:.1f}s", flush=True)
        if result.returncode:
            failed.append(name)
    if failed:
        print("Failed smoke checks: " + ", ".join(failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
