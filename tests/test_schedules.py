"""Repeating schedules in hOn 2.30.7's record format, against fictional offline fixtures."""

import unittest
from datetime import UTC, datetime, timedelta

from room_ac_control.cloud_timers import CloudTimers, iso, select_timers, utc_time
from room_ac_control.controller import ControlError
from room_ac_control.schedules import (
    EVERY_DAY,
    Schedules,
    clock,
    conflicts,
    day_labels,
    next_occurrence,
    preview_record,
    record_days,
    schedule_dates,
    schedule_rows,
)
from tests.test_cloud_timers import FixtureHandler, fixture_device


def stamp(**delta):
    return iso(datetime.now(UTC) + timedelta(**delta))


def repeating(
    ident="repeat-1", days=(0, 1, 2, 3, 4), start="2026-01-05T06:00:00.000Z", end=None, active=True, offset=-60
):
    record = {
        "id": ident,
        "frequency": "weekly",
        "days": list(days),
        "isActive": active,
        "maintenance": False,
        "timezoneOffset": offset,
        "dateISOstart": start,
        "setupStart": {
            "commandName": "startProgram",
            "parameters": {"machMode": "4", "tempSel": "22.00", "onOffStatus": "1"},
        },
    }
    if end:
        record.update(dateISOend=end, setupEnd={"commandName": "stopProgram", "parameters": {"onOffStatus": "0"}})
    return record


