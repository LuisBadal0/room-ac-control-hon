"""Turbo cannot run with Silent mode or Sleep, and a fan speed choice ends it (hOn 2.32.11)."""

import unittest

from room_ac_control.ac_model import turbo_conflicts

CONTROLS = {"rapidMode": {}, "muteStatus": {}, "silentSleepStatus": {}, "windSpeed": {}}


def reader(**values):
    return lambda name: values.get(name)


class TurboRuleTests(unittest.TestCase):
    def test_turbo_on_turns_off_silent_mode_and_sleep_that_are_on(self):
        changes, notice = turbo_conflicts("rapidMode", "1", reader(muteStatus="1", silentSleepStatus="1.0"), CONTROLS)
        self.assertEqual(changes, {"muteStatus": "0", "silentSleepStatus": "0"})
        self.assertEqual(notice, "Turbo turns off Silent mode and Sleep.")

    def test_silent_mode_sleep_and_fan_speed_each_turn_off_turbo(self):
        for key, value, notice in (
            ("muteStatus", "1", "Silent mode turns off Turbo."),
            ("silentSleepStatus", "1", "Sleep turns off Turbo."),
            ("windSpeed", "3", "Choosing a fan speed turns off Turbo."),
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    turbo_conflicts(key, value, reader(rapidMode="1"), CONTROLS), ({"rapidMode": "0"}, notice)
                )

    def test_nothing_changes_when_the_other_switches_are_already_off(self):
        self.assertEqual(turbo_conflicts("rapidMode", "1", reader(muteStatus="0"), CONTROLS), ({}, None))
        self.assertEqual(turbo_conflicts("windSpeed", "1", reader(rapidMode="0"), CONTROLS), ({}, None))

    def test_turning_a_switch_off_or_another_setting_has_no_side_effects(self):
        on = reader(rapidMode="1", muteStatus="1", silentSleepStatus="1")
        for key, value in (("rapidMode", "0"), ("muteStatus", "0"), ("silentSleepStatus", "0"), ("tempSel", "22")):
            with self.subTest(key=key):
                self.assertEqual(turbo_conflicts(key, value, on, CONTROLS), ({}, None))

    def test_switches_this_ac_does_not_have_are_left_alone(self):
        changes, notice = turbo_conflicts(
            "rapidMode", "1", reader(muteStatus="1", silentSleepStatus="1"), {"rapidMode": {}, "muteStatus": {}}
        )
        self.assertEqual(changes, {"muteStatus": "0"})
        self.assertEqual(notice, "Turbo turns off Silent mode and Sleep.")


if __name__ == "__main__":
    unittest.main()
