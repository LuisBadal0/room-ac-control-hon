"""Energy use as the hOn app shows it under Statistics › Energy consumption.

hOn 2.30.7 reads an AC's consumption from its statistics service
(`statistics/v1/influx/retrieve`) by the AC's MAC address. The answer holds totals for
this week, month and year in kWh, and a history for each, as a list of
{date, consumption}. Many ACs do not measure their consumption; for those the service
answers with zeros and empty lists, and hOn shows an empty state. This is read-only.
"""

import math
from datetime import UTC, datetime

URL = "https://api-iot.he.services/statistics/v1/influx/retrieve"
PERIODS = ("week", "month", "year")


def kwh(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return round(result, 2) if math.isfinite(result) and 0 <= result <= 1_000_000 else None


def when(value):
    """A history entry's date: ISO text, hOn's MM-DD-YYYY, or Unix time in seconds or ms."""
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, UTC).astimezone().replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return result.astimezone().replace(tzinfo=None) if result.tzinfo else result
    except ValueError:
        pass
    for pattern in ("%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def summary(data):
    """Totals and history from a statistics answer: {"total": {...}, "history": {...}, "measured": bool}."""
    payload = data.get("payload") if isinstance(data, dict) else None
    # The service wraps its answer twice: {"payload": {"payload": {...}}}.
    if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
        payload = payload["payload"]
    if not isinstance(payload, dict):
        payload = {}
    totals = payload.get("total")
    totals = totals if isinstance(totals, dict) else {}
    histories = payload.get("history")
    histories = histories if isinstance(histories, dict) else {}
    total = {period: kwh(totals.get(period)) for period in PERIODS}
    history = {}
    for period in PERIODS:
        rows = histories.get(period)
        bars = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and (value := kwh(row.get("consumption"))) is not None:
                bars.append({"date": when(row.get("date")), "kwh": value})
        history[period] = bars
    measured = any(value for value in total.values()) or any(bar["kwh"] for bars in history.values() for bar in bars)
    return {"total": total, "history": history, "measured": measured}


async def load(handler, device):
    """Ask hOn's statistics service for the AC's energy use; raises when it cannot answer."""
    params = {"macAddress": device.mac_address, "applianceType": "AC", "filter": "week"}
    async with handler.get(URL, params=params) as response:
        if response.status != 200:
            raise ConnectionError(f"Statistics service answered {response.status}")
        data = await response.json(content_type=None)
    return summary(data)
