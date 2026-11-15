"""Room temperature history kept on this computer, and the chart's helpers. Offline fixtures."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from room_ac_control.functions_view.history_sheet import scale, segments, ticks
from room_ac_control.program_memory import ProgramMemory
from room_ac_control.room_history import EVERY, KEEP, RoomHistory, reading, summary, valid
from room_ac_control.secure_state import SecureState

NOW = 1_800_000_000


def snapshot(room=23.5, power="On", **extra):
    return {"id": "fixture-ac", "room": room, "target": 22, "power": power, **extra}


class ReadingTests(unittest.TestCase):
    def test_reading_keeps_the_values_the_dashboard_shows(self):
        row = reading(snapshot(sensors={"outdoor": 31, "humidity": 55}), NOW)
        self.assertEqual(row, [NOW, 23.5, 31.0, 55.0, 22.0, 1])

    def test_outside_comes_from_the_weather_without_an_outdoor_sensor(self):
        row = reading(snapshot(power="Off", weather={"temperature": 18.4, "humidity": 70}), NOW)
        self.assertEqual(row[2:4], [18.4, 70.0])
        self.assertEqual(row[5], 0)

    def test_no_room_temperature_means_no_reading(self):
        for room in (None, "", "n/a", float("nan"), 99, True):
            self.assertIsNone(reading(snapshot(room=room), NOW), room)

    def test_valid_refuses_damaged_rows(self):
        self.assertTrue(valid([NOW, 23.0, None, None, 22.0, 1]))
        for row in ([NOW, 23.0], ["x", 23.0, None, None, None, 1], [NOW, "23", None, None, None, 1], {}, None):
            self.assertFalse(valid(row), row)


class HistoryTests(unittest.TestCase):
    def test_one_reading_every_ten_minutes_for_seven_days(self):
        history = RoomHistory(persistent=False)
        self.assertTrue(history.record("account", "ac", snapshot(), now=NOW))
        self.assertFalse(history.record("account", "ac", snapshot(), now=NOW + EVERY - 1))
        self.assertTrue(history.record("account", "ac", snapshot(room=24), now=NOW + EVERY))
        self.assertFalse(history.record("", "ac", snapshot(), now=NOW + 2 * EVERY))
        self.assertFalse(history.record("account", "ac", snapshot(room=None), now=NOW + 2 * EVERY))
        later = NOW + KEEP + EVERY // 2
        self.assertTrue(history.record("account", "ac", snapshot(room=25), now=later))
        rows = history.readings("account", "ac", 24 * 8, now=later)
        self.assertEqual([row["room"] for row in rows], [24.0, 25.0])
        self.assertEqual([row["room"] for row in history.readings("account", "ac", 1, now=later)], [25.0])
        self.assertEqual(history.readings("other", "ac", 24, now=later), [])

    def test_readings_survive_a_restart_encrypted_and_damaged_files_start_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.dpapi"
            RoomHistory(path).record("account", "ac", snapshot(), now=NOW)
            self.assertNotIn(b"23.5", path.read_bytes())
            self.assertEqual(len(RoomHistory(path).readings("account", "ac", 24, now=NOW)), 1)
            path.write_bytes(b"not encrypted")
            with patch("room_ac_control.room_history.diagnostics") as diagnostics:
                self.assertEqual(RoomHistory(path).data, {})
            diagnostics.record.assert_called_once()

    def test_memory_records_for_the_signed_in_account_and_survives_write_failures(self):
        history = RoomHistory(persistent=False)
        memory = ProgramMemory(SecureState(persistent=False), history)
        memory.use_account("fixture@example.test")
        memory.record_reading(snapshot())
        self.assertEqual(len(memory.readings("fixture-ac", 1)), 1)
        history.write = Mock(side_effect=OSError("fixture"))
        history.data.clear()
        memory.record_reading(snapshot())  # Logged, not raised: the dashboard keeps working.
        self.assertEqual(ProgramMemory(SecureState(persistent=False)).readings("fixture-ac", 1), [])

    def test_summary(self):
        rows = [{"room": 22.0}, {"room": None}, {"room": 25.0}, {"room": 23.6}]
        self.assertEqual(summary(rows), {"low": 22.0, "high": 25.0, "average": 23.5})
        self.assertIsNone(summary([{"room": None}]))


class ChartTests(unittest.TestCase):
    def test_lines_break_where_readings_stop(self):
        rows = [
            {"time": 0, "room": 22.0},
            {"time": EVERY, "room": 22.5},
            {"time": 10 * EVERY, "room": 23.0},  # The app was closed in between.
            {"time": 11 * EVERY, "room": None},
            {"time": 12 * EVERY, "room": 23.5},
            {"time": 13 * EVERY, "room": 24.0},
        ]
        self.assertEqual(segments(rows, "room"), [[(0, 22.0), (EVERY, 22.5)], [(12 * EVERY, 23.5), (13 * EVERY, 24.0)]])

    def test_scale_spans_at_least_four_degrees_around_room_and_outside(self):
        self.assertEqual(scale([{"room": 23.2, "outside": None}, {"room": 23.8, "outside": None}]), (21, 26))
        self.assertEqual(scale([{"room": 22.5, "outside": 31.2}]), (22, 32))

    def test_ticks_fall_on_six_hours_for_a_day_and_midnight_for_a_week(self):
        end = datetime(2026, 11, 15, 14, 20).timestamp()
        day = [datetime.fromtimestamp(moment).hour for moment in ticks(end - 24 * 3600, end, 24)]
        self.assertEqual(day, [18, 0, 6, 12])
        week = [datetime.fromtimestamp(moment) for moment in ticks(end - 7 * 24 * 3600, end, 168)]
        self.assertEqual(len(week), 7)
        self.assertTrue(all(moment.hour == 0 and moment.minute == 0 for moment in week))


if __name__ == "__main__":
    unittest.main()
