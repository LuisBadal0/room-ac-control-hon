"""Fictional rooms for the public, account-free design preview."""

from copy import deepcopy


def devices():
    modes = {"Auto": "0", "Cool": "1", "Dry": "2", "Heat": "4", "Fan": "6"}
    fans = {"Auto": "0", "Low": "5", "Medium": "3", "High": "1"}

    def enum(key, label, options, value):
        return {"key": key, "label": label, "kind": "enum", "options": options, "value": value, "reported": True}

    toggle = {"Off": "0", "On": "1"}
    controls = {
        "machMode": enum("machMode", "Mode", modes, "1"),
        "windSpeed": enum("windSpeed", "Fan speed", fans, "0"),
        "silentSleepStatus": enum("silentSleepStatus", "Sleep", toggle, "0"),
        "ecoMode": enum("ecoMode", "Eco Mode", toggle, "0"),
        "windDirectionVertical": enum(
            "windDirectionVertical",
            "Vertical airflow",
            {**{f"Position {n}": v for n, v in enumerate(("2", "4", "5", "6", "7"), 1)}, "Swing": "8"},
            "8",
        ),
        "tempSel": {
            "key": "tempSel",
            "label": "Target temperature",
            "kind": "range",
            "min": 16,
            "max": 32,
            "step": 1,
            "value": 23,
            "reported": True,
        },
    }
    room = {
        "id": "preview-living-room",
        "name": "Living room",
        "model": "DEMO-AC",
        "power": "On",
        "mode": "Cool",
        "room": 23,
        "target": 23,
        "fan": "Auto",
        "connection": "CONNECTED",
        "fetched": "Preview",
        "controls": controls,
        "modes": modes,
        "fans": fans,
        "temperatures": [str(n) for n in range(16, 33)],
        "commands": {},
        "sensors": {"outdoor": 31, "humidity": 58, "air": "Good", "air_measured": True},
        # Fictional weather for the offline preview, in the shape weather.summary gives.
        "weather": {
            "temperature": 27.4,
            "low": 24.1,
            "high": 29.0,
            "humidity": 46,
            "pressure": 1016,
            "rain": 10,
            "wind": 14,
            "uv": 6.2,
            "aqi": 2,
            "air": "Fair",
            "condition": "Cloudy",
        },
        "alerts": [],
    }
    bedroom = deepcopy(room)
    bedroom.update(
        id="preview-bedroom",
        name="Bedroom",
        power="Off",
        room=22,
        sensors={"outdoor": 31, "air": "Good", "air_measured": False},
        alerts=[{"kind": "filter"}],
    )
    return [room, bedroom]


def seed_history(memory, rooms, now=None):
    """A fictional week of room readings for the offline preview's history chart."""
    import math
    import time
    from datetime import datetime

    from .room_history import EVERY

    if memory.history is None:
        return
    now = time.time() if now is None else now
    for offset, room in enumerate(rooms):
        for step in range(7 * 24 * 3600 // EVERY, -1, -1):
            moment = now - step * EVERY
            hour = datetime.fromtimestamp(moment).hour + datetime.fromtimestamp(moment).minute / 60
            on = 13 <= hour < 22 and offset == 0
            outside = 25 + 6 * math.sin((hour - 9) / 24 * 2 * math.pi)
            indoor = (23.4 if on else 25.5 - offset) + 0.9 * math.sin((hour - 11) / 24 * 2 * math.pi)
            snapshot = {"room": round(indoor, 1), "target": 23, "power": "On" if on else "Off"}
            snapshot["sensors"] = {"outdoor": round(outside, 1)}
            memory.history.record(memory.account, room["id"], snapshot, now=moment)


def energy(room, today=None):
    """Fictional energy use for the offline preview; the bedroom reports none, like many ACs."""
    from datetime import date, timedelta

    from .energy import summary

    if room["id"] != "preview-living-room":
        return summary({"payload": {"payload": {"total": {"week": 0, "month": 0, "year": 0}}}})
    today = today or date.today()
    week = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    month = [today - timedelta(days=offset) for offset in range(today.day - 1, -1, -1)]
    daily = lambda day: round(2.2 + 1.4 * ((day.toordinal() * 7) % 5) / 4, 1)
    history = {
        "week": [{"date": day.isoformat(), "consumption": daily(day)} for day in week],
        "month": [{"date": day.isoformat(), "consumption": daily(day)} for day in month],
        "year": [
            {
                "date": date(today.year, number, 1).isoformat(),
                "consumption": (40, 32, 18, 9, 26, 71, 98, 104, 63, 21, 12)[number - 1] if number <= 11 else 0,
            }
            for number in range(1, today.month + 1)
        ],
    }
    totals = {period: round(sum(row["consumption"] for row in rows), 1) for period, rows in history.items()}
    return summary({"payload": {"payload": {"total": totals, "history": history}}})
