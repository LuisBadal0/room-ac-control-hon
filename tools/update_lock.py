"""Pin packages to new versions in the hash-verified locks.

Usage: python tools/update_lock.py pillow==12.4.0 [pyhon==0.18.0 ...]

For each package, the SHA-256 of every wheel PyPI publishes for that version is
written into each lock that already pins the package, and the pin in
requirements.txt is updated when the package is listed there. New transitive
dependencies are not resolved: add them by hand, then run the tests and a fresh
`tools/Setup.ps1`. Releases newer than 14 days are refused unless --allow-new is
given, so a compromised or broken release has time to be pulled first.
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKS = (
    ROOT / "requirements.lock",
    ROOT / "packaging" / "requirements-build.lock",
    ROOT / "packaging" / "requirements-dev.lock",
)
REQUIREMENTS = ROOT / "requirements.txt"
MINIMUM_AGE = timedelta(days=14)


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_hashes(release):
    """SHA-256 values for every non-yanked wheel in a PyPI release JSON."""
    files = [f for f in release["urls"] if f["packagetype"] == "bdist_wheel" and not f.get("yanked")]
    if not files:
        raise ValueError(f"{release['info']['name']} {release['info']['version']} has no wheels on PyPI.")
    uploaded = min(datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00")) for f in files)
    return sorted({f["digests"]["sha256"] for f in files}), uploaded


def entry(name, version, hashes):
    lines = [f"{name}=={version} \\"]
    lines += [f"    --hash=sha256:{digest} \\" for digest in hashes]
    lines[-1] = lines[-1].removesuffix(" \\")
    return "\n".join(lines) + "\n"


def replace_entry(text, name, version, hashes):
    """Replace a package's pin and hashes; None when the lock does not pin it."""
    pattern = re.compile(
        r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==[^\s\\]+(?: \\\n(?:[ \t]+--hash=\S+(?: \\)?\n?)+)", re.M
    )
    for match in pattern.finditer(text):
        if normalize(match["name"]) == normalize(name):
            block = entry(match["name"], version, hashes)
            if not match.group(0).endswith("\n"):
                block = block.rstrip("\n")
            return text[: match.start()] + block + text[match.end() :]
    return None


def replace_requirement(text, name, version):
    pattern = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==\S+$", re.M)
    for match in pattern.finditer(text):
        if normalize(match["name"]) == normalize(name):
            return text[: match.start()] + f"{match['name']}=={version}" + text[match.end() :]
    return text


def fetch(name, version):
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{name}/{version}/json", headers={"User-Agent": "room-ac-control-lock-updater"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(argv=None, fetcher=fetch, now=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pins", nargs="+", metavar="name==version")
    parser.add_argument("--allow-new", action="store_true", help="accept releases newer than 14 days")
    args = parser.parse_args(argv)
    now = now or datetime.now(UTC)
    for pin in args.pins:
        name, _, version = pin.partition("==")
        if not name or not version:
            parser.error(f"Expected name==version, got {pin!r}.")
        hashes, uploaded = wheel_hashes(fetcher(name, version))
        if now - uploaded < MINIMUM_AGE and not args.allow_new:
            print(f"{name} {version} was released {uploaded:%Y-%m-%d}; wait 14 days or pass --allow-new.")
            return 1
        changed, pinned = [], False
        for lock in LOCKS:
            if not lock.exists():
                continue
            text = lock.read_text(encoding="utf-8")
            updated = replace_entry(text, name, version, hashes)
            if updated is None:
                continue
            pinned = True
            if updated != text:
                lock.write_text(updated, encoding="utf-8", newline="\n")
                changed.append(lock.relative_to(ROOT).as_posix())
        if not pinned:
            print(f"{name} is not pinned in any lock; add it by hand with its dependencies.")
            return 1
        text = REQUIREMENTS.read_text(encoding="utf-8")
        updated = replace_requirement(text, name, version)
        if updated != text:
            REQUIREMENTS.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(REQUIREMENTS.name)
        print(
            f"{name}=={version}: {len(hashes)} wheel hashes; updated {', '.join(changed) or 'nothing (already current)'}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
