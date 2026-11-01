"""Repeating schedules held by hOn's cloud service, in hOn 2.30.7's record format.

hOn stores days as 0 = Monday … 6 = Sunday and repeats a schedule with the
frequency "everyday" or "weekly". The dates hold an occurrence and the service
repeats it on the listed days, so a past date in a repeating record is normal.
When a schedule starts after it ends, hOn moves the start back one day.
Records are written to the same cron service as the one-time timers.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .cloud_timers import BUCKETS, DATE, SETUP, command_payload, iso, utc_time
from .controller import MODES, ControlError, code

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EVERY_DAY = (0, 1, 2, 3, 4, 5, 6)
WEEKDAYS = (0, 1, 2, 3, 4)
WEEKEND = (5, 6)
# Fields a schedule keeps when it is switched on or off.
KEEP = {"scheduledProgram", "setupStart", "setupEnd", "dateISOstart", "dateISOend", "days",
        "timezoneOffset", "frequency", "scheduleEnd"}


def day_labels(days):
    """Display tokens, each translated on its own: ["Weekdays"] or ["Mon", "Wed"]."""
    days = tuple(sorted(set(days)))
    if days == EVERY_DAY:
        return ["Every day"]
    if days == WEEKDAYS:
        return ["Weekdays"]
    if days == WEEKEND:
        return ["Weekend"]
    return [DAY_NAMES[day] for day in days]


def clock_text(value):
    return f"{value[0]:02d}:{value[1]:02d}"


def record_days(record):
    """Repeat days of a record; () for an unfamiliar repeat, None for one-time."""
    frequency = record.get("frequency")
    if frequency in {"everyday", "daily"}:
        return EVERY_DAY
    if frequency not in {"weekly", "every"}:
        return None
    days = record.get("days")
    if not isinstance(days, list) or not days:
        return ()
    result = set()
    for day in days:
        if isinstance(day, bool) or not str(day).isdigit() or not 0 <= int(day) <= 6:
            return ()
        result.add(int(day))
    return tuple(sorted(result))


def clock(record, field):
    """Local clock time of a stored date, using the offset saved with the record."""
    due = utc_time(record.get(field))
    if due is None:
        return None
    offset = record.get("timezoneOffset")
    if isinstance(offset, (int, float)) and not isinstance(offset, bool):
        local = due - timedelta(minutes=offset)  # JavaScript offsets are UTC minus local.
    else:
        local = due.astimezone()
    return local.hour, local.minute


def summary(command):
    """The mode and temperature a stored start command applies."""
    parameters = command.get("parameters") if isinstance(command, dict) else None
    if not isinstance(parameters, dict):
        return {}
    result = {}
    mode = MODES.get(code(parameters.get("machMode")))
    if mode:
        night = mode in {"Cool", "Heat"} and code(parameters.get("silentSleepStatus")) == "1"
        result["mode"] = mode + (" Night" if night else "")
    try:
        result["temperature"] = float(parameters["tempSel"])
    except (KeyError, TypeError, ValueError):
        pass
    return result


def schedule_rows(payload, now=None):
    """Every schedule shown in the list: upcoming one-time timers and repeating ones.

    Maintenance routines are left alone, and finished one-time timers are hidden.
    """
    now = now or datetime.now(timezone.utc)
    rows = []
    for bucket in BUCKETS:
        records = payload.get(bucket, [])
        if not isinstance(records, list):
            raise ControlError("The cloud service returned an unfamiliar timer format.")
        for record in records:
            if not isinstance(record, dict) or record.get("maintenance") or not record.get("id"):
                continue
            times = {action: clock(record, DATE[action]) for action in DATE if isinstance(record.get(SETUP[action]), dict)}
            times = {action: value for action, value in times.items() if value is not None}
            if not times:
                continue
            row = {"id": str(record["id"]), "bucket": bucket, "record": record, "active": bool(record.get("isActive")),
                   "start": times.get("on"), "end": times.get("off"), **summary(record.get("setupStart"))}
            days = record_days(record)
            if record.get("frequency") == "once":
                upcoming = [due for due in (utc_time(record.get(DATE[action])) for action in times) if due and due > now]
                if not upcoming or not row["active"]:
                    continue
                due = min(upcoming).astimezone()
                row.update(kind="once", due=due, days=(due.weekday(),))
            elif days:
                row.update(kind="repeat", days=days)
            else:
                # Monthly or other repeats that this app does not edit.
                row.update(kind="other", days=())
            rows.append(row)
    rows.sort(key=lambda row: ({"repeat": 0, "once": 1}.get(row["kind"], 2), row["start"] or row["end"]))
    return rows


def conflicts(rows, start, end, days, ignore=None):
    """Active schedules with a start or end at the same time on a shared day."""
    mine = {value for value in (start, end) if value is not None}
    found = []
    for row in rows:
        if row["id"] == ignore or not row["active"] or row["kind"] == "other":
            continue
        shared = set(days) & set(row["days"])
        same = mine & {value for value in (row["start"], row["end"]) if value is not None}
        if shared and same:
            found.append({"row": row, "time": min(same), "days": tuple(sorted(shared))})
    return found


def next_occurrence(hour, minute, days, now=None):
    """The next local time on one of the days; times skipped by a clock change are passed over."""
    now = now or datetime.now().astimezone()
    for ahead in range(8):
        day = (now + timedelta(days=ahead)).date()
        if day.weekday() not in days:
            continue
        naive = datetime(day.year, day.month, day.day, hour, minute)
        local = naive.astimezone()
        if local.replace(tzinfo=None) != naive:
            continue
        if local > now:
            return local
    raise ControlError("Choose at least one day for the schedule.")


def validate_request(start, end, days):
    days = tuple(sorted(set(days or ())))
    if not days or any(day not in EVERY_DAY for day in days):
        raise ControlError("Choose at least one day for the schedule.")
    if start is None and end is None:
        raise ControlError("Choose a start time, an end time or both.")
    for value in (start, end):
        if value is not None and not (0 <= value[0] <= 23 and 0 <= value[1] <= 59):
            raise ControlError("Choose a valid 24-hour time.")
    if start is not None and start == end:
        raise ControlError("The start and end times must differ.")
    return days


def schedule_dates(start, end, days, now=None):
    """Next occurrences, with hOn's rule that a start after its end moves back a day."""
    now = now or datetime.now().astimezone()
    due = {}
    if start is not None:
        due["on"] = next_occurrence(*start, days, now)
    if end is not None:
        due["off"] = next_occurrence(*end, days, now)
    if len(due) == 2 and due["on"] > due["off"]:
        due["on"] -= timedelta(days=1)
    return due


