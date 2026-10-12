"""Offline timer dispatch, persistence and real command routing with a fake API."""
from datetime import datetime, timedelta
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from room_ac_control.secure_state import SecureState
from room_ac_control.timers import TimerBook
from room_ac_control.controller import Controller, ControlError
from tests.test_controller import make_device


def settings(on="08:00", off="22:00", repeat="daily", enabled=True):
    return {"on": {"time": on, "repeat": repeat, "enabled": enabled},
            "off": {"time": off, "repeat": repeat, "enabled": enabled}}


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.state = SecureState(persistent=False)
        self.book = TimerBook(self.state)
        self.now = datetime(2026, 10, 12, 7, 0)

    def test_daily_dispatch_persists_before_emit_and_never_duplicates(self):
        self.book.save("a", "room", settings(), self.now)
        event = self.book.poll("a", ["room"], self.now.replace(hour=8))
        self.assertEqual((event.device, event.action), ("room", "on"))
        entry = self.book.get("a", "room")["on"]
        self.assertEqual(entry["next"], "2026-10-13T08:00:00")
        reopened = TimerBook(self.state)
        self.assertIsNone(reopened.poll("a", ["room"], self.now.replace(hour=8)))
        reopened.finish("a", event, "failed")
        self.assertEqual(reopened.get("a", "room")["on"]["last_result"], "failed")
        self.assertIsNone(reopened.poll("a", ["room"], self.now.replace(hour=8, second=30)))

    def test_once_crosses_midnight_and_disables_after_consumption(self):
        self.book.save("a", "room", settings("00:15", "23:30", "once"), self.now.replace(hour=23))
        event = self.book.poll("a", ["room"], datetime(2026, 10, 13, 0, 15))
        self.assertEqual(event.action, "on")
        entries = self.book.get("a", "room")
        self.assertFalse(entries["on"]["enabled"])
        self.assertEqual(entries["off"]["last_result"], "missed")
        self.assertFalse(entries["off"]["enabled"])

    def test_late_wake_skips_both_actions_and_rolls_daily_forward(self):
        self.book.save("a", "room", settings(), self.now)
        self.assertIsNone(self.book.poll("a", ["room"], datetime(2026, 10, 15, 23)))
        for entry in self.book.get("a", "room").values():
            self.assertTrue(entry["enabled"])
            self.assertEqual(entry["last_result"], "missed")
            self.assertTrue(entry["next"].startswith("2026-10-16"))

    def test_busy_defers_briefly_then_expires_without_catchup(self):
        self.book.save("a", "room", settings(), self.now)
        due = self.now.replace(hour=8)
        self.assertIsNone(self.book.poll("a", ["room"], due, ready=False))
        self.assertIsNotNone(self.book.poll("a", ["room"], due + timedelta(seconds=45)))
        self.book.save("a", "second", settings(), self.now)
        self.assertIsNone(self.book.poll("a", ["second"], due + timedelta(seconds=61), ready=False))
        self.assertEqual(self.book.get("a", "second")["on"]["last_result"], "missed")

    def test_account_device_and_available_device_isolation(self):
        self.book.save("a", "room", settings(), self.now)
        self.book.save("b", "room", settings("09:00"), self.now)
        self.assertIsNone(self.book.poll("b", ["room"], self.now.replace(hour=8)))
        self.assertIsNone(self.book.poll("a", ["other"], self.now.replace(hour=8)))
        self.assertIsNotNone(self.book.poll("a", ["room"], self.now.replace(hour=8)))
        self.assertIsNone(self.book.poll("", ["room"], self.now.replace(hour=8)))

    def test_saving_unchanged_timers_preserves_due_and_invalid_forms_are_atomic(self):
        self.book.save("a", "room", settings(), self.now)
        before = self.book.get("a", "room")
        self.book.save("a", "room", settings(), self.now.replace(hour=8))
        self.assertEqual(before, self.book.get("a", "room"))
        for invalid in (settings("8:00"), settings("25:00"), settings("08:60"), settings("22:00"), settings(repeat="weekly")):
            with self.assertRaises(ValueError):
                self.book.save("a", "room", invalid, self.now)
        self.assertEqual(before, self.book.get("a", "room"))

    def test_failed_persistence_does_not_emit_or_advance_timer(self):
        self.book.save("a", "room", settings(), self.now)
        before = self.book.get("a", "room")
        with patch.object(self.state, "write", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                self.book.poll("a", ["room"], self.now.replace(hour=8))
        self.assertEqual(before, self.book.get("a", "room"))

    def test_disable_and_stale_completion_do_not_rearm_or_overwrite(self):
        self.book.save("a", "room", settings(), self.now)
        event = self.book.poll("a", ["room"], self.now.replace(hour=8))
        self.book.save("a", "room", settings("09:00", enabled=False), self.now)
        self.book.finish("a", event, "accepted")
        self.assertIsNone(self.book.poll("a", ["room"], self.now.replace(hour=23)))
        self.assertEqual(self.book.get("a", "room")["on"]["last_result"], "")

    def test_encrypted_schedules_survive_reopening_and_forgetting_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.dpapi"
            state = SecureState(path)
            TimerBook(state).save("fixture-account", "fixture-room", settings(), self.now)
            self.assertNotIn(b"fixture-room", path.read_bytes())
            state.forget_credentials()
            self.assertTrue(TimerBook(SecureState(path)).get("fixture-account", "fixture-room")["on"]["enabled"])


class TimerCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_timer_that_expired_while_waiting_for_worker_does_not_send(self):
        for action in ("on", "off"):
            device, api = make_device("0")
            controller = Controller()
            controller.devices[device.unique_id] = device
            due = (datetime.now() - timedelta(minutes=3)).isoformat()
            with self.assertRaisesRegex(ControlError, "missed"):
                await controller.timer_action(device.unique_id, action, due)
            self.assertEqual(api.sent, [])

    async def test_turn_on_and_off_use_supported_commands(self):
        device, api = make_device("0")
        controller = Controller()
        controller.devices[device.unique_id] = device
        await controller.timer_action(device.unique_id, "on")
        await controller.timer_action(device.unique_id, "off")
        self.assertEqual(api.sent, [("settings", {"onOffStatus": "1"}), ("stopProgram", {"onOffStatus": "0"})])
