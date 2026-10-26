"""Version bumps must agree everywhere, since merging one publishes a release."""
from pathlib import Path
import re
import tomllib
import unittest

from room_ac_control import __version__

ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
