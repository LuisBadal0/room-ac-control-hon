"""Outside weather at the AC's location, as the hOn app shows it under Outdoor.

hOn 2.30.7 asks its own weather service for the location saved with the AC, by the AC's
MAC address. The answer is a 3-hour forecast, a UV index and air pollution, in
OpenWeather's format; hOn shows the first entry of each. This reads the same answer.
It is read-only, and the place name and coordinates in it are never kept.
"""

import math

import aiohttp

# hOn tries its cached API first, then the main one.
URLS = (
    "https://api-cache-iot.he.services/commands/v1/weather",
    "https://api-iot.he.services/commands/v1/weather",
)
# OpenWeather's air quality index, with hOn's labels.
AIR_QUALITY = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very poor"}
# The service describes the weather in English whatever language is asked for, so the
# app shows OpenWeather's condition group instead, in its own words and translations.
CONDITIONS = {
    "Clear": "Clear sky",
    "Clouds": "Cloudy",
    "Rain": "Rain",
    "Drizzle": "Drizzle",
    "Thunderstorm": "Thunderstorm",
    "Snow": "Snow",
    "Mist": "Mist",
    "Fog": "Fog",
    "Haze": "Haze",
    "Smoke": "Smoke",
    "Dust": "Dust",
    "Sand": "Sand",
    "Ash": "Volcanic ash",
    "Squall": "Squalls",
    "Tornado": "Tornado",
}


def number(value, low, high):
    """A finite number within a plausible range, or None."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def first(items):
    return items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}


def celsius(kelvin):
    value = number(kelvin, 150, 350)
    return None if value is None else round(value - 273.15, 1)


def summary(payload):
    """The values hOn's Outdoor panel shows, from a weather answer; {} when there are none."""
    if not isinstance(payload, dict):
        return {}
    now = first(payload.get("list"))
    main = now.get("main") if isinstance(now.get("main"), dict) else {}
    wind = now.get("wind") if isinstance(now.get("wind"), dict) else {}
    weather = first(now.get("weather"))
    quality = first(payload.get("quality", {}).get("list") if isinstance(payload.get("quality"), dict) else None)
    level = quality["main"].get("aqi") if isinstance(quality.get("main"), dict) else None
    values = {
        "temperature": celsius(main.get("temp")),
        "low": celsius(main.get("temp_min")),
        "high": celsius(main.get("temp_max")),
        "humidity": number(main.get("humidity"), 0, 100),
        "pressure": number(main.get("pressure"), 800, 1100),
        "rain": None if (chance := number(now.get("pop"), 0, 1)) is None else round(chance * 100),
        # OpenWeather's standard units, the ones its Kelvin temperatures come with, are m/s.
        "wind": None if (speed := number(wind.get("speed"), 0, 100)) is None else round(speed * 3.6),
        "uv": number(first(payload.get("uvi")).get("value"), 0, 20),
        "aqi": level if isinstance(level, int) and not isinstance(level, bool) and level in AIR_QUALITY else None,
        "air": AIR_QUALITY.get(level) if isinstance(level, int) and not isinstance(level, bool) else None,
        "condition": CONDITIONS.get(weather.get("main")) if isinstance(weather.get("main"), str) else None,
    }
    return {key: value for key, value in values.items() if value is not None}


async def load(handler, device):
    """Ask hOn's weather service for the AC's location; the main API is tried if the cache fails."""
    params = {"macAddress": device.mac_address, "phoneLanguage": "en"}
    failure: Exception = ConnectionError("No weather service answered")
    for url in URLS:
        try:
            async with handler.get(url, params=params) as response:
                if response.status != 200:
                    raise ConnectionError(f"Weather service answered {response.status}")
                data = await response.json(content_type=None)
            values = summary(data.get("payload") if isinstance(data, dict) else None)
            if values:
                return values
            failure = ValueError("The weather answer had no forecast")
        except (aiohttp.ClientError, OSError, ValueError, TimeoutError) as error:
            failure = error
    raise failure


def readings(snapshot):
    """The dashboard's Outside, Humidity and Air quality readings, each with its source.

    The AC's own sensors come first. A value the AC does not measure comes from the
    weather at its location, as in hOn's Outdoor panel: {key: (value, "ac" or "weather")}."""
    sensors = snapshot.get("sensors") or {}
    weather = snapshot.get("weather") or {}
    result = {}
    for key, outside in (("outdoor", "temperature"), ("humidity", "humidity")):
        if key in sensors:
            result[key] = (sensors[key], "ac")
        elif outside in weather:
            result[key] = (weather[outside], "weather")
    if sensors.get("air") and sensors.get("air_measured", True):
        result["air"] = (sensors["air"], "ac")
    elif weather.get("air"):
        result["air"] = (weather["air"], "weather")
    elif sensors.get("air"):
        result["air"] = (sensors["air"], "ac")  # Level 0, which hOn also shows as good.
    return result
