"""Energy use from hOn's statistics service, read with offline fixtures only."""

import asyncio
import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from room_ac_control import energy
from room_ac_control.controller import ControlError, Controller
from room_ac_control.demo import devices
from room_ac_control.demo import energy as preview_energy

# The shape hOn answers with for an AC that does not measure its consumption.
EMPTY = {
    "message": "Retrieve Influx Statistics",
    "payload": {
        "payload": {
            "total": {"week": 0, "month": 0, "year": 0},
            "history": {"week": [], "month": [], "year": []},
        }
    },
}
MEASURED = {
    "payload": {
        "payload": {
            "total": {"week": 12.345, "month": "40.5", "year": 300},
            "history": {
                "week": [
                    {"date": "2026-11-09", "consumption": 1.5},
                    {"date": "11-10-2026", "consumption": "2"},
                    {"date": 1_794_355_200_000, "consumption": 0},
                    {"date": "not a date", "consumption": 3},
                    {"date": "2026-11-12", "consumption": -1},
                    {"date": "2026-11-13", "consumption": None},
                    "junk",
                ],
                "month": None,
            },
        }
    },
}


class Response:
    def __init__(self, status, data):
        self.status, self.data = status, data

    async def json(self, content_type=None):
        return self.data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Handler:
    def __init__(self, status=200, data=EMPTY):
        self.status, self.data, self.calls = status, data, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return Response(self.status, self.data)


class Device:
    mac_address = "00-00-00-00-00-00"
    unique_id = "fixture-ac"


class SummaryTests(unittest.TestCase):
    def test_an_ac_without_a_meter_has_no_measured_use(self):
        values = energy.summary(EMPTY)
        self.assertFalse(values["measured"])
        self.assertEqual(values["total"], {"week": 0, "month": 0, "year": 0})
        self.assertEqual(values["history"], {"week": [], "month": [], "year": []})

    def test_measured_totals_and_history_keep_only_plausible_values(self):
        values = energy.summary(MEASURED)
        self.assertTrue(values["measured"])
        self.assertEqual(values["total"], {"week": 12.35, "month": 40.5, "year": 300.0})
        week = values["history"]["week"]
        self.assertEqual([bar["kwh"] for bar in week], [1.5, 2.0, 0.0, 3.0])
        self.assertEqual(week[0]["date"], datetime(2026, 11, 9))
        self.assertEqual(week[1]["date"], datetime(2026, 11, 10))
        self.assertIsInstance(week[2]["date"], datetime)
        self.assertIsNone(week[3]["date"])
        self.assertEqual(values["history"]["month"], [])

    def test_unfamiliar_answers_are_empty_not_errors(self):
        for data in (None, [], {"payload": None}, {"payload": {"total": "x", "history": []}}, {"payload": "x"}):
            self.assertFalse(energy.summary(data)["measured"], data)
        self.assertIsNone(energy.kwh(True))
        self.assertIsNone(energy.kwh(float("inf")))
        self.assertIsNone(energy.when(float("nan")))
        self.assertIsNone(energy.when(10**20))

    def test_load_asks_like_hon_and_refuses_failed_answers(self):
        handler = Handler(data=MEASURED)
        values = asyncio.run(energy.load(handler, Device()))
        self.assertTrue(values["measured"])
        url, params = handler.calls[0]
        self.assertEqual(url, energy.URL)
        self.assertEqual(params, {"macAddress": Device.mac_address, "applianceType": "AC", "filter": "week"})
        with self.assertRaises(ConnectionError):
            asyncio.run(energy.load(Handler(status=500), Device()))

    def test_preview_values(self):
        living, bedroom = devices()
        values = preview_energy(living, today=date(2026, 11, 15))
        self.assertTrue(values["measured"])
        self.assertEqual(len(values["history"]["week"]), 7)
        self.assertEqual(len(values["history"]["month"]), 15)
        self.assertEqual(len(values["history"]["year"]), 11)
        self.assertFalse(preview_energy(bedroom)["measured"])


class ControllerTests(unittest.TestCase):
    def test_energy_is_cached_for_half_an_hour_per_ac(self):
        controller = Controller()
        controller.api = type("Api", (), {"_hon": object()})()
        controller.devices = {"fixture-ac": Device()}
        loader = AsyncMock(return_value={"measured": False})
        with patch("room_ac_control.energy.load", loader), patch("room_ac_control.controller.time.monotonic") as now:
            now.return_value = 1000.0
            asyncio.run(controller.energy("fixture-ac"))
            now.return_value = 1000.0 + Controller.ENERGY_EVERY - 1
            asyncio.run(controller.energy("fixture-ac"))
            self.assertEqual(loader.await_count, 1)
            now.return_value = 1000.0 + Controller.ENERGY_EVERY
            asyncio.run(controller.energy("fixture-ac"))
            self.assertEqual(loader.await_count, 2)

    def test_energy_needs_a_signed_in_account(self):
        with self.assertRaises(ControlError):
            asyncio.run(Controller().energy("fixture-ac"))


if __name__ == "__main__":
    unittest.main()
