"""Signed update checks, download, unpacking and the swap helper, all offline.

Manifests are pre-signed with a throwaway test key (tests/fixtures); the
private key no longer exists. No network request is made and no real app is
started: the helper is run against fixture folders with launching disabled."""

import base64
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from room_ac_control import updates
from room_ac_control.i18n import Translator
from room_ac_control.secure_state import SecureState
from room_ac_control.translations import PORTUGUESE

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "update_manifests.json").read_text(encoding="utf-8"))
TEST_KEY = FIXTURES["public_key"].encode()
ARCHIVE = base64.b64decode(FIXTURES["archive"])


def case(name):
    item = FIXTURES["cases"][name]
    return base64.b64decode(item["data"]), base64.b64decode(item["signature"])


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def opener_for(responses, seen=None):
    def opener(url, timeout=30):
        if seen is not None:
            seen.append(url)
        return Response(responses[url])

    return opener


def release(**changes):
    data, signature = case("valid")
    value = updates.read_manifest(data, signature, TEST_KEY)
    value.update(changes)
    return value


def runtime_zip(path, files=None, extra=()):
    files = files if files is not None else {"RoomACControl.exe": b"exe", "_internal/base_library.zip": b"lib"}
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("Room AC Control/Start Room AC Control.cmd", "@echo off")
        for name, data in files.items():
            bundle.writestr(updates.ZIP_RUNTIME + name, data)
        for info, data in extra:
            bundle.writestr(info, data)
    return path


class ManifestTests(unittest.TestCase):
    def test_built_in_key_loads_and_matches_the_release_workflow_copy(self):
        from awscrt.crypto import RSA

        self.assertIsNotNone(RSA.new_public_key_from_pem_data(updates.PUBLIC_KEY))
        committed = (Path(__file__).resolve().parents[1] / "packaging" / "update-signing-key.pub").read_bytes()
        self.assertEqual(committed.replace(b"\r\n", b"\n"), updates.PUBLIC_KEY)

    def test_valid_manifest_gives_fixed_github_urls(self):
        value = release()
        self.assertEqual(value["version"], "9.9.9")
        self.assertEqual(
            value["url"],
            "https://github.com/LuisBadal0/room-ac-control-hon/releases/download/"
            "v9.9.9/Room-AC-Control-for-hOn-9.9.9-Windows-x64.zip",
        )
        self.assertEqual(value["notes"], "https://github.com/LuisBadal0/room-ac-control-hon/releases/tag/v9.9.9")

    def test_tampered_or_wrongly_signed_manifests_are_rejected(self):
        data, signature = case("valid")
        for attempt in (data.replace(b"9.9.9", b"9.9.8"), data + b" "):
            with self.assertRaisesRegex(updates.UpdateError, "not signed"):
                updates.read_manifest(attempt, signature, TEST_KEY)
        with self.assertRaisesRegex(updates.UpdateError, "not signed"):
            updates.read_manifest(data, signature[:-1] + bytes([signature[-1] ^ 1]), TEST_KEY)
        with self.assertRaisesRegex(updates.UpdateError, "not signed"):
            updates.read_manifest(data, b"short", TEST_KEY)
        # Signed by the test key, so the app's own key must refuse it.
        with self.assertRaisesRegex(updates.UpdateError, "not signed"):
            updates.read_manifest(data, signature)

    def test_signed_but_invalid_fields_are_rejected(self):
        for name in ("schema", "archive", "tag", "size", "version"):
            with self.subTest(name), self.assertRaises(updates.UpdateError):
                updates.read_manifest(*case(name), TEST_KEY)

    def test_versions_compare_numerically_and_downgrades_are_ignored(self):
        self.assertGreater(updates.parse_version("0.1.10"), updates.parse_version("0.1.9"))
        for text in ("1.2", "1.2.3.4", "01.2.3", "v1.2.3", "", None):
            with self.assertRaises(updates.UpdateError):
                updates.parse_version(text)
        responses = {updates.MANIFEST_URL: case("older")[0], updates.SIGNATURE_URL: case("older")[1]}
        self.assertIsNone(updates.check("0.1.22", opener_for(responses), TEST_KEY))
        responses = {updates.MANIFEST_URL: case("valid")[0], updates.SIGNATURE_URL: case("valid")[1]}
        self.assertEqual(updates.check("0.1.22", opener_for(responses), TEST_KEY)["version"], "9.9.9")
        self.assertIsNone(updates.check("9.9.9", opener_for(responses), TEST_KEY))

    def test_oversized_answers_and_insecure_redirects_are_refused(self):
        responses = {updates.MANIFEST_URL: b"x" * (updates.MAX_MANIFEST + 1)}
        with self.assertRaises(updates.UpdateError):
            updates.fetch(updates.MANIFEST_URL, updates.MAX_MANIFEST, opener_for(responses))
        handler = updates.HttpsOnly()
        with self.assertRaisesRegex(updates.UpdateError, "insecure"):
            handler.redirect_request(None, None, 302, "Found", {}, "http://example.test/update.json")


