"""Install verified Windows dependencies, then the reviewed local source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def lock_digests(build=False):
    return {"runtime": hashlib.sha256((ROOT/"requirements.lock").read_bytes()).hexdigest(),
            "build": hashlib.sha256((ROOT/"packaging"/"requirements-build.lock").read_bytes()).hexdigest() if build else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("These dependency locks are for Windows.")
    if sys.prefix == sys.base_prefix or not Path(sys.prefix).resolve().is_relative_to(ROOT):
        raise RuntimeError("Use a virtual environment inside this checkout.")
    lock = ROOT/"packaging"/"requirements-build.lock" if args.build else ROOT/"requirements.lock"
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--require-hashes", "--only-binary=:all:", "--force-reinstall", "-r", str(lock)], check=True)
    # Editable source is intentionally local; no isolated, unpinned build download.
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-deps", "--no-build-isolation", "-e", str(ROOT)], check=True)
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    (Path(sys.prefix)/"room-ac-ready").write_text(json.dumps(lock_digests(args.build))+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
