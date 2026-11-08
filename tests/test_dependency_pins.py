import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import update_lock  # noqa: E402

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", re.M)


def pins(path):
    return {update_lock.normalize(name): version for name, version in PIN.findall(path.read_text(encoding="utf-8"))}


def release(name, version, digests, uploaded="2026-01-01T00:00:00.000000Z"):
    files = [
        {"packagetype": "bdist_wheel", "digests": {"sha256": d}, "upload_time_iso_8601": uploaded} for d in digests
    ]
    files.append({"packagetype": "sdist", "digests": {"sha256": "f" * 64}, "upload_time_iso_8601": uploaded})
    return {"info": {"name": name, "version": version}, "urls": files}


LOCK = """# Fixture lock.
alpha==1.0 \\
    --hash=sha256:aaaa \\
    --hash=sha256:bbbb

Beta_Pkg==2.0 \\
    --hash=sha256:cccc
"""


class LockConsistencyTests(unittest.TestCase):
    def test_direct_pins_match_the_runtime_lock(self):
        # A Dependabot bump of requirements.txt alone fails here until
        # tools/update_lock.py writes the matching hashes.
        lock = pins(ROOT / "requirements.lock")
        for name, version in pins(ROOT / "requirements.txt").items():
            self.assertEqual(lock.get(name), version, f"{name}: run tools/update_lock.py {name}=={version}")

    def test_every_locked_package_has_a_hash(self):
        for path in update_lock.LOCKS:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for match in PIN.finditer(text):
                following = text[match.end() :].split("\n", 2)
                self.assertIn("--hash=sha256:", following[1], f"{path.name}: {match.group(0)}")


class UpdateLockTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.lock = self.root / "requirements.lock"
        self.lock.write_text(LOCK, encoding="utf-8")
        self.requirements = self.root / "requirements.txt"
        self.requirements.write_text("Alpha==1.0\nother==3\n", encoding="utf-8")
        for name, value in {
            "ROOT": self.root,
            "LOCKS": (self.lock, self.root / "missing.lock"),
            "REQUIREMENTS": self.requirements,
        }.items():
            patcher = mock.patch.object(update_lock, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_tool(self, *argv, digests=("1111", "2222"), uploaded="2026-01-01T00:00:00.000000Z"):
        output = io.StringIO()
        fetcher = lambda name, version: release(name, version, digests, uploaded)  # noqa: E731
        with redirect_stdout(output):
            code = update_lock.main(list(argv), fetcher=fetcher, now=datetime(2026, 3, 1, tzinfo=UTC))
        return code, output.getvalue()

    def test_rewrites_only_the_named_entry_with_every_wheel_hash(self):
        code, _ = self.run_tool("alpha==1.1")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.lock.read_text(encoding="utf-8"),
            LOCK.replace(
                "alpha==1.0 \\\n    --hash=sha256:aaaa \\\n    --hash=sha256:bbbb",
                "alpha==1.1 \\\n    --hash=sha256:1111 \\\n    --hash=sha256:2222",
            ),
        )
        self.assertEqual(self.requirements.read_text(encoding="utf-8"), "Alpha==1.1\nother==3\n")

    def test_matches_normalized_names_and_keeps_the_last_entry_intact(self):
        code, _ = self.run_tool("beta-pkg==2.1", digests=("3333",))
        self.assertEqual(code, 0)
        self.assertTrue(self.lock.read_text(encoding="utf-8").endswith("Beta_Pkg==2.1 \\\n    --hash=sha256:3333\n"))
        self.assertEqual(self.requirements.read_text(encoding="utf-8"), "Alpha==1.0\nother==3\n")

    def test_refuses_releases_younger_than_two_weeks(self):
        code, output = self.run_tool("alpha==1.1", uploaded="2026-02-25T00:00:00.000000Z")
        self.assertEqual(code, 1)
        self.assertIn("--allow-new", output)
        self.assertEqual(self.lock.read_text(encoding="utf-8"), LOCK)
        code, _ = self.run_tool("alpha==1.1", "--allow-new", uploaded="2026-02-25T00:00:00.000000Z")
        self.assertEqual(code, 0)

    def test_refuses_packages_that_no_lock_pins(self):
        code, output = self.run_tool("gamma==1.0")
        self.assertEqual(code, 1)
        self.assertIn("not pinned", output)
        self.assertEqual(self.lock.read_text(encoding="utf-8"), LOCK)

    def test_rejects_releases_without_wheels(self):
        with self.assertRaises(ValueError):
            update_lock.wheel_hashes({"info": {"name": "x", "version": "1"}, "urls": []})


if __name__ == "__main__":
    unittest.main()
