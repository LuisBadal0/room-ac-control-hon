"""What an AC reports and supports, read from pyhOn's appliance without changing it.

The dashboard's device snapshot (`describe`), the controls and presets an AC exposes,
its sensors and alerts, and checks that a requested value is one it accepts.
"""

import re
from datetime import datetime

MODES = {"0": "Auto", "1": "Cool", "2": "Dry", "3": "Dry", "4": "Heat", "5": "Fan", "6": "Fan"}
FANS = {"1": "High", "2": "Medium", "3": "Low", "4": "Auto", "5": "Auto"}
FIELDS = {
    "tempSel": "Target temperature",
    "machMode": "Mode",
    "windSpeed": "Fan speed",
    "ecoMode": "Eco mode",
    "silentSleepStatus": "Sleep",
    "muteStatus": "Silent mode",
    "rapidMode": "Turbo / rapid mode",
    "healthMode": "Health / purification",
    "screenDisplayStatus": "Unit display",
    "echoStatus": "Buzzer (Echo)",
    "10degreeHeatingStatus": "10°C heating",
    "selfCleaningStatus": "Self cleaning",
    "selfCleaning56Status": "56°C self cleaning",
    "humanSensingStatus": "Eco pilot",
    "windDirectionHorizontal": "Horizontal airflow",
    "windDirectionVertical": "Vertical airflow",
    "onOffStatus": "Power",
    "lightStatus": "Light",
    "delayTime": "Start delay",
}
VERTICAL = {"2": "Position 1", "4": "Position 2", "5": "Position 3", "6": "Position 4", "7": "Position 5", "8": "Swing"}
HORIZONTAL = {
    "0": "Position 1",
    "3": "Position 2",
    "4": "Position 3",
    "5": "Position 4",
    "6": "Position 5",
    "7": "Swing",
}
VALUE_LABELS = {
    "machMode": MODES,
    "windSpeed": FANS,
    "windDirectionVertical": VERTICAL,
    "windDirectionHorizontal": HORIZONTAL,
    "humanSensingStatus": {"0": "Off", "1": "Avoid direct airflow", "2": "Follow person", "3": "Other"},
}
INTERNAL = {"prStr", "prCode", "program", "category", "favourite", "zoneMap"}
CONTROL_DESCRIPTIONS = {
    "muteStatus": "Quieter AC operation. Separate from Sleep and command sounds.",
    "echoStatus": "Unit command-feedback buzzer setting. Separate from Silent mode.",
}
MAINTENANCE_TERMS = (
    "clean",
    "steriliz",
    "sterilis",
    "descal",
    "maintenance",
    "service",
    "diagnos",
    "calibrat",
    "reset",
    "filter",
    "test",
)


def function_group(command_name, category="", label="", parameters=None):
    """Classify each preset independently; ordinary Dry/Health modes are everyday use."""
    if command_name in FIELDS:
        # muteStatus contains "test" across its word boundary; it is a comfort setting.
        return "maintenance" if command_name in {"selfCleaningStatus", "selfCleaning56Status"} else "everyday"
    name = " ".join((command_name, category, label)).lower()
    if any(term in name for term in MAINTENANCE_TERMS):
        return "maintenance"
    for key in ("selfCleaningStatus", "selfCleaning56Status"):
        parameter = (parameters or {}).get(key)
        if parameter and parameter.typology == "fixed" and code(parameter.value) == "1":
            return "maintenance"
    return "everyday"


def readable(name):
    if name in FIELDS:
        return FIELDS[name]
    name = name.split(".")[-1].replace("iot_", "").replace("_", " ")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip().capitalize()


def parameter_spec(key, parameter, device, reported=True):
    if parameter.typology not in {"enum", "range"} or key in INTERNAL:
        return None
    current = device.get(key) if reported else None
    spec = {
        "key": key,
        "label": readable(key),
        "kind": parameter.typology,
        "value": parameter.value if current is None else current,
        "reported": current is not None,
    }
    if key in CONTROL_DESCRIPTIONS:
        spec["description"] = CONTROL_DESCRIPTIONS[key]
    if parameter.typology == "range":
        spec.update(min=parameter.min, max=parameter.max, step=parameter.step)
        if parameter.min == parameter.max:
            return None
        if parameter.min == 0 and parameter.max == 1 and parameter.step == 1:
            spec.update(kind="enum", options={"Off": "0", "On": "1"})
    else:
        values = list(parameter.values)
        if len(values) < 2:
            return None
        labels = VALUE_LABELS.get(key, {})
        if set(values) == {"0", "1"} and key not in VALUE_LABELS:
            labels = {"0": "Off", "1": "On"}
        spec.update(
            options=choices(parameter, labels)
            if labels
            else {readable(v) if not v.isnumeric() else v: v for v in values}
        )
    return spec


