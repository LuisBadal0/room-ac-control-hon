"""Outside weather at the AC's location, read the way hOn reads it. Offline, with fakes."""

import asyncio
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp

from room_ac_control import weather
from room_ac_control.controller import Controller
from room_ac_control.diagnostics import diagnostics

# The shape of hOn's answer (OpenWeather's forecast, UV index and air pollution), with
# fictional values. Real answers also carry a place name and coordinates, never kept.
PAYLOAD = {
    "cod": "200",
    "cnt": 2,
    "list": [
        {
            "dt": 1794279600,
            "main": {"temp": 290.12, "temp_min": 289.65, "temp_max": 290.19, "pressure": 1009, "humidity": 97},
            "weather": [{"id": 502, "main": "Rain", "description": "heavy intensity rain", "icon": "10n"}],
            "wind": {"speed": 4.68, "deg": 208},
            "pop": 1,
        },
        {"main": {"temp": 280.0, "humidity": 10}, "weather": [{"description": "clear sky"}], "pop": 0},
    ],
    "city": {"name": "Fixture Town", "coord": {"lat": 1.5, "lon": 2.5}},
    "uvi": [{"lat": 1.5, "lon": 2.5, "value": 2.44}, {"value": 9}],
    "quality": {"coord": [1.5, 2.5], "list": [{"main": {"aqi": 2}, "components": {"pm2_5": 2.39}}]},
}
SUMMARY = {
    "temperature": 17.0,
    "low": 16.5,
    "high": 17.0,
    "humidity": 97.0,
    "pressure": 1009.0,
    "rain": 100,
    "wind": 17,
    "uv": 2.44,
    "aqi": 2,
    "air": "Fair",
    "condition": "Rain",
}


