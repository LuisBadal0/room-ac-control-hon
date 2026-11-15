"""Windows notifications for changes the AC reports while the app waits in the notification area.

Each refresh is compared with the previous one for the same AC. A new error code, a
filter reminder, the AC going offline, and the AC turning on or off are worth a
notification; the cause of a power change is named when a saved timer was due. Changes
this app just asked for are not announced: the person made them.
"""

from datetime import datetime, timedelta

# How close to a timer's due time a power change counts as the timer's doing.
TIMER_EARLY = timedelta(minutes=2)
TIMER_LATE = timedelta(minutes=15)


def due(snapshot, action):
    """When the saved on or off timer was due, as a local time, or None."""
    timers = snapshot.get("timers") or {}
    values = timers.get("values") if timers.get("available") else None
    entry = (values or {}).get(action) or {}
    value = entry.get("due")
    return value if isinstance(value, datetime) else None


def errors(snapshot):
    return {alert.get("code") for alert in snapshot.get("alerts") or [] if alert.get("kind") == "error"}


def kinds(snapshot):
    return {alert.get("kind") for alert in snapshot.get("alerts") or []}


def changes(previous, current, now=None, own_power_change=False):
    """Notifications as (title, message) pairs, English source text with {name} and {code} fields.

    `own_power_change` is True right after this app sent a power or settings command."""
    if not previous or previous.get("id") != current.get("id"):
        return []
    now = now or datetime.now()
    name = current.get("name") or "Room AC Control"
    result = []
    for code in sorted(errors(current) - errors(previous), key=str):
        result.append(("{name}: AC error", "The AC reports error {code}. Check it in the hOn app.", code))
    if "filter" in kinds(current) and "filter" not in kinds(previous):
        result.append(("{name}: clean the air filter", "The AC reports that its filter needs cleaning.", None))
    if previous.get("connection") == "CONNECTED" and current.get("connection") == "DISCONNECTED":
        result.append(("{name} is offline", "The cloud service lost the connection to the AC.", None))
    before, after = previous.get("power"), current.get("power")
    if {before, after} == {"On", "Off"} and not own_power_change:
        action = "on" if after == "On" else "off"
        when = due(previous, action)
        timer = when is not None and when - TIMER_EARLY <= now <= when + TIMER_LATE
        if action == "off":
            message = "Turned off by its End at timer." if timer else "Turned off outside this app."
            result.append(("{name} turned off", message, None))
        else:
            message = "Turned on by its start timer." if timer else "Turned on outside this app."
            result.append(("{name} turned on", message, None))
    return [{"title": title, "message": message, "name": name, "code": code} for title, message, code in result]


def text(language, notification):
    """The notification's title and message in the app's language, with the AC's name and code."""
    title = language.translate(notification["title"]).format(name=notification["name"])
    message = language.translate(notification["message"]).format(code=notification["code"] or "")
    return title, message