class DownloadTests(unittest.TestCase):
    def test_matching_download_is_kept_and_progress_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = []
            path = updates.download(
                release(),
                Path(folder),
                lambda done, total: progress.append((done, total)),
                opener=opener_for({release()["url"]: ARCHIVE}),
            )
            self.assertEqual(path.read_bytes(), ARCHIVE)
            self.assertEqual(progress[-1], (len(ARCHIVE), len(ARCHIVE)))
            self.assertEqual([item.name for item in Path(folder).iterdir()], [path.name])

    def test_wrong_bytes_size_or_cancel_leave_nothing_behind(self):
        for body, cancelled in (
            (b"fixture archivX", False),
            (ARCHIVE + b"extra", False),
            (ARCHIVE[:-1], False),
            (ARCHIVE, True),
        ):
            with self.subTest(body=body, cancelled=cancelled), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(updates.UpdateError):
                    updates.download(
                        release(),
                        Path(folder),
                        cancelled=lambda cancelled=cancelled: cancelled,
                        opener=opener_for({release()["url"]: body}),
                    )
                self.assertEqual(list(Path(folder).iterdir()), [])


class UnpackTests(unittest.TestCase):
    def test_only_the_runtime_folder_is_unpacked(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            target = folder / "runtime" / "RoomACControl.new"
            target.mkdir(parents=True)
            (target / "stale.txt").write_text("old")
            updates.extract_runtime(runtime_zip(folder / "update.zip"), target)
            self.assertEqual(
                sorted(str(p.relative_to(target)).replace("\\", "/") for p in target.rglob("*") if p.is_file()),
                ["RoomACControl.exe", "_internal/base_library.zip"],
            )

    def test_unsafe_names_links_and_missing_executable_are_refused(self):
        link = zipfile.ZipInfo(updates.ZIP_RUNTIME + "link")
        link.external_attr = 0o120777 << 16
        unsafe = [
            ((updates.ZIP_RUNTIME + "../../outside.txt"), b"x"),
            ((updates.ZIP_RUNTIME + "C:/outside.txt"), b"x"),
            (link, b"RoomACControl.exe"),
        ]
        for item in unsafe:
            with self.subTest(item=str(item[0])), tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                with self.assertRaisesRegex(updates.UpdateError, "unsafe"):
                    updates.extract_runtime(runtime_zip(folder / "u.zip", extra=[item]), folder / "new")
                self.assertFalse((folder / "outside.txt").exists())
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with self.assertRaisesRegex(updates.UpdateError, "incomplete"):
                updates.extract_runtime(runtime_zip(folder / "u.zip", files={"other.dll": b"x"}), folder / "new")

    def test_new_version_must_pass_its_self_test_with_the_expected_version(self):
        def fake(report):
            def run(command, **options):
                Path(command[-1]).write_text(json.dumps(report), encoding="utf-8")
                return SimpleNamespace(returncode=0 if report.get("ok") else 1)

            return run

        good = {"ok": True, "version": "9.9.9", "updates": True}
        updates.self_test(Path("new"), "9.9.9", run=fake(good))
        for report in ({**good, "ok": False}, {**good, "version": "9.9.8"}, {"ok": True, "version": "9.9.9"}):
            with self.subTest(report=report), self.assertRaises(updates.UpdateError):
                updates.self_test(Path("new"), "9.9.9", run=fake(report))

        def timeout(command, **options):
            raise subprocess.TimeoutExpired(command, 1)

        with self.assertRaises(updates.UpdateError):
            updates.self_test(Path("new"), "9.9.9", run=timeout)


class InstallTests(unittest.TestCase):
    def test_only_the_portable_layout_can_update_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "runtime" / "RoomACControl"
            runtime.mkdir(parents=True)
            exe = runtime / "RoomACControl.exe"
            exe.write_bytes(b"exe")
            self.assertEqual(updates.install_location(exe, frozen=True), runtime.resolve())
            self.assertIsNone(updates.install_location(exe, frozen=False))
            other = Path(folder) / "elsewhere" / "RoomACControl.exe"
            other.parent.mkdir()
            other.write_bytes(b"exe")
            self.assertIsNone(updates.install_location(other, frozen=True))
            self.assertTrue(updates.writable(runtime))

    def test_helper_gets_paths_through_its_environment(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            location = folder / "Luís & Co (test)" / "runtime" / "RoomACControl"
            updates.launch_helper(
                location, "9.9.9", folder=folder, pid=4242, popen=lambda *args, **options: calls.append((args, options))
            )
            script = (folder / "apply-update.cmd").read_bytes()
        (command,), options = calls[0]
        self.assertEqual(command[-3:], ["/d", "/c", r".\apply-update.cmd"])
        self.assertEqual(options["cwd"], str(folder))
        environment = options["env"]
        self.assertEqual(environment["UPDATE_PID"], "4242")
        self.assertEqual(environment["UPDATE_CURRENT"], str(location))
        self.assertEqual(environment["UPDATE_STAGED"], str(location) + ".new")
        self.assertEqual(environment["UPDATE_OLD"], str(location) + ".old")
        self.assertEqual(environment["UPDATE_VERSION"], "9.9.9")
        script.decode("ascii")  # Static ASCII: no paths are written into it.
        self.assertIn(b"\r\n", script)

    @unittest.skipUnless(sys.platform == "win32", "The swap helper is a Windows batch file")
    def test_helper_waits_for_the_app_then_swaps_or_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            location = folder / "Luís & Co" / "runtime" / "RoomACControl"
            location.mkdir(parents=True)
            (location / "RoomACControl.exe").write_text("old")
            new = updates.staged(location)
            new.mkdir()
            (new / "RoomACControl.exe").write_text("new")
            app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
            started = time.monotonic()
            helper = updates.launch_helper(
                location,
                "9.9.9",
                folder=folder / "updates",
                pid=app.pid,
                popen=subprocess.Popen,
                extra={"UPDATE_LAUNCH": "0", "UPDATE_TRIES": "1"},
            )
            self.assertEqual(helper.wait(timeout=60), 0)
            app.wait()
            self.assertGreaterEqual(time.monotonic() - started, 1.5)  # It waited for the app to exit.
            self.assertEqual((location / "RoomACControl.exe").read_text(), "new")
            self.assertEqual((updates.previous(location) / "RoomACControl.exe").read_text(), "old")
            self.assertFalse(new.exists())
            self.assertEqual(updates.finish(location, "9.9.9", folder / "updates"), "Updated to version 9.9.9.")
            self.assertFalse(updates.previous(location).exists())

            # A failed swap puts the current version back and says so.
            helper = updates.launch_helper(
                location,
                "9.9.10",
                folder=folder / "updates",
                pid=999999,
                popen=subprocess.Popen,
                extra={"UPDATE_LAUNCH": "0", "UPDATE_TRIES": "1"},
            )
            self.assertEqual(helper.wait(timeout=60), 1)  # Nothing was staged.
            self.assertEqual((location / "RoomACControl.exe").read_text(), "new")
            self.assertIn("could not be installed", updates.finish(location, "9.9.9", folder / "updates"))

    @unittest.skipUnless(sys.platform == "win32", "The swap helper is a Windows batch file")
    def test_a_folder_still_in_use_keeps_the_current_version_and_says_why(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            location = folder / "runtime" / "RoomACControl"
            location.mkdir(parents=True)
            (location / "RoomACControl.exe").write_text("old")
            new = updates.staged(location)
            new.mkdir()
            (new / "RoomACControl.exe").write_text("new")
            # Another running copy keeps a file open, so Windows will not move the folder.
            with (location / "RoomACControl.exe").open("rb"):
                helper = updates.launch_helper(
                    location,
                    "9.9.9",
                    folder=folder / "updates",
                    pid=999999,
                    popen=subprocess.Popen,
                    extra={"UPDATE_LAUNCH": "0", "UPDATE_TRIES": "1"},
                )
                self.assertEqual(helper.wait(timeout=60), 1)
            self.assertEqual((location / "RoomACControl.exe").read_text(), "old")
            message = updates.finish(location, "0.4.0", folder / "updates")
            self.assertIn("app folder was in use", message)
            self.assertIn(message, PORTUGUESE)

    def test_finish_reports_nothing_without_an_update_and_tidies_leftovers(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            location = folder / "runtime" / "RoomACControl"
            for leftover in (updates.previous(location), updates.staged(location)):
                leftover.mkdir(parents=True)
            (folder / "Room-AC-Control-for-hOn-9.9.9-Windows-x64.zip.part").write_bytes(b"x")
            self.assertIsNone(updates.finish(location, "0.1.23", folder))
            self.assertFalse(updates.previous(location).exists() or updates.staged(location).exists())
            self.assertEqual(list(folder.glob("*.zip*")), [])


class UpdaterTests(unittest.TestCase):
    def wait(self, updater, states):
        deadline = time.monotonic() + 10
        while updater.state not in states and time.monotonic() < deadline:
            updater.poll()
            time.sleep(0.01)
        return updater.state

    def test_check_install_and_apply_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "runtime" / "RoomACControl"
            location.mkdir(parents=True)
            updater = updates.Updater("0.1.23", location)
            seen = []
            updater.listen(lambda: seen.append(updater.state))
            with patch.object(updates, "check", return_value=release()):
                self.assertTrue(updater.check())
                self.assertEqual(self.wait(updater, {"available"}), "available")
            stages = []
            with (
                patch.object(updates, "updates_folder", return_value=Path(folder) / "updates"),
                patch.object(
                    updates,
                    "download",
                    side_effect=lambda r, f, progress, cancelled: (progress(1, 2), runtime_zip(Path(folder) / "u.zip"))[
                        1
                    ],
                ),
                patch.object(
                    updates, "self_test", side_effect=lambda runtime, version: stages.append((runtime, version))
                ),
            ):
                self.assertTrue(updater.install())
                self.assertEqual(self.wait(updater, {"ready", "failed"}), "ready", updater.error)
            self.assertEqual(stages, [(updates.staged(location), "9.9.9")])
            self.assertTrue((updates.staged(location) / "RoomACControl.exe").exists())
            self.assertIn("downloading", seen)
            with patch.object(updates, "launch_helper") as helper:
                self.assertTrue(updater.apply())
                self.assertFalse(updater.apply())  # Never starts the helper twice.
            helper.assert_called_once_with(location, "9.9.9")

    def test_failed_self_test_removes_the_staged_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "runtime" / "RoomACControl"
            location.mkdir(parents=True)
            updater = updates.Updater("0.1.23", location)
            updater.release, updater.state = release(), "available"

            def refuse(runtime, version):
                raise updates.UpdateError("The new version did not pass its checks. Nothing was changed.")

            with (
                patch.object(updates, "updates_folder", return_value=Path(folder) / "updates"),
                patch.object(
                    updates,
                    "download",
                    side_effect=lambda r, f, progress, cancelled: runtime_zip(Path(folder) / "u.zip"),
                ),
                patch.object(updates, "self_test", side_effect=refuse),
            ):
                updater.install()
                self.assertEqual(self.wait(updater, {"ready", "failed"}), "failed")
            self.assertIn("did not pass", updater.error)
            self.assertFalse(updates.staged(location).exists())
            self.assertFalse(updater.apply())

    def test_quiet_automatic_check_failures_stay_silent(self):
        updater = updates.Updater("0.1.23", Path("runtime/RoomACControl"))
        with patch.object(updates, "check", side_effect=OSError("offline")):
            updater.check(quiet=True)
            self.assertEqual(self.wait(updater, {"idle", "failed"}), "idle")
            updater.check()
            self.assertEqual(self.wait(updater, {"idle", "failed"}), "failed")
        self.assertIn("internet", updater.error)

    def test_source_checkouts_and_previews_never_update(self):
        for updater in (updates.Updater("0.1.23", None), updates.Updater("0.1.23", Path("x"), demo=True)):
            self.assertFalse(updater.supported)
            self.assertFalse(updater.check())
            self.assertFalse(updater.install())


class PreferenceAndLanguageTests(unittest.TestCase):
    def test_automatic_checks_default_on_and_the_choice_is_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.dpapi"
            state = SecureState(path)
            self.assertTrue(state.auto_update())
            state.save_auto_update(False)
            self.assertFalse(SecureState(path).auto_update())
        state = SecureState(persistent=False)
        for value in ("no", 0, None):
            state.data["auto_update"] = value
            self.assertTrue(state.auto_update())
            with self.assertRaises(ValueError):
                state.save_auto_update(value)
        with patch.object(state, "write", side_effect=OSError("fixture")):
            state.data.pop("auto_update")
            with self.assertRaises(OSError):
                state.save_auto_update(False)
        self.assertNotIn("auto_update", state.data)

    def test_every_update_message_is_translated(self):
        import ast

        source = (Path(__file__).resolve().parents[1] / "src" / "room_ac_control" / "updates.py").read_text(
            encoding="utf-8"
        )
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "UpdateError":
                self.assertIn(node.args[0].value, PORTUGUESE)
        from room_ac_control.updates_view import UpdatesView

        portuguese = Translator("pt-PT")
        fake = SimpleNamespace()
        for state in ("idle", "checking", "current", "available", "downloading", "verifying", "ready"):
            fake.updater = SimpleNamespace(
                state=state, supported=True, demo=False, release=release(), progress=0.5, error=None
            )
            for text in UpdatesView.message(fake):
                self.assertNotEqual(portuguese.translate(text), text, text)
        for demo, supported in ((True, False), (False, False)):
            fake.updater.demo, fake.updater.supported = demo, supported
            for text in UpdatesView.message(fake):
                self.assertNotEqual(portuguese.translate(text), text, text)


if __name__ == "__main__":
    unittest.main()
