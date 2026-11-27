"""Sending a command from the dashboard: which notifications it keeps quiet."""

import unittest

from room_ac_control.dashboard.status import StatusMixin
from room_ac_control.worker import UNKNOWN_OUTCOME


class Text:
    def set(self, value):
        self.value = value


class FakeWorker:
    """Keeps the submitted operation; nothing reaches a cloud service."""

    def __init__(self):
        self.controller = self
        self.submitted = None

    async def action(self, device_id, action, requested):
        return "Command accepted by the cloud service."

    def submit(self, coroutine, callback, operation, on_error=None):
        coroutine.close()
        self.submitted = (callback, operation, on_error)


class Dashboard(StatusMixin):
    def __init__(self):
        self.busy, self.demo = False, False
        self.selected = {"id": "fixture-ac", "controls": {"tempSel": {}}}
        self.dirty = {"tempSel": "24"}
        self.pending_changes = {}
        self.own_change_until = {}
        self.refresh_epoch, self.auto_inflight = 0, False
        self.status = Text()
        self.worker = FakeWorker()
        self.errors = []

    def set_busy(self, value):
        self.busy = value

    def show_error(self, text):
        self.errors.append(text)


class CommandNotificationTests(unittest.TestCase):
    def send(self):
        app = Dashboard()
        app.action("apply")
        self.assertIn("fixture-ac", app.own_change_until)  # Its own change is not news.
        _, operation, failed = app.worker.submitted
        self.assertEqual(operation, "command")
        return app, failed

    def test_a_refused_command_lets_power_changes_be_announced_again(self):
        app, failed = self.send()
        failed("The AC is off. Use Turn on with these settings.")
        self.assertNotIn("fixture-ac", app.own_change_until)
        self.assertEqual(app.errors, ["The AC is off. Use Turn on with these settings."])

    def test_a_command_with_an_unknown_outcome_stays_quiet(self):
        app, failed = self.send()
        text = "Could not reach the cloud service. Check internet access and try again." + UNKNOWN_OUTCOME
        failed(text)
        self.assertIn("fixture-ac", app.own_change_until)  # It may still have reached the AC.
        self.assertEqual(app.errors, [text])


if __name__ == "__main__":
    unittest.main()
