"""Local wall-clock timers; dispatch once, persist before sending, never catch up late."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import re


def time_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Enter a time in 24-hour HH:MM format, for example 22:30.")
    return value


def next_time(value, now):
    hour, minute = map(int, time_value(value).split(":"))
    result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return result if result > now else result + timedelta(days=1)


@dataclass(frozen=True)
class TimerEvent:
    device: str
    action: str
    due: str


class TimerBook:
    """Account/device isolation, injectable clock, and a 60-second dispatch window."""
    def __init__(self, state):
        self.state = state

    def get(self, account, device):
        records = self.state.schedules(account).get(device, {})
        result = {}
        for action in ("on", "off"):
            entry = records.get(action, {}) if isinstance(records, dict) else {}
            try:
                time_value(entry["time"])
                due = datetime.fromisoformat(entry["next"])
                if due.tzinfo is not None or entry["repeat"] not in {"daily", "once"}:
                    raise ValueError("Invalid timer")
                if type(entry["enabled"]) is not bool:
                    raise ValueError("Invalid timer")
                result[action] = dict(entry)
            except (KeyError, ValueError, TypeError):
                result[action] = {"enabled": False, "time": "08:00" if action == "on" else "22:00",
                                  "repeat": "daily", "next": "", "last_result": ""}
        return result

    def save(self, account, device, settings, now=None):
        now = now or datetime.now()
        previous = self.get(account, device)
        records = deepcopy(self.state.schedules(account))
        entries = {}
        for action in ("on", "off"):
            entry = dict(settings[action])
            time_value(entry["time"])
            if type(entry["enabled"]) is not bool or entry["repeat"] not in {"daily", "once"}:
                raise ValueError("Choose a valid timer and repeat option.")
            old = previous[action]
            unchanged = all(entry[key] == old[key] for key in ("enabled", "time", "repeat"))
            entries[action] = old if unchanged and old["next"] else {
                **entry, "next": next_time(entry["time"], now).isoformat(), "last_result": ""}
        if all(entries[action]["enabled"] for action in entries) and entries["on"]["time"] == entries["off"]["time"]:
            raise ValueError("Choose different turn-on and turn-off times.")
        records[device] = entries
        self.state.save_schedules(account, records)

    def poll(self, account, devices, now=None, ready=True):
        """Expire missed events even while busy; emit at most one event per poll."""
        if not account:
            return None
        now = now or datetime.now()
        records = deepcopy(self.state.schedules(account))
        candidates, changed = [], False
        for device in devices:
            for action, entry in self.get(account, device).items():
                if not entry["enabled"] or not entry["next"]:
                    continue
                due = datetime.fromisoformat(entry["next"])
                if due > now:
                    continue
                if now - due > timedelta(seconds=60):
                    self.consume(entry, now, "missed")
                    records.setdefault(device, {})[action] = entry
                    changed = True
                elif ready:
                    candidates.append((due, action != "off", device, action, entry))
        event = None
        if candidates:
            _, _, device, action, entry = min(candidates, key=lambda item: item[:4])
            event = TimerEvent(device, action, entry["next"])
            self.consume(entry, now, "sending")
            records.setdefault(device, {})[action] = entry
            changed = True
        if changed:
            # A failed write raises before any command is emitted.
            self.state.save_schedules(account, records)
        return event

    @staticmethod
    def consume(entry, now, result):
        entry["last_due"] = entry["next"]
        entry["last_result"] = result
        if entry["repeat"] == "once":
            entry["enabled"] = False
        entry["next"] = next_time(entry["time"], now).isoformat()

    def finish(self, account, event, result):
        records = deepcopy(self.state.schedules(account))
        entry = records.get(event.device, {}).get(event.action, {})
        if entry.get("last_due") == event.due:
            entry["last_result"] = result
            self.state.save_schedules(account, records)

    def summary(self, account, device):
        entries = self.get(account, device)
        active = [f"{'On' if action == 'on' else 'Off'} {entry['time']}" for action, entry in entries.items() if entry["enabled"]]
        return " · ".join(active) or "No timers enabled"
