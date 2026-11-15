"""Room temperature history, kept on this computer.

The AC reports its room temperature (and sometimes humidity) only as a current value, so
the app keeps one reading every ten minutes while it is open, for seven days, per account
and AC. The outside temperature comes from the AC's outdoor sensor or, without one, from
the weather at its location, as on the dashboard. Readings are encrypted for the current
Windows user like the rest of the app's saved state, and never leave this computer.
"""

import json
import math
import os
import secrets
import threading
import time
from pathlib import Path

from .diagnostics import diagnostics

EVERY = 10 * 60  # Seconds between kept readings.
KEEP = 7 * 24 * 60 * 60  # Readings older than this are dropped.
# A reading: [time (Unix seconds), room °C, outside °C, humidity %, target °C, AC on (1/0)].
FIELDS = ("time", "room", "outside", "humidity", "target", "on")


def number(value, low, high):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return round(result, 1) if math.isfinite(result) and low <= result <= high else None


def reading(snapshot, now):
    """The values worth keeping from a device snapshot, or None without a room temperature."""
    from .weather import readings

    room = number(snapshot.get("room"), -20, 60)
    if room is None:
        return None
    found = readings(snapshot)
    outside = number(found["outdoor"][0], -50, 60) if "outdoor" in found else None
    humidity = number(found["humidity"][0], 0, 100) if "humidity" in found else None
    return [
        int(now),
        room,
        outside,
        humidity,
        number(snapshot.get("target"), 0, 50),
        1 if snapshot.get("power") == "On" else 0,
    ]


def valid(row):
    return (
        isinstance(row, list)
        and len(row) == len(FIELDS)
        and isinstance(row[0], int)
        and not isinstance(row[0], bool)
        and all(value is None or (isinstance(value, int | float) and not isinstance(value, bool)) for value in row[1:])
    )


class RoomHistory:
    def __init__(self, path=None, persistent=True):
        self.persistent = persistent
        self.path = (
            Path(path)
            if path
            else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RoomACControl" / "history.dpapi"
        )
        self.lock = threading.RLock()
        self.data: dict[str, dict[str, list]] = {}
        if persistent and self.path.exists():
            try:
                from .secure_state import protect

                loaded = json.loads(protect(self.path.read_bytes(), decrypt=True).decode("utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("Unsupported history")
                for account, devices in loaded.items():
                    if isinstance(devices, dict):
                        self.data[account] = {
                            device: [row for row in rows if valid(row)]
                            for device, rows in devices.items()
                            if isinstance(rows, list)
                        }
            except (OSError, ValueError, UnicodeError, TypeError) as error:
                diagnostics.record("history_load_failed", error)
                self.data = {}

    def write(self):
        if not self.persistent:
            return
        from .secure_state import protect

        encrypted = protect(json.dumps(self.data, separators=(",", ":")).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + secrets.token_hex(6) + ".tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, account, device, snapshot, now=None):
        """Keep a reading if the last one is at least ten minutes old; True when kept."""
        if not account or not device:
            return False
        now = time.time() if now is None else now
        row = reading(snapshot, now)
        if row is None:
            return False
        with self.lock:
            rows = self.data.setdefault(account, {}).setdefault(device, [])
            if rows and now - rows[-1][0] < EVERY:
                return False
            rows.append(row)
            rows[:] = [old for old in rows if now - old[0] <= KEEP]
            self.write()
            return True

    def readings(self, account, device, hours, now=None):
        """Readings from the last `hours`, oldest first, as dictionaries."""
        now = time.time() if now is None else now
        with self.lock:
            rows = list(self.data.get(account, {}).get(device, []))
        return [dict(zip(FIELDS, row)) for row in rows if now - row[0] <= hours * 3600]


def summary(rows, key="room"):
    """Lowest, highest and average of one value, or None without readings."""
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return {"low": min(values), "high": max(values), "average": round(sum(values) / len(values), 1)}
