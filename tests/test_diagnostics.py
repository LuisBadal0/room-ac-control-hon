"""Diagnostics must remain useful without exporting untrusted sensitive text."""

import json
import logging
import re
import tempfile
import unittest
from pathlib import Path

from room_ac_control.diagnostics import EVENTS, Diagnostics, quiet_library_logs


class DiagnosticTests(unittest.TestCase):
    def test_secret_messages_and_custom_exception_names_are_not_exported(self):
        report = Diagnostics()
        secret = "sample@example.test token=secret-test-token password=fake-password"
        report.record("cloud_operation_failed", RuntimeError(secret))
        error = type("secret_test_token", (Exception,), {})(secret)
        report.record("background_task_failed", error)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            report.export(path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(secret, text)
            self.assertNotIn("secret_test_token", text)
            self.assertEqual(json.loads(text)["events"][-1]["error"], "UnexpectedError")
        with self.assertRaises(ValueError):
            report.record(secret)

    def test_every_event_the_app_records_is_registered(self):
        # An unregistered name raises inside an error handler, hiding the original failure.
        source = Path(__file__).resolve().parents[1] / "src" / "room_ac_control"
        used = {}
        for file in sorted(source.rglob("*.py")):
            for name in re.findall(r'diagnostics\.record\(\s*"([^"]+)"', file.read_text(encoding="utf-8")):
                used.setdefault(name, file.name)
        self.assertGreater(len(used), 10)
        self.assertEqual({name: file for name, file in used.items() if name not in EVENTS}, {})
        self.assertEqual(EVENTS - set(used), set(), "registered events nothing records")

    def test_reports_are_bounded_and_copied(self):
        report = Diagnostics(limit=2)
        for _ in range(5):
            report.record("notification_failed", TimeoutError("secret"))
        exported = report.report()
        self.assertEqual(len(exported["events"]), 2)
        exported["events"][0]["event"] = "modified"
        self.assertEqual(report.report()["events"][0]["event"], "notification_failed")

    def test_library_suppression_does_not_disable_application_logging(self):
        prior = logging.root.manager.disable
        quiet_library_logs()
        self.assertEqual(logging.root.manager.disable, prior)
        with self.assertLogs("room_ac_control", level="WARNING") as captured:
            logging.getLogger("room_ac_control").warning("safe application event")
        self.assertIn("safe application event", captured.output[0])


if __name__ == "__main__":
    unittest.main()
