"""When each maintenance routine last ran.

Runs come from hOn's command history, from routines this app starts, and from the AC
reporting a self-clean switch as on. hOn keeps only the last few commands, so every run
seen is also kept in the encrypted local state."""
from datetime import datetime, timezone

from .controller import code, function_group

# Self-clean programs and the switches that start the same cycles share one history.
PROGRAM_ROUTINES = {"iot_self_clean": "selfCleaningStatus", "iot_self_clean_56": "selfCleaning56Status"}
SWITCH_ROUTINES = ("selfCleaning56Status", "selfCleaningStatus")


def routine_for(command, category):
    """The routine a maintenance program runs, shared with its matching switch."""
    category = str(category or "").lower().split(".")[-1]
    return PROGRAM_ROUTINES.get(category, f"{command}:{category}")


def item_routine(item):
    """The routine behind a Maintenance card: a switch or a program."""
    if item["kind"] == "setting":
        return item["key"]
    return routine_for(item["command"], item["form"]["category"])


def switched_on(values):
    """Routines a set of parameters turns on, such as {"selfCleaningStatus": "1"}."""
    return [key for key in SWITCH_ROUTINES if code((values or {}).get(key)) == "1"]


def parse_time(text):
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def runs_from_history(history):
    """The latest start of each maintenance routine in hOn's command history, as {routine: datetime}."""
    runs = {}
    for entry in history if isinstance(history, list) else []:
        command = entry.get("command") if isinstance(entry, dict) else None
        if not isinstance(command, dict):
            continue
        when = parse_time(command.get("timestamp") or str(entry.get("SK_Secondary", "")).partition("#")[2])
        if when is None:
            continue
        parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
        name = str(command.get("commandName") or "")
        routines = switched_on(parameters)
        program = str(command.get("programName") or "").lower().split(".")[-1]
        if not routines and name == "startProgram" and program and function_group(name, program) == "maintenance":
            routines = [routine_for(name, program)]
        for routine in routines:
            if routine not in runs or when > runs[routine]:
                runs[routine] = when
    return runs


def last_run_text(when, now=None):
    """("Last run {count} days ago", count) and similar, ready for translation."""
    if when is None:
        return "No run recorded yet", None
    now = now or datetime.now(timezone.utc)
    seconds = max(0, (now-when).total_seconds())
    if seconds < 60:
        return "Last run just now", None
    if seconds < 3600:
        return "Last run {count} min ago", int(seconds//60)
    if seconds < 86400:
        hours = int(seconds//3600)
        return ("Last run 1 hour ago", None) if hours == 1 else ("Last run {count} hours ago", hours)
    days = int(seconds//86400)
    return ("Last run yesterday", None) if days == 1 else ("Last run {count} days ago", days)
