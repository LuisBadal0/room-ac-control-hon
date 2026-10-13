"""One-time schedules held by hOn's cloud service, independent of the PC.

Protocol field names were checked against hOn 2.30.7 and a read-only cloud
response. No manufacturer code or assets are distributed with this adapter.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from .controller import ControlError, capabilities, code, validate

BASE = "https://api-iot.he.services/cron/v1/air-conditioner"
BUCKETS = ("scheduledPrograms", "scheduleRunningProgramEnd")
DATE = {"on": "dateISOstart", "off": "dateISOend"}
SETUP = {"on": "setupStart", "off": "setupEnd"}


def utc_time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def select_timers(payload, now=None):
    """Keep maintenance/recurring schedules separate; refuse ambiguous controls."""
    now = now or datetime.now(timezone.utc)
    found = {"on": [], "off": []}
    blocked = set()
    for bucket in BUCKETS:
        rows = payload.get(bucket, [])
        if not isinstance(rows, list):
            raise ControlError("The cloud service returned an unfamiliar timer format.")
        for record in rows:
            if not isinstance(record, dict):
                raise ControlError("The cloud service returned an unfamiliar timer format.")
            if not record.get("isActive") or record.get("maintenance"):
                continue
            if record.get("frequency") != "once":
                if bucket == "scheduleRunningProgramEnd":
                    blocked.add("off")
                continue
            for action, field in DATE.items():
                due = utc_time(record.get(field))
                if record.get(field) and due is None:
                    blocked.add(action)
                if due and due > now:
                    if not record.get("id") or not isinstance(record.get(SETUP[action]), dict):
                        blocked.add(action)
                    found[action].append({"record": record, "bucket": bucket, "due": due})
    result = {}
    for action, rows in found.items():
        rows.sort(key=lambda item: item["due"])
        first = rows[0] if rows else None
        result[action] = {
            "supported": action not in blocked and len(rows) <= 1,
            "due": first["due"].astimezone().replace(tzinfo=None) if first else None,
            "expected": [str(first["record"]["id"]), iso(first["due"])] if first and first["record"].get("id") else None,
            "count": len(rows),
        }
    return result, found


def command_payload(device, action, handler, requested=None):
    """Prepare a future command without sending it or changing live parameters."""
    if action not in DATE:
        raise ControlError("Unknown timer action.")
    if action == "off":
        command = device.commands.get("stopProgram")
    else:
        base = device.commands.get("startProgram")
        command = base.categories.get("iot_simple_start") if base else None
        if command is None:
            raise ControlError("This AC does not expose a standard scheduled start command.")
    if command is None:
        raise ControlError("This AC does not expose a scheduled stop command.")
    changes = dict(requested or {})
    if action == "off" and changes:
        raise ControlError("A stop timer does not accept temperature settings.")
    allowed = set(capabilities(device)[0]) - {"onOffStatus"}
    if not set(changes).issubset(allowed):
        raise ControlError("Unsupported timer setting requested.")
    groups = deepcopy(command.parameter_groups)
    params = groups.get("parameters", {})
    for key, parameter in command.settings.items():
        if parameter.group != "parameters" or parameter.typology not in {"enum", "range"}:
            continue
        value = changes.get(key, device.get(key))
        if value is None:
            continue
        validate(parameter, value)
        # pyhOn's internal conversion is reused, with the parameter restored.
        previous = parameter.value
        try:
            parameter.value = str(value)
            params[key] = parameter.intern_value
        finally:
            parameter.value = previous
    if not set(changes).issubset(params):
        raise ControlError("The scheduled start does not support a selected setting.")
    params["onOffStatus"] = "1" if action == "on" else "0"
    if action == "on" and any(code(params.get(k)) == "1" for k in ("selfCleaningStatus", "selfCleaning56Status")):
        raise ControlError("Choose a comfort mode before scheduling a start.")
    if action == "on" and "tempSel" in params:
        params["tempSel"] = f"{float(params['tempSel']):.2f}"
    stamp = iso(datetime.now(timezone.utc))
    return {"macAddress": device.mac_address, "timestamp": stamp,
            "commandName": "startProgram" if action == "on" else "stopProgram",
            "transactionId": device.mac_address + "_" + stamp,
            "applianceOptions": deepcopy(device.options), "device": handler.device.get(mobile=True),
            "attributes": {"channel": "mobileApp", "origin": "standardProgram", "prStr": "Start" if action == "on" else "Stop"},
            "ancillaryParameters": groups.get("ancillaryParameters", {}),
            "parameters": params, "applianceType": device.appliance_type}


def schedule_body(device, action, due, command, existing=None, end_only=False):
    now = datetime.now().astimezone()
    selected = due
    due = due.astimezone()  # Naive wheel selections use the Windows local zone.
    if selected.tzinfo is None and due.replace(tzinfo=None) != selected:
        raise ControlError("That time does not exist after the daylight-saving clock change. Choose another time.")
    if due <= now or due > now + timedelta(days=2):
        raise ControlError("Choose a future time within the next day.")
    body = {k: deepcopy(v) for k, v in (existing or {}).items() if k in {
        "scheduledProgram", "setupStart", "setupEnd", "dateISOstart", "dateISOend", "days", "timezoneOffset"}}
    body.update(macAddress=device.mac_address, frequency="once", maintenance=False, isActive=True,
                timezoneOffset=-int(due.utcoffset().total_seconds() // 60))
    if end_only:
        body["scheduleEnd"] = True
    body[DATE[action]], body[SETUP[action]] = iso(due), command
    # An unnamed standard schedule is supported by the native app.
    body.setdefault("scheduledProgram", None)
    body.setdefault("days", [])
    other = "off" if action == "on" else "on"
    if other_due := utc_time(body.get(DATE[other])):
        if other_due <= now:
            body.pop(DATE[other], None)
            body.pop(SETUP[other], None)
    return body


class CloudTimers:
    def __init__(self, handler):
        self.handler = handler

    async def request(self, method, path="", body=None):
        url = BASE + ("/" + quote(str(path), safe="") if path else "")
        if method == "GET":
            context = self.handler.get(url)
        elif method == "POST":
            context = self.handler.post(url, json=body)
        else:
            # pyhOn exposes GET/POST helpers; its interceptor supplies the same
            # authentication and token refresh for the native PUT/DELETE methods.
            context = self.handler._intercept(getattr(self.handler.session, method.lower()), url, json=body)
        async with context as response:
            if not 200 <= response.status < 300:
                raise ControlError("The cloud service rejected the timer request. Refresh and check hOn.")
            data = await response.json()
        if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
            raise ControlError("The cloud service returned an unfamiliar timer response. Check hOn before retrying.")
        payload = data["payload"]
        if "resultCode" in payload and str(payload["resultCode"]) != "0":
            raise ControlError("The cloud service did not accept the timer. Refresh and check hOn.")
        return payload

    async def read(self, device):
        payload = await self.request("GET", device.mac_address)
        if not any(k in payload for k in BUCKETS):
            raise ControlError("The cloud service did not return timer status.")
        state, found = select_timers(payload)
        if "startProgram" not in device.commands or "iot_simple_start" not in device.commands["startProgram"].categories:
            state["on"]["supported"] = False
        if "stopProgram" not in device.commands:
            state["off"]["supported"] = False
        return state, found

    async def change(self, device, action, due, expected, requested=None):
        if action not in DATE:
            raise ControlError("Unknown timer action.")
        state, found = await self.read(device)
        current = state[action]
        if not current["supported"]:
            raise ControlError("There are conflicting or unsupported schedules. Manage them in hOn first.")
        if current["expected"] != expected:
            raise ControlError("This timer changed in hOn. Refresh its status before trying again.")
        item = found[action][0] if found[action] else None
        existing = item["record"] if item else None
        end_only = item["bucket"] == "scheduleRunningProgramEnd" if item else action == "off"
        other = "off" if action == "on" else "on"
        if due is None:
            if existing is None:
                return state
            other_due = utc_time(existing.get(DATE[other]))
            if other_due and other_due > datetime.now(timezone.utc):
                if not isinstance(existing.get(SETUP[other]), dict):
                    raise ControlError("The paired timer has an unfamiliar format. Manage it in hOn.")
                # Preserve the other half of a paired schedule.
                body = schedule_body(device, other, other_due, existing[SETUP[other]], existing, end_only)
                body.pop(DATE[action], None)
                body.pop(SETUP[action], None)
                await self.request("PUT", existing["id"], body)
            else:
                body = {"macAddress": device.mac_address, "maintenance": False}
                if end_only:
                    body["scheduleEnd"] = True
                await self.request("DELETE", existing["id"], body)
        else:
            device.attributes.clear()
            await device.update(force=True)
            command = command_payload(device, action, self.handler, requested)
            body = schedule_body(device, action, due, command, existing, end_only)
            await self.request("PUT" if existing else "POST", existing["id"] if existing else "", body)
        # Only show an active/cleared timer after authoritative readback.
        wanted = iso(due) if due else None
        for attempt in range(3):
            updated, _ = await self.read(device)
            actual = updated[action]["expected"]
            if updated[action]["supported"] and (actual[1] if actual else None) == wanted:
                return updated
            if attempt < 2:
                await asyncio.sleep(1)
        raise ControlError("The timer request was sent, but its saved status is not confirmed. Check hOn before retrying.")