class Response:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, content_type=None):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Handler:
    """Stands in for pyhOn's authenticated connection; answers are queued per URL."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        answer = self.answers[url].pop(0) if self.answers.get(url) else Response(500, {})
        if isinstance(answer, Exception):
            raise answer
        return answer


DEVICE = SimpleNamespace(mac_address="fixture-mac", unique_id="fixture-ac")
CACHED, MAIN = weather.URLS


class SummaryTests(unittest.TestCase):
    def test_the_first_entry_of_each_list_is_shown_like_hon(self):
        self.assertEqual(weather.summary(PAYLOAD), SUMMARY)

    def test_place_names_and_coordinates_are_never_kept(self):
        text = repr(weather.summary(PAYLOAD))
        for private in ("Fixture Town", "1.5", "2.5", "coord", "city"):
            self.assertNotIn(private, text)

    def test_every_air_quality_level_has_hons_label(self):
        for level, label in ((1, "Good"), (2, "Fair"), (3, "Moderate"), (4, "Poor"), (5, "Very poor")):
            payload = deepcopy(PAYLOAD)
            payload["quality"]["list"][0]["main"]["aqi"] = level
            self.assertEqual(weather.summary(payload)["air"], label)

    def test_conditions_and_levels_are_translated(self):
        from room_ac_control.translations import PORTUGUESE

        for label in (*weather.CONDITIONS.values(), *weather.AIR_QUALITY.values()):
            self.assertIn(label, PORTUGUESE)

    def test_missing_or_odd_values_are_left_out(self):
        self.assertEqual(weather.summary(None), {})
        self.assertEqual(weather.summary({"list": "no", "quality": [], "uvi": {}}), {})
        payload = deepcopy(PAYLOAD)
        payload["list"][0]["main"].update(temp="hot", humidity=140, pressure=True)
        payload["list"][0]["pop"] = float("nan")
        payload["quality"]["list"][0]["main"]["aqi"] = 9
        payload["uvi"] = []
        values = weather.summary(payload)
        for key in ("temperature", "humidity", "pressure", "rain", "aqi", "air", "uv"):
            self.assertNotIn(key, values)
        self.assertEqual(values["wind"], 17)


class ReadingsTests(unittest.TestCase):
    def test_the_acs_own_sensors_come_first(self):
        snapshot = {
            "sensors": {"outdoor": 31.0, "humidity": 58.0, "air": "Medium", "air_measured": True},
            "weather": SUMMARY,
        }
        self.assertEqual(
            weather.readings(snapshot),
            {"outdoor": (31.0, "ac"), "humidity": (58.0, "ac"), "air": ("Medium", "ac")},
        )

    def test_values_the_ac_does_not_measure_come_from_the_weather(self):
        snapshot = {"sensors": {"air": "Good", "air_measured": False}, "weather": SUMMARY}
        self.assertEqual(
            weather.readings(snapshot),
            {"outdoor": (17.0, "weather"), "humidity": (97.0, "weather"), "air": ("Fair", "weather")},
        )

    def test_without_weather_level_0_still_shows_as_hon_shows_it(self):
        snapshot = {"sensors": {"air": "Good", "air_measured": False}}
        self.assertEqual(weather.readings(snapshot), {"air": ("Good", "ac")})
        self.assertEqual(weather.readings({}), {})


class LoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_cached_api_is_asked_first_with_the_acs_mac(self):
        handler = Handler({CACHED: [Response(200, {"payload": PAYLOAD})]})
        self.assertEqual(await weather.load(handler, DEVICE), SUMMARY)
        # hOn sends the phone's language too; the service answers in English regardless.
        self.assertEqual(handler.calls, [(CACHED, {"macAddress": "fixture-mac", "phoneLanguage": "en"})])

    async def test_the_main_api_answers_when_the_cache_fails(self):
        for failure in (Response(503, {}), aiohttp.ClientError("fixture"), Response(200, {"payload": {}})):
            with self.subTest(failure=failure):
                handler = Handler({CACHED: [failure], MAIN: [Response(200, {"payload": PAYLOAD})]})
                self.assertEqual(await weather.load(handler, DEVICE), SUMMARY)
                self.assertEqual([url for url, _ in handler.calls], [CACHED, MAIN])

    async def test_an_error_is_raised_when_neither_answers(self):
        handler = Handler({CACHED: [Response(500, {})], MAIN: [Response(200, ValueError("not json"))]})
        with self.assertRaises(ValueError):
            await weather.load(handler, DEVICE)


class ControllerWeatherTests(unittest.IsolatedAsyncioTestCase):
    def controller(self, answers):
        controller = Controller()
        controller.api = SimpleNamespace(_hon=Handler(answers))
        return controller

    async def test_weather_is_loaded_at_most_every_15_minutes(self):
        controller = self.controller({CACHED: [Response(200, {"payload": PAYLOAD}) for _ in range(3)]})
        with patch("room_ac_control.controller.time.monotonic", return_value=1000.0):
            self.assertEqual(await controller.weather(DEVICE), SUMMARY)
            self.assertEqual(await controller.weather(DEVICE), SUMMARY)
            self.assertEqual(len(controller.api._hon.calls), 1)
            self.assertEqual(await controller.weather(DEVICE, load=False), SUMMARY)
        with patch("room_ac_control.controller.time.monotonic", return_value=1000.0 + 15 * 60 + 1):
            await controller.weather(DEVICE)
        self.assertEqual(len(controller.api._hon.calls), 2)

    async def test_a_failed_load_keeps_recent_values_and_is_recorded(self):
        controller = self.controller({CACHED: [Response(200, {"payload": PAYLOAD})]})
        with patch("room_ac_control.controller.time.monotonic", return_value=0.0):
            await controller.weather(DEVICE)
        before = len(diagnostics.report()["events"])
        with patch("room_ac_control.controller.time.monotonic", return_value=20 * 60.0):
            self.assertEqual(await controller.weather(DEVICE), SUMMARY)  # Both APIs fail now.
            calls = len(controller.api._hon.calls)
            await controller.weather(DEVICE)  # Not retried within the minute.
            self.assertEqual(len(controller.api._hon.calls), calls)
        self.assertEqual(diagnostics.report()["events"][-1]["event"], "weather_failed")
        self.assertGreater(len(diagnostics.report()["events"]), before)
        # Failing retries do not keep old values longer than three hours.
        for minutes in range(21, 3 * 60 + 5, 30):
            with patch("room_ac_control.controller.time.monotonic", return_value=minutes * 60.0):
                await controller.weather(DEVICE)
        with patch("room_ac_control.controller.time.monotonic", return_value=(3 * 60 + 1) * 60.0):
            self.assertEqual(await controller.weather(DEVICE, load=False), {})

    async def test_a_slow_weather_service_does_not_hold_up_status(self):
        controller = self.controller({})
        controller.WEATHER_TIMEOUT = 0.05

        async def slow(*args):
            await asyncio.sleep(60)

        with patch("room_ac_control.weather.load", new=slow):
            self.assertEqual(await controller.weather(DEVICE), {})

    async def test_no_weather_without_a_signed_in_account(self):
        self.assertEqual(await Controller().weather(DEVICE), {})


if __name__ == "__main__":
    unittest.main()