def capabilities(device):
    controls = {}
    command = device.commands.get("settings")
    if command:
        for key, parameter in command.settings.items():
            if parameter.group != "parameters":
                continue
            if spec := parameter_spec(key, parameter, device):
                controls[key] = spec
    programs = []
    start = device.commands.get("startProgram")
    if start:
        selector = start.settings.get("program")
        if selector:
            programs = [{"value": value, "label": readable(value)} for value in selector.values]
    commands = {}
    for name, command in device.commands.items():
        if name in {"settings", "stopProgram"}:
            continue
        forms = []
        for category, variant in command.categories.items():
            params = []
            for key, parameter in variant.settings.items():
                if parameter.group == "parameters" and key != "onOffStatus":
                    if spec := parameter_spec(key, parameter, device, reported=False):
                        params.append(spec)
            label = readable(category) if category != "_" else readable(name)
            forms.append(
                {
                    "category": category,
                    "label": label,
                    "parameters": params,
                    "group": function_group(name, category, label, variant.settings),
                }
            )
        commands[name] = {"label": "Start preset" if name == "startProgram" else readable(name), "forms": forms}
    return controls, programs, commands


class ControlError(Exception):
    """Safe, user-facing message with no account information."""


def code(value):
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value)


# hOn 2.32.11 lets Turbo run alone: turning it on ends Silent mode and Sleep, and
# turning either of those on, or choosing a fan speed, ends Turbo.
TURBO_CONFLICTS = {
    "rapidMode": ("muteStatus", "silentSleepStatus"),
    "muteStatus": ("rapidMode",),
    "silentSleepStatus": ("rapidMode",),
}
TURBO_NOTICES = {
    "rapidMode": "Turbo turns off Silent mode and Sleep.",
    "muteStatus": "Silent mode turns off Turbo.",
    "silentSleepStatus": "Sleep turns off Turbo.",
    "windSpeed": "Choosing a fan speed turns off Turbo.",
}


def turbo_conflicts(key, value, current, controls):
    """The switches to turn off with this change, as hOn does, and why.

    `current(name)` gives a setting's value including unsent changes. Only switches
    this AC has and that are on now are returned.
    """
    off: tuple[str, ...]
    if key == "windSpeed":
        off = ("rapidMode",)
    elif key in TURBO_CONFLICTS and code(value) == "1":
        off = TURBO_CONFLICTS[key]
    else:
        return {}, None
    changes = {name: "0" for name in off if name in controls and code(current(name)) == "1"}
    return changes, TURBO_NOTICES[key] if changes else None


def choices(parameter, labels):
    if parameter is None:
        return {}
    result = {}
    for value in parameter.values:
        label = labels.get(code(value), f"Other ({value})")
        if label in result:
            label += f" ({value})"
        result[label] = str(value)
    return result


def mode_choices(snapshot):
    """Night choices are supported mode + Sleep combinations, never new HVAC codes."""
    sleep = snapshot.get("controls", {}).get("silentSleepStatus", {})
    sleep_values = set(sleep.get("options", {}).values())
    result = []
    for label, value in snapshot.get("modes", {}).items():
        patch = {"machMode": value}
        if "0" in sleep_values:
            patch["silentSleepStatus"] = "0"
        result.append(
            {
                "label": label,
                "value": patch,
                "description": "Standard mode",
                "glyph": {"Auto": "leaf", "Cool": "snow", "Dry": "drop", "Heat": "sun", "Fan": "fan"}.get(
                    label, "wind"
                ),
            }
        )
    if "1" in sleep_values:
        for label, value in snapshot.get("modes", {}).items():
            if label in {"Cool", "Heat"}:
                result.append(
                    {
                        "label": label + " Night",
                        "value": {"machMode": value, "silentSleepStatus": "1"},
                        "description": ("Cooling" if label == "Cool" else "Heating") + " with Sleep enabled",
                    }
                )
    return result