class RecordTests(unittest.TestCase):
    def test_days_follow_hon_indexes_and_unfamiliar_repeats_are_not_editable(self):
        self.assertEqual(record_days({"frequency": "everyday"}), EVERY_DAY)
        self.assertEqual(record_days({"frequency": "weekly", "days": [4, 0, 2]}), (0, 2, 4))
        self.assertEqual(record_days({"frequency": "weekly", "days": ["5", "6"]}), (5, 6))
        self.assertEqual(record_days({"frequency": "weekly", "days": [7]}), ())
        self.assertEqual(record_days({"frequency": "weekly", "days": []}), ())
        self.assertEqual(record_days({"frequency": "weekly", "days": [True]}), ())
        self.assertEqual(record_days({"frequency": "monthly", "days": [1]}), None)
        self.assertEqual(record_days({"frequency": "once"}), None)

    def test_labels_name_common_sets(self):
        self.assertEqual(day_labels(EVERY_DAY), ["Every day"])
        self.assertEqual(day_labels((4, 3, 2, 1, 0)), ["Weekdays"])
        self.assertEqual(day_labels((5, 6)), ["Weekend"])
        self.assertEqual(day_labels((0, 2)), ["Mon", "Wed"])

    def test_clock_uses_the_record_offset(self):
        # Lisbon summer time: JavaScript offset -60, so 06:00Z is 07:00 local.
        self.assertEqual(
            clock({"dateISOstart": "2026-07-06T06:00:00.000Z", "timezoneOffset": -60}, "dateISOstart"), (7, 0)
        )
        self.assertEqual(
            clock({"dateISOstart": "2026-01-05T06:30:00.000Z", "timezoneOffset": 0}, "dateISOstart"), (6, 30)
        )
        self.assertIsNone(clock({"dateISOstart": "not a date"}, "dateISOstart"))

    def test_rows_list_upcoming_and_repeating_schedules_only(self):
        payload = {
            "scheduledPrograms": [
                repeating(end="2026-01-05T07:30:00.000Z"),
                repeating("paused", days=EVERY_DAY, active=False),
                {
                    "id": "past-once",
                    "frequency": "once",
                    "isActive": True,
                    "dateISOstart": stamp(hours=-2),
                    "setupStart": {"parameters": {}},
                },
                {
                    "id": "soon",
                    "frequency": "once",
                    "isActive": True,
                    "dateISOstart": stamp(hours=3),
                    "setupStart": {"parameters": {"machMode": "1", "silentSleepStatus": "1", "tempSel": "25.00"}},
                },
                {
                    "id": "monthly",
                    "frequency": "monthly",
                    "isActive": True,
                    "dateISOstart": stamp(hours=3),
                    "setupStart": {"parameters": {}},
                },
                {"id": "no-time", "frequency": "weekly", "days": [1], "isActive": True},
            ],
            "scheduleRunningProgramEnd": [],
            "scheduledProgramsMaintenance": [
                {
                    "id": "clean",
                    "maintenance": True,
                    "frequency": "weekly",
                    "days": [1],
                    "dateISOstart": stamp(hours=1),
                    "setupStart": {},
                }
            ],
        }
        rows = {row["id"]: row for row in schedule_rows(payload)}
        self.assertEqual(set(rows), {"repeat-1", "paused", "soon", "monthly"})
        self.assertEqual((rows["repeat-1"]["start"], rows["repeat-1"]["end"]), ((7, 0), (8, 30)))
        self.assertEqual((rows["repeat-1"]["mode"], rows["repeat-1"]["temperature"]), ("Heat", 22.0))
        self.assertFalse(rows["paused"]["active"])
        self.assertEqual(rows["soon"]["kind"], "once")
        self.assertEqual(rows["soon"]["mode"], "Cool Night")
        self.assertEqual(rows["monthly"]["kind"], "other")
        with self.assertRaises(ControlError):
            schedule_rows({"scheduledPrograms": {}})

    def test_conflicts_need_a_shared_day_and_the_same_time(self):
        rows = schedule_rows(
            {
                "scheduledPrograms": [
                    repeating(end="2026-01-05T21:00:00.000Z"),
                    repeating("paused", days=EVERY_DAY, active=False),
                ]
            }
        )
        found = conflicts(rows, (7, 0), None, (0, 6))
        self.assertEqual(
            [(item["row"]["id"], item["time"], item["days"]) for item in found], [("repeat-1", (7, 0), (0,))]
        )
        self.assertEqual(len(conflicts(rows, None, (22, 0), (0,))), 1)  # 21:00Z is 22:00 local.
        self.assertEqual(conflicts(rows, None, (21, 0), (0,)), [])
        self.assertEqual(len(conflicts(rows, (9, 0), (22, 0), (1,))), 1)
        self.assertEqual(conflicts(rows, (7, 0), None, (5, 6)), [])  # Weekend only.
        self.assertEqual(conflicts(rows, (7, 0), None, (0,), ignore="repeat-1"), [])  # Editing itself.

    def test_next_occurrence_and_hon_start_before_end_rule(self):
        now = datetime.now().astimezone().replace(second=0, microsecond=0)
        for days in ((0,), (6,), (2, 4), EVERY_DAY):
            due = next_occurrence(7, 15, days, now)
            self.assertIn(due.weekday(), days)
            self.assertEqual((due.hour, due.minute), (7, 15))
            self.assertTrue(now < due <= now + timedelta(days=7, hours=1))
        with self.assertRaises(ControlError):
            next_occurrence(7, 0, (), now)
        # A start later in the cycle than its end moves back one day, as in hOn.
        later = (now + timedelta(hours=2)).replace(minute=0)
        earlier = (now + timedelta(hours=1)).replace(minute=0)
        if later.date() == earlier.date() == now.date():
            due = schedule_dates((earlier.hour, 0), (later.hour, 0), EVERY_DAY, now)
            self.assertLess(due["on"], due["off"])
            # An overnight window: the start moves back to yesterday, before today's end.
            due = schedule_dates((later.hour, 0), (earlier.hour, 0), EVERY_DAY, now)
            self.assertEqual(due["on"].date(), now.date() - timedelta(days=1))
            self.assertTrue(timedelta(0) < due["off"] - due["on"] < timedelta(days=1))

    def test_preview_records_round_trip_through_the_list(self):
        record = preview_record("preview-1", (7, 0), (8, 30), (0, 1, 2, 3, 4), {"machMode": "4", "tempSel": "22"})
        row = schedule_rows({"scheduledPrograms": [record]})[0]
        self.assertEqual(
            (row["kind"], row["days"], row["start"], row["end"], row["mode"]),
            ("repeat", (0, 1, 2, 3, 4), (7, 0), (8, 30), "Heat"),
        )


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device, self.api = fixture_device()
        await self.device.update(force=True)
        self.handler = FixtureHandler()
        self.service = Schedules(CloudTimers(self.handler))

    async def test_create_weekly_schedule_in_hon_format_without_an_ac_command(self):
        result = await self.service.save(
            self.device, None, (7, 0), (8, 30), (0, 1, 2, 3, 4), {"machMode": "4", "tempSel": "22"}
        )
        self.assertTrue(result["saved"])
        method, url, body = self.handler.writes[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(
            (body["frequency"], body["days"], body["isActive"], body["maintenance"]),
            ("weekly", [0, 1, 2, 3, 4], True, False),
        )
        self.assertNotIn("scheduleEnd", body)
        self.assertEqual(body["setupStart"]["commandName"], "startProgram")
        self.assertEqual(body["setupStart"]["parameters"]["machMode"], "4")
        self.assertEqual(body["setupStart"]["parameters"]["tempSel"], "22.00")
        self.assertEqual(body["setupStart"]["parameters"]["onOffStatus"], "1")
        self.assertEqual(body["setupEnd"]["commandName"], "stopProgram")
        start, end = utc_time(body["dateISOstart"]), utc_time(body["dateISOend"])
        self.assertLess(start, end)
        self.assertIn(start.astimezone().weekday(), range(5))
        self.assertEqual(start.astimezone().strftime("%H:%M"), "07:00")
        self.assertEqual(body["timezoneOffset"], -int(start.astimezone().utcoffset().total_seconds() // 60))
        self.assertEqual([row["id"] for row in result["rows"]], ["fixture-new"])
        self.assertEqual(self.api.sent, [])  # Saved for later; the AC is not commanded now.

    async def test_every_day_uses_hons_everyday_frequency_and_end_only_is_allowed(self):
        await self.service.save(self.device, None, None, (23, 0), EVERY_DAY)
        body = self.handler.writes[-1][2]
        self.assertEqual((body["frequency"], body["days"]), ("everyday", list(EVERY_DAY)))
        self.assertNotIn("setupStart", body)
        self.assertEqual(body["setupEnd"]["parameters"]["onOffStatus"], "0")

    async def test_conflict_is_reported_before_writing_and_saved_when_confirmed(self):
        await self.service.save(self.device, None, (7, 0), None, (0,))
        writes = len(self.handler.writes)
        result = await self.service.save(self.device, None, None, (7, 0), (0, 1))
        self.assertFalse(result["saved"])
        self.assertEqual(result["conflicts"][0]["time"], (7, 0))
        self.assertEqual(len(self.handler.writes), writes)
        self.handler.payload["scheduledPrograms"][0]["id"] = "first"
        result = await self.service.save(self.device, None, None, (7, 0), (0, 1), allow_conflict=True)
        self.assertTrue(result["saved"])
        self.assertEqual(len(self.handler.writes), writes + 1)

    async def test_edit_switch_and_delete_existing_schedule(self):
        self.handler.payload["scheduledPrograms"] = [repeating(start=stamp(days=-3))]
        await self.service.save(self.device, "repeat-1", (6, 45), None, (5, 6))
        method, url, body = self.handler.writes[-1]
        self.assertEqual((method, url.rsplit("/", 1)[-1], body["days"]), ("PUT", "repeat-1", [5, 6]))
        rows = await self.service.set_active(self.device, "repeat-1", False)
        method, url, body = self.handler.writes[-1]
        self.assertEqual((method, body["isActive"], body["days"], body["frequency"]), ("PUT", False, [5, 6], "weekly"))
        self.assertIn("setupStart", body)
        self.assertFalse(rows[0]["active"])
        rows = await self.service.delete(self.device, "repeat-1")
        method, url, body = self.handler.writes[-1]
        self.assertEqual((method, body), ("DELETE", {"macAddress": self.device.mac_address, "maintenance": False}))
        self.assertEqual(rows, [])
        self.assertEqual(self.api.sent, [])

    async def test_end_timer_bucket_delete_keeps_scheduleEnd(self):
        self.handler.payload["scheduleRunningProgramEnd"] = [
            {
                "id": "end-1",
                "frequency": "once",
                "isActive": True,
                "scheduleEnd": True,
                "dateISOend": stamp(hours=2),
                "setupEnd": {"commandName": "stopProgram", "parameters": {"onOffStatus": "0"}},
            }
        ]
        await self.service.delete(self.device, "end-1")
        self.assertTrue(self.handler.writes[-1][2]["scheduleEnd"])

    async def test_missing_or_unsupported_schedules_and_unconfirmed_writes_are_reported(self):
        self.handler.payload["scheduledPrograms"] = [
            {
                "id": "monthly",
                "frequency": "monthly",
                "isActive": True,
                "dateISOstart": stamp(hours=3),
                "setupStart": {"parameters": {}},
            }
        ]
        for call in (
            self.service.save(self.device, "gone", (7, 0), None, (0,)),
            self.service.save(self.device, "monthly", (7, 0), None, (0,)),
            self.service.set_active(self.device, "monthly", False),
            self.service.delete(self.device, "gone"),
        ):
            with self.assertRaisesRegex(ControlError, "changed in hOn"):
                await call
        for bad in (((7, 0), None, ()), (None, None, (0,)), ((7, 0), (7, 0), (0,)), ((24, 0), None, (0,))):
            with self.assertRaises(ControlError):
                await self.service.save(self.device, None, *bad)
        self.assertEqual(self.handler.writes, [])
        self.handler.stale = True
        with self.assertRaisesRegex(ControlError, "not confirmed"):
            await self.service.save(self.device, None, (7, 0), None, (0,))

    async def test_one_time_timer_cards_still_ignore_repeating_schedules(self):
        await self.service.save(self.device, None, (7, 0), (8, 0), EVERY_DAY)
        state, _ = select_timers(self.handler.payload)
        self.assertTrue(state["on"]["supported"] and state["off"]["supported"])
        self.assertEqual((state["on"]["count"], state["off"]["count"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
