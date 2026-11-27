"""When each maintenance routine last ran.

Runs come from hOn's command history, from routines this app starts, and from the AC
reporting a self-clean switch as on. hOn keeps only the last few commands, so every run
seen is also kept in the encrypted local state."""

from datetime import UTC, datetime, timedelta

from .controller import code, function_group

# Self-clean programs and the switches that start the same cycles share one history.
PROGRAM_ROUTINES = {"iot_self_clean": "selfCleaningStatus", "iot_self_clean_56": "selfCleaning56Status"}
SWITCH_ROUTINES = ("selfCleaning56Status", "selfCleaningStatus")
# Older runs read better as a date than as "Last run 336 days ago".
OLD_AFTER_DAYS = 60


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
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def runs_from_hon(dates):
    """hOn's own last self-clean dates (`lastSelfClean`, `lastSelfClean56`) as {routine: datetime}."""
    runs = {}
    for routine, text in (dates or {}).items():
        when = parse_time(text) if routine in SWITCH_ROUTINES and text else None
        if when is not None:
            runs[routine] = when
    return runs


# hOn's dates are also kept under this prefix, so each one counts once: a date the person
# sets by hand stays until hOn reports a different one.
HON_SEEN = "hon:"


def new_hon_runs(dates, saved):
    """hOn's last self-clean dates not seen before, with the record that marks them seen."""
    runs = {routine: when for routine, when in runs_from_hon(dates).items() if saved.get(HON_SEEN + routine) != when}
    return {**runs, **{HON_SEEN + routine: when for routine, when in runs.items()}}


# hOn 2.32.11 counts down 30 days from the last self-clean (or from when the AC was added
# to the account) and colours the count at 10 days or fewer, then at 3 or fewer.
SELF_CLEAN_DAYS = 30
SELF_CLEAN_WARNING = 10
SELF_CLEAN_DANGER = 3


def self_clean_due(routine, last_run, enrolled=None, now=None):
    """Days left until a self-clean is due and how urgent that is, as ({count}, "ok"|"warning"|"danger").

    None for other routines, or when neither a run nor the date the AC was added is known."""
    from math import ceil

    start = last_run or enrolled
    if routine not in SWITCH_ROUTINES or start is None:
        return None
    now = now or datetime.now(UTC)
    left = max(0, ceil((start + timedelta(days=SELF_CLEAN_DAYS) - now).total_seconds() / 86400))
    level = "danger" if left <= SELF_CLEAN_DANGER else "warning" if left <= SELF_CLEAN_WARNING else "ok"
    return left, level


def runs_from_history(history):
    """The latest start of each maintenance routine in hOn's command history, as {routine: datetime}."""
    runs: dict[str, datetime] = {}
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


def running_programs(snapshot):
    """Self-clean programs the AC reports as running, as routines."""
    program = str(snapshot.get("program") or "").lower().split(".")[-1]
    return [PROGRAM_ROUTINES[program]] if snapshot.get("power") == "On" and program in PROGRAM_ROUTINES else []


def last_run_text(when, now=None):
    """("Last run {count} days ago", {"count": 12}) and similar, ready for translation.

    Runs more than OLD_AFTER_DAYS ago give their date instead: ("Last run on {date}", {"date": when})."""
    if when is None:
        return "No run recorded yet", {}
    now = now or datetime.now(UTC)
    seconds = max(0, (now - when).total_seconds())
    if seconds < 60:
        return "Last run just now", {}
    if seconds < 3600:
        return "Last run {count} min ago", {"count": int(seconds // 60)}
    if seconds < 86400:
        hours = int(seconds // 3600)
        return ("Last run 1 hour ago", {}) if hours == 1 else ("Last run {count} hours ago", {"count": hours})
    days = int(seconds // 86400)
    if days == 1:
        return "Last run yesterday", {}
    if days < OLD_AFTER_DAYS:
        return "Last run {count} days ago", {"count": days}
    return "Last run on {date}", {"date": when}


def parse_day(text, today):
    """A typed date such as 06/12/2025 (day first; / - . or spaces) as a date, or None.

    Dates in the future or before 2000 are refused."""
    from datetime import date

    parts = [part for part in str(text).replace("-", "/").replace(".", "/").replace(" ", "/").split("/") if part]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    day, month, year = (int(part) for part in parts)
    if year < 100:
        year += 2000
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    return value if date(2000, 1, 1) <= value <= today else None


def day_to_time(day):
    """A chosen day as midday local time, in UTC, so it never shifts to another day."""
    return datetime(day.year, day.month, day.day, 12).astimezone().astimezone(UTC)