def mode_label(snapshot, pending=None):
    pending = pending or {}
    mode = snapshot.get("controls", {}).get("machMode", {})
    current = mode.get("value") if mode.get("reported") else None
    selected = pending.get("machMode", current)
    label = next(
        (label for label, value in snapshot.get("modes", {}).items() if value == code(selected)),
        snapshot.get("mode", "Unknown"),
    )
    sleep = snapshot.get("controls", {}).get("silentSleepStatus", {})
    sleep_value = pending.get("silentSleepStatus", sleep.get("value") if sleep.get("reported") else None)
    return label + " Night" if label in {"Cool", "Heat"} and code(sleep_value) == "1" else label


# hOn 2.30.7 shows the AC's airQuality level on every series except "jade": 0 and 1
# as good, 2 as medium, 3 as bad. A unit without the sensor reports 0 and hOn shows
# it as good too, so the dashboard matches what the person sees in hOn.
AIR_QUALITY = {"0": "Good", "1": "Good", "2": "Medium", "3": "Poor"}
NO_AIR_QUALITY_SERIES = {"jade"}


def reading(device, key, low, high):
    """A reported sensor value; sensors a unit lacks report 0, so 0 is hidden."""
    try:
        number = float(device.get(key))
    except (TypeError, ValueError):
        return None
    return number if number != 0 and low <= number <= high else None


def sensors(device):
    """Read-only values the AC reports alongside its settings."""
    result = {}
    outdoor = reading(device, "tempOutdoor", -40, 60)
    if outdoor is not None:
        result["outdoor"] = outdoor
    humidity = reading(device, "humidityIndoor", 1, 100)
    if humidity is not None:
        result["humidity"] = humidity
    if str(device.info.get("series", "")).lower() not in NO_AIR_QUALITY_SERIES:
        level = code(device.get("airQuality"))
        if quality := AIR_QUALITY.get(level):
            result["air"] = quality
            # Level 0 is also what a unit without the sensor reports: not a measurement.
            result["air_measured"] = level != "0"
    return result


def alerts(device):
    """Conditions the AC reports, most severe first (hOn 2.30.7 AC parameters).

    hOn treats any errors value other than "00" as an error. Defrosting is
    defrostStatus, or manualDefrostingStatus on units with manual defrost.
    filterChangeStatusLocal is the unit's filter flag.
    """
    result = []
    error = device.get("errors")
    if error is not None and str(error).strip() and code(error) != "0":
        result.append({"kind": "error", "code": str(error).strip()})
    if "1" in {code(device.get("defrostStatus")), code(device.get("manualDefrostingStatus"))}:
        result.append({"kind": "defrost"})
    if code(device.get("filterChangeStatusLocal")) == "1":
        result.append({"kind": "filter"})
    return result


def describe(device):
    settings = device.settings
    temp = settings.get("settings.tempSel")
    power = code(device.get("onOffStatus"))
    controls, programs, commands = capabilities(device)
    return {
        "id": device.unique_id,
        "name": device.nick_name or device.model_name or "Room AC Control",
        "model": device.model_name,
        "power": {"0": "Off", "1": "On"}.get(power, "Unknown"),
        "room": device.get("tempIndoor"),
        "target": device.get("tempSel"),
        "program": device.get("programName"),
        "mode": MODES.get(code(device.get("machMode")), "Unknown"),
        "fan": FANS.get(code(device.get("windSpeed")), "Unknown"),
        "modes": choices(settings.get("settings.machMode"), MODES),
        "fans": choices(settings.get("settings.windSpeed"), FANS),
        "temperatures": list(temp.values) if temp else [],
        "can_on": "settings.onOffStatus" in settings and "settings" in device.commands,
        "can_off": "stopProgram" in device.commands,
        "can_apply": "settings" in device.commands,
        "connection": device.get("attributes.lastConnEvent.category", "Unknown"),
        "fetched": datetime.now().strftime("%H:%M:%S"),
        "controls": controls,
        "programs": programs,
        "commands": commands,
        "sensors": sensors(device),
        "alerts": alerts(device),
    }


def validate(parameter, value):
    if parameter.typology == "range":
        try:
            number = float(value)
            ticks = (number - parameter.min) / parameter.step
            valid = parameter.min <= number <= parameter.max and abs(ticks - round(ticks)) < 1e-6
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ControlError("Choose a value within the AC's supported range and step.")
    elif str(value) not in parameter.values:
        raise ControlError("Choose a setting supported by this AC.")
