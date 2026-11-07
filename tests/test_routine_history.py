"""When maintenance routines last ran, from offline fixtures shaped like hOn's command history."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest

from pyhon.commands import HonCommand

from room_ac_control.controller import Controller, describe
from room_ac_control.program_memory import ProgramMemory
from room_ac_control.routine_history import (day_to_time, item_routine, last_run_text, parse_day, running_programs,
                                             runs_from_history)
from room_ac_control.secure_state import SecureState
from tests.test_controller import make_device

UTC = timezone.utc


def entry(when, program=None, command="startProgram", **parameters):
    """One fake history entry; hOn's real ones also carry account and device identifiers."""
    body = {"commandName": command, "timestamp": when, "parameters": {"onOffStatus": "1", **parameters},
            "attributes": {"channel": "mobileApp", "origin": "standardProgram"}}
    if program:
        body["programName"] = f"PROGRAMS.AC.{program.upper()}"
    return {"SK_Secondary": f"cmdHistory#{when}", "command": body}


class HistoryTests(unittest.TestCase):
    def test_self_clean_starts_are_found_and_the_latest_is_kept(self):
        history = [
            entry("2026-11-07T02:26:10.894Z", "iot_heat", selfCleaningStatus="0"),
            entry("2026-11-01T09:00:00.000Z", "iot_self_clean", selfCleaningStatus="1"),
            entry("2026-10-20T09:00:00.000Z", "iot_self_clean"),
            entry("2026-10-28T21:15:00.000Z", None, "settings", selfCleaning56Status="1"),
            entry("2026-10-29T08:00:00.000Z", "iot_self_clean_56"),
            entry("2026-10-10T08:00:00.000Z", "iot_sterilization"),
        ]
        self.assertEqual(runs_from_history(history), {
            "selfCleaningStatus": datetime(2026, 11, 1, 9, tzinfo=UTC),
            "selfCleaning56Status": datetime(2026, 10, 29, 8, tzinfo=UTC),
            "startProgram:iot_sterilization": datetime(2026, 10, 10, 8, tzinfo=UTC),
        })

    def test_everyday_presets_switching_off_and_malformed_entries_are_ignored(self):
        timeless = entry("", "iot_self_clean")
        timeless["SK_Secondary"] = "cmdHistory#"
        history = [entry("2026-11-07T02:26:10Z", "iot_heat"), entry("2026-11-06T02:26:10Z", None, "settings", selfCleaningStatus="0"),
                   timeless, {"command": "startProgram"}, "broken", None]
        self.assertEqual(runs_from_history(history), {})
        self.assertEqual(runs_from_history(None), {})

    def test_the_switch_and_the_program_share_one_routine(self):
        switch = {"kind": "setting", "key": "selfCleaningStatus"}
        program = {"kind": "function", "command": "startProgram", "form": {"category": "iot_self_clean"}}
        program_56 = {"kind": "function", "command": "startProgram", "form": {"category": "iot_self_clean_56"}}
        self.assertEqual(item_routine(switch), item_routine(program))
        self.assertEqual(item_routine(program_56), "selfCleaning56Status")

    def test_elapsed_time_wording(self):
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        ago = lambda **delta: last_run_text(now-timedelta(**delta), now)
        self.assertEqual(last_run_text(None, now), ("No run recorded yet", {}))
        self.assertEqual(ago(seconds=20), ("Last run just now", {}))
        self.assertEqual(ago(minutes=42), ("Last run {count} min ago", {"count": 42}))
        self.assertEqual(ago(hours=1, minutes=5), ("Last run 1 hour ago", {}))
        self.assertEqual(ago(hours=5), ("Last run {count} hours ago", {"count": 5}))
        self.assertEqual(ago(days=1, hours=3), ("Last run yesterday", {}))
        self.assertEqual(ago(days=12, hours=3), ("Last run {count} days ago", {"count": 12}))
        self.assertEqual(last_run_text(now+timedelta(minutes=5), now), ("Last run just now", {}))
        # Older runs show their date: 6 December 2025 is about 11 months before.
        december = datetime(2025, 12, 6, 12, tzinfo=UTC)
        self.assertEqual(last_run_text(december, now), ("Last run on {date}", {"date": december}))

    def test_typed_dates_are_day_first_and_never_in_the_future(self):
        from datetime import date
        today = date(2026, 11, 7)
        for text in ("06/12/2025", "6/12/2025", "06-12-2025", "06.12.2025", " 06 12 2025 ", "6/12/25"):
            self.assertEqual(parse_day(text, today), date(2025, 12, 6), text)
        self.assertEqual(parse_day("07/11/2026", today), today)
        for text in ("", "12/31/2025", "08/11/2026", "31/02/2025", "01/01/1999", "yesterday", "06/12"):
            self.assertIsNone(parse_day(text, today), text)
        # A chosen day is stored as local midday, so it shows as that day in any time zone offset.
        self.assertEqual(day_to_time(date(2025, 12, 6)).astimezone().date(), date(2025, 12, 6))

    def test_a_running_self_clean_program_counts_only_while_the_ac_is_on(self):
        snapshot = {"power": "On", "program": "PROGRAMS.AC.IOT_SELF_CLEAN_56"}
        self.assertEqual(running_programs(snapshot), ["selfCleaning56Status"])
        self.assertEqual(running_programs(dict(snapshot, power="Off")), [])
        self.assertEqual(running_programs({"power": "On", "program": "PROGRAMS.AC.IOT_HEAT"}), [])
        self.assertEqual(running_programs({"power": "On", "program": None}), [])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.memory = ProgramMemory(SecureState(persistent=False))
        self.memory.use_account("sample@example.test")

    def test_later_runs_replace_earlier_ones_per_account_and_unit(self):
        early, late = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": late})
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": early, "selfCleaning56Status": early})
        self.assertEqual(self.memory.routine_runs("unit"), {"selfCleaningStatus": late, "selfCleaning56Status": early})
        self.assertEqual(self.memory.routine_runs("other-unit"), {})
        self.memory.use_account("other@example.test")
        self.assertEqual(self.memory.routine_runs("unit"), {})

    def test_malformed_saved_runs_are_ignored(self):
        state = self.memory.state
        state.data["routine_runs"] = {self.memory.account: {"unit": {"selfCleaningStatus": "not a time", "x": 3}}}
        self.assertEqual(self.memory.routine_runs("unit"), {})
        state.data["routine_runs"] = {self.memory.account: {"unit": ["broken"]}}
        self.assertEqual(self.memory.routine_runs("unit"), {})
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": datetime(2026, 11, 1, tzinfo=UTC)})
        self.assertIn("selfCleaningStatus", self.memory.routine_runs("unit"))

    def test_a_date_set_by_hand_replaces_a_later_one(self):
        later, entered = datetime(2026, 11, 1, tzinfo=UTC), datetime(2025, 12, 6, 12, tzinfo=UTC)
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": later})
        self.memory.set_routine_run("unit", "selfCleaningStatus", entered)
        self.assertEqual(self.memory.routine_runs("unit"), {"selfCleaningStatus": entered})
        self.assertFalse(self.memory.save_error)
        # A newer run seen later still replaces the date that was entered.
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": later})
        self.assertEqual(self.memory.routine_runs("unit")["selfCleaningStatus"], later)

    def test_a_failed_write_is_reported_not_raised(self):
        def denied():
            raise OSError("test access failure")
        self.memory.state.write = denied
        self.memory.record_routine_runs("unit", {"selfCleaningStatus": datetime(2026, 11, 1, tzinfo=UTC)})
        self.assertTrue(self.memory.save_error)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI required")
    def test_runs_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"state.dpapi"
            when = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
            SecureState(path).record_routine_runs("account", "unit", {"selfCleaningStatus": when})
            self.assertEqual(SecureState(path).routine_runs("account", "unit"), {"selfCleaningStatus": when.isoformat()})


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.memory = ProgramMemory(SecureState(persistent=False))
        self.memory.use_account("sample@example.test")
        self.device, self.api = make_device()
        categories = {}
        for name in ("iot_heat", "iot_self_clean"):
            categories[name] = HonCommand("startProgram", {"parameters": {
                "onOffStatus": {"typology": "fixed", "fixedValue": "1"},
                "selfCleaningStatus": {"typology": "fixed", "fixedValue": "1" if "clean" in name else "0"},
            }}, self.device, categories=categories, category_name="PROGRAM."+name.upper())
        self.device.commands["startProgram"] = categories["iot_heat"]
        await self.device.update(force=True)
        self.controller = Controller(memory=self.memory)
        self.controller.devices[self.device.unique_id] = self.device
        self.unit = self.device.unique_id

    async def test_starting_a_self_clean_here_records_it_and_a_heat_preset_does_not(self):
        await self.controller.action(self.unit, "execute", {"command": "startProgram", "category": "iot_heat", "parameters": {}})
        self.assertEqual(self.memory.routine_runs(self.unit), {})
        before = datetime.now(UTC)
        await self.controller.action(self.unit, "execute", {"command": "startProgram", "category": "iot_self_clean", "parameters": {}})
        self.assertGreaterEqual(self.memory.routine_runs(self.unit)["selfCleaningStatus"], before)

    async def test_a_self_clean_switch_reported_on_counts_as_a_run(self):
        self.controller.remember(describe(self.device))
        self.assertEqual(self.memory.routine_runs(self.unit), {})
        snapshot = describe(self.device)
        snapshot["controls"]["selfCleaningStatus"] = {"key": "selfCleaningStatus", "value": "1", "reported": True}
        self.controller.remember(snapshot)
        self.assertIn("selfCleaningStatus", self.memory.routine_runs(self.unit))

    async def test_a_self_clean_program_reported_running_counts_as_a_run(self):
        snapshot = describe(self.device)
        snapshot.update(power="On", program="PROGRAMS.AC.IOT_SELF_CLEAN")
        self.controller.remember(snapshot)
        self.assertIn("selfCleaningStatus", self.memory.routine_runs(self.unit))

    async def test_history_is_read_without_sending_commands(self):
        async def history(device):
            return [entry("2026-11-01T09:00:00Z", "iot_self_clean")]
        self.api.load_command_history = history
        self.controller.api = self.api
        runs = await self.controller.routine_history(self.unit)
        self.assertEqual(runs, {"selfCleaningStatus": datetime(2026, 11, 1, 9, tzinfo=UTC)})
        self.assertEqual(self.api.sent, [])


if __name__ == "__main__":
    unittest.main()
