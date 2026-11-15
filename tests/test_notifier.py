"""Which reported changes become Windows notifications. Offline snapshots only."""

import unittest
from datetime import datetime, timedelta

from room_ac_control.i18n import Translator
from room_ac_control.notifier import changes, text
from room_ac_control.secure_state import SecureState

NOW = datetime(2026, 11, 15, 23, 0)


def snapshot(**values):
    base = {"id": "fixture-ac", "name": "Bedroom", "power": "On", "connection": "CONNECTED", "alerts": []}
    return {**base, **values}


def timers(action, due):
    return {"available": True, "values": {action: {"due": due, "supported": True}}}


class ChangeTests(unittest.TestCase):
    def titles(self, previous, current, **options):
        return [(item["title"], item["message"]) for item in changes(previous, current, now=NOW, **options)]

    def test_nothing_without_an_earlier_snapshot_or_a_change(self):
        self.assertEqual(changes(None, snapshot()), [])
        self.assertEqual(changes(snapshot(), snapshot(), now=NOW), [])
        self.assertEqual(changes(snapshot(id="other"), snapshot(power="Off"), now=NOW), [])

    def test_new_errors_filter_and_offline(self):
        current = snapshot(
            alerts=[{"kind": "error", "code": "E5"}, {"kind": "error", "code": "E1"}, {"kind": "filter"}],
            connection="DISCONNECTED",
        )
        result = changes(snapshot(alerts=[{"kind": "error", "code": "E1"}]), current, now=NOW)
        self.assertEqual([item["code"] for item in result if item["title"] == "{name}: AC error"], ["E5"])
        self.assertIn("{name}: clean the air filter", [item["title"] for item in result])
        self.assertIn("{name} is offline", [item["title"] for item in result])
        # A filter reminder already shown is not repeated.
        self.assertEqual(changes(current, current, now=NOW), [])

    def test_power_changes_name_a_due_timer(self):
        off = snapshot(power="Off")
        self.assertEqual(
            self.titles(snapshot(timers=timers("off", NOW - timedelta(minutes=3))), off),
            [("{name} turned off", "Turned off by its End at timer.")],
        )
        self.assertEqual(
            self.titles(snapshot(timers=timers("off", NOW - timedelta(hours=2))), off),
            [("{name} turned off", "Turned off outside this app.")],
        )
        self.assertEqual(
            self.titles(off.copy() | {"timers": timers("on", NOW + timedelta(minutes=1))}, snapshot()),
            [("{name} turned on", "Turned on by its start timer.")],
        )
        self.assertEqual(self.titles(off, snapshot()), [("{name} turned on", "Turned on outside this app.")])
        self.assertEqual(self.titles(snapshot(power="Unknown"), off), [])

    def test_this_apps_own_command_is_not_announced(self):
        self.assertEqual(self.titles(snapshot(), snapshot(power="Off"), own_power_change=True), [])

    def test_text_is_translated_with_the_name_and_code(self):
        [item] = changes(snapshot(), snapshot(alerts=[{"kind": "error", "code": "E7"}]), now=NOW)
        self.assertEqual(
            text(Translator("en"), item), ("Bedroom: AC error", "The AC reports error E7. Check it in the hOn app.")
        )
        self.assertEqual(
            text(Translator("pt-PT"), item), ("Bedroom: erro do AC", "O AC comunica o erro E7. Verifique-o na app hOn.")
        )
        [item] = changes(snapshot(), snapshot(power="Off"), now=NOW)
        self.assertEqual(text(Translator("pt-PT"), item), ("Bedroom desligou-se", "Desligado fora desta app."))


class PreferenceTests(unittest.TestCase):
    def test_notifications_are_on_by_default_and_a_failed_write_rolls_back(self):
        state = SecureState(persistent=False)
        self.assertTrue(state.notifications())
        state.save_notifications(False)
        self.assertFalse(state.notifications())
        state.data["notifications"] = "yes"
        self.assertTrue(state.notifications())
        with self.assertRaises(ValueError):
            state.save_notifications("no")
        state.data.pop("notifications")

        def fail():
            raise OSError("fixture")

        state.write = fail
        with self.assertRaises(OSError):
            state.save_notifications(False)
        self.assertNotIn("notifications", state.data)


if __name__ == "__main__":
    unittest.main()
