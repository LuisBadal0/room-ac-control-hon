"""Native timer protocol exercised only against fictional offline fixtures."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyhon.commands import HonCommand
from room_ac_control.cloud_timers import CloudTimers, BASE, iso, select_timers
from room_ac_control.controller import ControlError, Controller
from tests.test_controller import make_device


def fixture_device():
    device, api = make_device()
    variant = HonCommand("startProgram", {"parameters": deepcopy({
        k: p._attributes for k, p in device.commands["settings"].settings.items()})}, device)
    variant.settings["onOffStatus"].value = "1"
    base = HonCommand("startProgram", {}, device, categories={"iot_simple_start": variant})
    device.commands["startProgram"] = base
    return device, api


def record(action="off", ident="fixture-1", paired=False):
    result = {"id": ident, "frequency": "once", "isActive": True, "scheduledProgram": None}
    for a in ("on", "off") if paired else (action,):
        result["dateISOstart" if a == "on" else "dateISOend"] = iso(datetime.now(timezone.utc) + timedelta(hours=3 if a == "on" else 4))
        result["setupStart" if a == "on" else "setupEnd"] = {"commandName": "startProgram" if a == "on" else "stopProgram", "parameters": {"onOffStatus": "1" if a == "on" else "0"}}
    return result


class Response:
    def __init__(self, data, status=200): self.data, self.status = data, status
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return deepcopy(self.data)


class FixtureHandler:
    def __init__(self, records=None):
        self.payload = {"scheduledPrograms": [], "scheduleRunningProgramEnd": [], "scheduledProgramsMaintenance": []}
        self.payload.update(deepcopy(records or {}))
        self.calls, self.writes = [], []
        self.device = SimpleNamespace(get=lambda mobile: {"mobileId": "fictional-mobile"})
        self.session = SimpleNamespace(put=self.put, delete=self.delete)
        self.status, self.stale = 200, False
    def get(self, url):
        self.calls.append(("GET", url, None))
        return Response({"payload": self.payload}, self.status)
    def write(self, method, url, json):
        self.calls.append((method, url, deepcopy(json)))
        self.writes.append(self.calls[-1])
        if not self.stale and self.status == 200:
            if method == "POST":
                bucket = "scheduleRunningProgramEnd" if json.get("scheduleEnd") else "scheduledPrograms"
                self.payload[bucket].append({**deepcopy(json), "id": "fixture-new"})
            else:
                ident = url.rsplit("/", 1)[-1]
                for bucket in ("scheduledPrograms", "scheduleRunningProgramEnd"):
                    for index, item in enumerate(list(self.payload[bucket])):
                        if item["id"] == ident:
                            if method == "DELETE": self.payload[bucket].remove(item)
                            else: self.payload[bucket][index] = {**deepcopy(json), "id": ident}
        return Response({"payload": {"resultCode": "0"}}, self.status)
    def post(self, url, json): return self.write("POST", url, json)
    def put(self, url, json): return self.write("PUT", url, json)
    def delete(self, url, json): return self.write("DELETE", url, json)
    def _intercept(self, method, url, **kwargs): return method(url, **kwargs)


class NativeTimerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device, self.api = fixture_device()
        await self.device.update(force=True)
        self.handler = FixtureHandler()
        self.service = CloudTimers(self.handler)
        self.due = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=2)

    async def test_start_persists_settings_without_immediate_ac_command(self):
        before = self.device.commands["startProgram"].categories["iot_simple_start"].parameter_groups
        result = await self.service.change(self.device, "on", self.due, None, {"tempSel": "26", "machMode": "4", "silentSleepStatus": "1"})
        self.assertEqual(self.api.sent, [])
        method, url, body = self.handler.writes[0]
        self.assertEqual((method, url), ("POST", BASE))
        self.assertEqual(body["frequency"], "once")
        self.assertNotIn("setupEnd", body)
        self.assertNotIn("scheduleEnd", body)
        self.assertEqual(body["setupStart"]["commandName"], "startProgram")
        params = body["setupStart"]["parameters"]
        self.assertEqual((str(params["tempSel"]), params["machMode"], params["silentSleepStatus"]), ("26.00", "4", "1"))
        self.assertEqual(before, self.device.commands["startProgram"].categories["iot_simple_start"].parameter_groups)
        self.assertEqual(result["on"]["due"], self.due)
        # A new client reads the persisted cloud record; no PC schedule database.
        fresh, _ = await CloudTimers(self.handler).read(self.device)
        self.assertEqual(fresh["on"], result["on"])

    async def test_end_only_create_and_cancel_use_native_schedule_flag_and_id(self):
        state = await self.service.change(self.device, "off", self.due, None)
        body = self.handler.writes[0][2]
        self.assertTrue(body["scheduleEnd"])
        self.assertNotIn("setupStart", body)
        self.assertEqual(body["setupEnd"]["parameters"]["onOffStatus"], "0")
        state = await self.service.change(self.device, "off", None, state["off"]["expected"])
        method, url, body = self.handler.writes[1]
        self.assertEqual((method, url), ("DELETE", BASE + "/fixture-new"))
        self.assertEqual(body, {"macAddress": "test-device", "maintenance": False, "scheduleEnd": True})
        self.assertIsNone(state["off"]["due"])
        self.assertEqual(self.api.sent, [])

    async def test_existing_phone_end_timer_is_read_and_updated_in_place(self):
        original = record()
        self.handler.payload["scheduleRunningProgramEnd"] = [original]
        state, _ = await self.service.read(self.device)
        self.assertIsNotNone(state["off"]["due"])
        await self.service.change(self.device, "off", self.due, state["off"]["expected"])
        self.assertEqual(self.handler.writes[0][:2], ("PUT", BASE + "/fixture-1"))
        self.assertEqual(len(self.handler.payload["scheduleRunningProgramEnd"]), 1)

    async def test_paired_stop_preserves_the_other_timer_and_its_parameters(self):
        original = record(paired=True)
        self.handler.payload["scheduledPrograms"] = [original]
        state, _ = await self.service.read(self.device)
        result = await self.service.change(self.device, "on", None, state["on"]["expected"])
        method, _, body = self.handler.writes[0]
        self.assertEqual(method, "PUT")
        self.assertNotIn("dateISOstart", body)
        self.assertNotIn("setupStart", body)
        self.assertEqual(body["dateISOend"], original["dateISOend"])
        self.assertEqual(body["setupEnd"], original["setupEnd"])
        self.assertIsNone(result["on"]["due"])
        self.assertEqual(result["off"]["expected"], state["off"]["expected"])

    async def test_stale_identity_and_conflicting_timers_never_write(self):
        self.handler.payload["scheduleRunningProgramEnd"] = [record()]
        with self.assertRaisesRegex(ControlError, "changed in hOn"):
            await self.service.change(self.device, "off", None, ["old", iso(self.due)])
        self.handler.payload["scheduleRunningProgramEnd"].append(record(ident="fixture-2"))
        with self.assertRaisesRegex(ControlError, "conflicting"):
            await self.service.change(self.device, "off", self.due, None)
        self.assertEqual(self.handler.writes, [])

    async def test_updating_an_end_timer_drops_its_already_executed_start(self):
        original = record(paired=True)
        original["dateISOstart"] = iso(datetime.now(timezone.utc) - timedelta(hours=1))
        self.handler.payload["scheduledPrograms"] = [original]
        state, _ = await self.service.read(self.device)
        await self.service.change(self.device, "off", self.due, state["off"]["expected"])
        body = self.handler.writes[0][2]
        self.assertNotIn("setupStart", body)
        self.assertNotIn("dateISOstart", body)
        self.assertEqual(self.api.sent, [])

    async def test_timer_network_failure_keeps_safe_diagnostics_and_disabled_state(self):
        controller = Controller()
        controller.cloud_timers = SimpleNamespace(read=AsyncMock(side_effect=TimeoutError()))
        status = await controller.timer_status(self.device)
        self.assertFalse(status["available"])
        self.assertIn("Refresh", status["error"])

    async def test_recurring_maintenance_expired_and_inactive_records_are_untouched(self):
        rows = [record("on", "recurring"), record("on", "expired"), record("on", "inactive")]
        rows[0]["frequency"] = "daily"
        rows[1]["dateISOstart"] = iso(datetime.now(timezone.utc) - timedelta(days=1))
        rows[2]["isActive"] = False
        self.handler.payload["scheduledPrograms"] = deepcopy(rows)
        self.handler.payload["scheduledProgramsMaintenance"] = [record("on", "maintenance")]
        await self.service.change(self.device, "on", self.due, None)
        self.assertEqual(self.handler.payload["scheduledPrograms"][:3], rows)
        self.assertEqual(len(self.handler.payload["scheduledProgramsMaintenance"]), 1)

    async def test_rejected_write_and_unconfirmed_readback_never_report_success(self):
        self.handler.status = 500
        with self.assertRaises(ControlError):
            await self.service.change(self.device, "off", self.due, None)
        self.handler.status, self.handler.stale = 200, True
        with patch("room_ac_control.cloud_timers.asyncio.sleep", new=AsyncMock()):
            with self.assertRaisesRegex(ControlError, "not confirmed"):
                await self.service.change(self.device, "off", self.due, None)
        self.assertEqual(len(self.handler.writes), 1)  # No automatic mutation retry.

    async def test_invalid_settings_and_past_time_never_write(self):
        with self.assertRaises(ControlError):
            await self.service.change(self.device, "on", self.due, None, {"tempSel": "70"})
        with self.assertRaises(ControlError):
            await self.service.change(self.device, "off", datetime.now()-timedelta(minutes=1), None)
        self.assertEqual(self.handler.writes, [])
        self.assertEqual(self.api.sent, [])

    async def test_unknown_timer_schema_does_not_become_an_empty_success(self):
        self.handler.payload = {"resultCode": "0"}
        controller = Controller()
        controller.cloud_timers = self.service
        status = await controller.timer_status(self.device)
        self.assertFalse(status["available"])
        self.handler.payload = {"scheduledPrograms": {"id": "unfamiliar"}}
        with self.assertRaises(ControlError): await self.service.read(self.device)


class TimerStatusTests(unittest.TestCase):
    def test_malformed_dates_and_missing_setup_cannot_be_changed(self):
        broken = record("on")
        broken["dateISOstart"] = "local time without offset"
        state, _ = select_timers({"scheduledPrograms": [broken]})
        self.assertFalse(state["on"]["supported"])
        broken = record("off")
        del broken["setupEnd"]
        state, _ = select_timers({"scheduleRunningProgramEnd": [broken]})
        self.assertFalse(state["off"]["supported"])
