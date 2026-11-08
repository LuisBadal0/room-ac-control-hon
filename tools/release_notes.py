"""Print one version's section of CHANGELOG.md, for its GitHub release notes.

Usage: python tools/release_notes.py [version] [--output file]

Without a version, the app version from src/room_ac_control/__init__.py is used.
Exits with an error when CHANGELOG.md has no section, or an empty one, for it.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$", re.M)


def app_version():
    text = (ROOT / "src" / "room_ac_control" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r"__version__\s*=\s*\"([^\"]+)\"", text).group(1)


def sections(text):
    """Map each `## [version] - date` heading to (date, body)."""
    found = {}
    headings = list(re.finditer(r"^## .*$", text, re.M))
    for index, match in enumerate(headings):
        parsed = HEADING.match(match.group(0))
        if not parsed:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        found[parsed["version"]] = (parsed["date"], text[match.end() : end].strip())
    return found


def notes(version, text=None):
    text = CHANGELOG.read_text(encoding="utf-8") if text is None else text
    section = sections(text).get(version)
    if section is None:
        raise ValueError(f"CHANGELOG.md has no section for {version}.")
    date, body = section
    if not date:
        raise ValueError(f"CHANGELOG.md's section for {version} has no release date.")
    if not re.search(r"^- ", body, re.M):
        raise ValueError(f"CHANGELOG.md's section for {version} lists no changes.")
    return body + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        body = notes(args.version or app_version())
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(body, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
