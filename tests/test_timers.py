"""Offline one-time wall-clock selection, including overnight rollover."""
from datetime import datetime
import unittest
from room_ac_control.inline_timers import next_time


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