def repeating_body(device, handler, start, end, days, requested=None, now=None):
    """A repeating record in hOn's format; start and end are (hour, minute) or None."""
    days = validate_request(start, end, days)
    due = schedule_dates(start, end, days, now)
    first = min(due.values())
    body = {"macAddress": device.mac_address, "scheduledProgram": None,
            "frequency": "everyday" if days == EVERY_DAY else "weekly", "days": list(days),
            "maintenance": False, "isActive": True,
            "timezoneOffset": -int(first.utcoffset().total_seconds() // 60)}
    if start is not None:
        body["setupStart"] = command_payload(device, "on", handler, requested)
    if end is not None:
        body["setupEnd"] = command_payload(device, "off", handler)
    for action, value in due.items():
        body[DATE[action]] = iso(value)
    return body


def preview_record(ident, start, end, days, requested=None, now=None):
    """A fictional record for the offline preview; it never reaches the cloud."""
    days = validate_request(start, end, days)
    due = schedule_dates(start, end, days, now)
    first = min(due.values())
    record = {"id": ident, "frequency": "everyday" if days == EVERY_DAY else "weekly", "days": list(days),
              "isActive": True, "maintenance": False,
              "timezoneOffset": -int(first.utcoffset().total_seconds() // 60)}
    if start is not None:
        record["setupStart"] = {"commandName": "startProgram", "parameters": {**(requested or {}), "onOffStatus": "1"}}
    if end is not None:
        record["setupEnd"] = {"commandName": "stopProgram", "parameters": {"onOffStatus": "0"}}
    for action, value in due.items():
        record[DATE[action]] = iso(value)
    return record


def same_dates(record, body):
    return all(iso(utc_time(record.get(field))) == body[field] if utc_time(record.get(field)) else False
               for field in DATE.values() if field in body)


class Schedules:
    """List and change schedules; every change is confirmed by reading it back."""

    def __init__(self, timers):
        self.timers = timers

    async def payload(self, device):
        payload = await self.timers.request("GET", device.mac_address)
        if not any(key in payload for key in BUCKETS):
            raise ControlError("The cloud service did not return timer status.")
        return payload

    async def rows(self, device):
        return schedule_rows(await self.payload(device))

    async def find(self, device, ident, kinds=("repeat", "once")):
        row = next((row for row in await self.rows(device) if row["id"] == ident), None)
        if row is None or row["kind"] not in kinds:
            raise ControlError("This schedule changed in hOn. Refresh the list before trying again.")
        return row

    async def confirm(self, device, check):
        for attempt in range(3):
            rows = await self.rows(device)
            if check(rows):
                return rows
            if attempt < 2:
                await asyncio.sleep(1)
        raise ControlError("The schedule request was sent, but its saved status is not confirmed. Check hOn before retrying.")

    async def save(self, device, ident, start, end, days, requested=None, allow_conflict=False):
        """Create or edit a repeating schedule; conflicts are returned unless allowed."""
        validate_request(start, end, days)
        rows = await self.rows(device)
        existing = None
        if ident is not None:
            existing = next((row for row in rows if row["id"] == ident), None)
            if existing is None or existing["kind"] != "repeat":
                raise ControlError("This schedule changed in hOn. Refresh the list before trying again.")
        found = conflicts(rows, start, end, days, ignore=ident)
        if found and not allow_conflict:
            return {"saved": False, "rows": rows, "conflicts": found}
        device.attributes.clear()
        await device.update(force=True)
        body = repeating_body(device, self.timers.handler, start, end, days, requested)
        if existing and existing["bucket"] == "scheduleRunningProgramEnd":
            body["scheduleEnd"] = True
        if existing:
            await self.timers.request("PUT", ident, body)
        else:
            await self.timers.request("POST", "", body)
        def saved(rows):
            return any(row["kind"] == "repeat" and (ident is None or row["id"] == ident)
                       and list(row["days"]) == body["days"] and same_dates(row["record"], body) for row in rows)
        return {"saved": True, "rows": await self.confirm(device, saved), "conflicts": []}

    async def set_active(self, device, ident, active):
        row = await self.find(device, ident, kinds=("repeat",))
        body = {key: deepcopy(value) for key, value in row["record"].items() if key in KEEP}
        body.update(macAddress=device.mac_address, maintenance=False, isActive=bool(active))
        await self.timers.request("PUT", ident, body)
        return await self.confirm(device, lambda rows: any(item["id"] == ident and item["active"] == bool(active) for item in rows))

    async def delete(self, device, ident):
        row = await self.find(device, ident)
        body = {"macAddress": device.mac_address, "maintenance": False}
        if row["bucket"] == "scheduleRunningProgramEnd":
            body["scheduleEnd"] = True
        await self.timers.request("DELETE", ident, body)
        return await self.confirm(device, lambda rows: all(item["id"] != ident for item in rows))
