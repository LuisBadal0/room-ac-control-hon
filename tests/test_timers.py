"""Offline one-time wall-clock selection, including overnight rollover."""
from datetime import datetime
from types import SimpleNamespace
import tkinter as tk
import unittest
from room_ac_control.inline_timers import NumberWheel, next_time


class TimeSelectionTests(unittest.TestCase):
    def test_later_today_and_overnight_use_the_next_occurrence(self):
        now = datetime(2026, 10, 13, 23, 45)
        self.assertEqual(next_time(23, 50, now), datetime(2026, 10, 13, 23, 50))
        self.assertEqual(next_time(0, 15, now), datetime(2026, 10, 14, 0, 15))
        self.assertEqual(next_time(23, 45, now), datetime(2026, 10, 14, 23, 45))

    def test_time_bounds_reject_invalid_hour_and_minute(self):
        for hour, minute in ((-1, 0), (24, 0), (0, -1), (0, 60)):
            with self.assertRaises(ValueError):
                next_time(hour, minute)


class WheelDragTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.changes = []
        self.wheel = NumberWheel(self.root, 24, 8, lambda: self.changes.append(self.wheel.value))

    def tearDown(self):
        self.root.destroy()

    def event(self, y):
        return SimpleNamespace(y=y, y_root=100+y)

    def test_drag_up_advances_and_down_reverses_with_live_offset(self):
        self.wheel.press(self.event(32))
        self.wheel.drag(self.event(6))
        self.assertEqual(self.wheel.value, 9)
        self.assertEqual(self.wheel.drag_offset, -4)
        self.wheel.drag(self.event(58))
        self.assertEqual(self.wheel.value, 7)
        self.wheel.release(self.event(58))
        self.assertEqual(self.wheel.value, 7)
        self.assertEqual(self.wheel.drag_offset, 0)
        self.assertIsNone(self.wheel.drag_state)

    def test_fast_release_wraps_and_snaps_without_motion_events(self):
        self.wheel.value = 23
        self.wheel.press(self.event(32))
        self.wheel.release(self.event(-24))  # 2.55 rows, snapped to three.
        self.assertEqual(self.wheel.value, 2)
        self.wheel.limit, self.wheel.value = 60, 0
        self.wheel.press(self.event(32))
        self.wheel.release(self.event(48))
        self.assertEqual(self.wheel.value, 59)

    def test_small_jitter_keeps_click_behavior_without_double_steps(self):
        self.wheel.press(self.event(10))
        self.wheel.release(self.event(12))
        self.assertEqual(self.changes, [7])
        self.wheel.press(self.event(54))
        self.wheel.drag(self.event(32))
        self.wheel.release(self.event(32))
        self.assertEqual(self.wheel.value, 8)  # Drag adds one, with no click.
        self.wheel.press(self.event(32))
        self.wheel.release(self.event(33))
        self.assertEqual(self.wheel.value, 8)

    def test_busy_transition_cancels_drag_and_release_cannot_change_values(self):
        self.wheel.press(self.event(32))
        self.wheel.drag(self.event(10))
        self.wheel.enabled = False
        self.wheel.draw()
        before = self.wheel.value
        self.wheel.release(self.event(-50))
        self.wheel.press(self.event(32))
        self.assertEqual(self.wheel.value, before)
        self.assertIsNone(self.wheel.drag_state)
