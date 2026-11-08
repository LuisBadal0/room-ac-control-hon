"""Version bumps must agree everywhere, since merging one publishes a release."""

import re
import sys
import tomllib
import unittest
from pathlib import Path

from room_ac_control import __version__

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import release_notes  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_app_version_matches_package_executable_and_readme(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        self.assertEqual(__version__, version)
        numbers = tuple(int(part) for part in version.split(".")) + (0,)
        info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
        for field in ("filevers", "prodvers"):
            found = re.search(rf"{field}=\(([\d,\s]+)\)", info).group(1)
            self.assertEqual(tuple(int(part) for part in found.split(",")), numbers, field)
        self.assertIn(f"StringStruct('FileVersion','{version}.0')", info)
        self.assertIn(f"StringStruct('ProductVersion','{version}')", info)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"Room-AC-Control-for-hOn-([\d.]+)-Windows-x64\.zip", readme)), {version})
        self.assertEqual(set(re.findall(r"`v(\d+\.\d+\.\d+)`", readme)), {version})


class ChangelogTests(unittest.TestCase):
    """Merging a version bump publishes CHANGELOG.md's section as the release notes."""

    def setUp(self):
        self.text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_current_version_has_dated_release_notes(self):
        body = release_notes.notes(__version__)
        self.assertRegex(body, r"(?m)^- \S")
        self.assertNotRegex(body, r"(?m)^## ")

    def test_unreleased_comes_first_and_versions_descend(self):
        found = release_notes.sections(self.text)
        self.assertEqual(next(iter(found)), "Unreleased")
        versions = [tuple(int(part) for part in v.split(".")) for v in found if v != "Unreleased"]
        self.assertEqual(versions, sorted(versions, reverse=True))
        self.assertEqual(len(versions), len(set(versions)))
        dates = [date for v, (date, _) in found.items() if v != "Unreleased"]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_missing_undated_or_empty_sections_are_refused(self):
        sample = "## [Unreleased]\n\n## [1.1.0]\n\n- Draft\n\n## [1.0.0] - 2026-01-01\n\n### Added\n"
        for version in ("Unreleased", "1.1.0", "1.0.0", "2.0.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_notes.notes(version, sample)
        self.assertEqual(
            release_notes.notes(
                "1.0.0", "## [1.0.0] - 2026-01-01\n\n### Added\n\n- A thing\n\n## [0.9.0] - 2025-12-01\n"
            ),
            "### Added\n\n- A thing\n",
        )


if __name__ == "__main__":
    unittest.main()
