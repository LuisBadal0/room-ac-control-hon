"""Tabs, preset ordering, search and labels for All functions; no Tk widgets."""

from ..control_choices import mode_icon
from ..controller import code, function_group, mode_choices
from ..i18n import search_text, tr, translator
from ..routine_history import last_run_text
from ..secure_state import TOP_PRESET_LIMIT

SECTIONS = (("settings", "Settings"), ("everyday", "Everyday use"), ("maintenance", "Maintenance"))
TABS = SECTIONS + (("schedules", "Schedules"),)
SECTION_GLYPHS = {"settings": "sliders", "everyday": "sparkle", "maintenance": "wrench", "schedules": "clock"}
SIZE = (540, 920)
WIDTH = 500
NEUTRAL = {"Off", "Unknown", "Unavailable"}
# The everyday presets shown ahead of the "More" section until the user picks their own
# (at most TOP_PRESET_LIMIT).
PRESETS_UP_FRONT = ("cool", "coolnight", "heat", "heatnight")
# A preset card's settings grid shows this many tiles. 10°C heating is a separate preset,
# not a setting of Heat, so Heat presets show their target temperature there instead, like Cool.
GRID_TILES = 6
HIDDEN_IN_GRID = {"10degreeHeatingStatus"}
# Maintenance cards: height plus the gap below.
ROUTINE_STEP = 236
# Starting values for presets that have not been saved yet.
PRESET_DEFAULTS = {"heat": {"tempSel": "24"}, "heatnight": {"tempSel": "24", "muteStatus": "1"}}


def preset_key(item):
    return item["label"].lower().replace(" ", "")


def everyday_layout(items, modes, chosen=None):
    """Split Everyday use presets into (choices, top, more), each preset once.

    `chosen` lists the preset keys picked to show first, in order (None: the defaults).
    Presets that only repeat a mode from the mode bar (Auto, Dry, Fan, a second Cool…)
    are left out, except the default top presets; whatever is not on top goes in More."""
    repeats = set(modes) | {mode + "night" for mode in modes}
    choices, seen = [], set()
    for item in items:
        key = preset_key(item)
        if key not in seen and (key in PRESETS_UP_FRONT or key not in repeats):
            seen.add(key)
            choices.append(item)
    rank = {key: index for index, key in enumerate(PRESETS_UP_FRONT)}
    choices.sort(key=lambda item: rank.get(preset_key(item), len(rank)))
    by_key = {preset_key(item): item for item in choices}
    picked = PRESETS_UP_FRONT if chosen is None else chosen
    top = [by_key[key] for key in dict.fromkeys(picked) if key in by_key][:TOP_PRESET_LIMIT]
    on_top = {preset_key(item) for item in top}
    return choices, top, [item for item in choices if preset_key(item) not in on_top]


def toggle_top_preset(chosen, key):
    """Add or remove one top preset: (new choice, refused). Adding a fifth is refused."""
    if key in chosen:
        return [other for other in chosen if other != key], False
    if len(chosen) >= TOP_PRESET_LIMIT:
        return list(chosen), True
    return [*chosen, key], False


# Shown in the Comfort card rather than as feature tiles or extra rows.
COMFORT = {"machMode", "windSpeed", "windDirectionVertical", "windDirectionHorizontal", "tempSel", "onOffStatus"}
# Feature tiles: glyph, the accent they take, and a short explanation.
FEATURES = {
    "ecoMode": ("leaf", "dry", "Limits power use"),
    "muteStatus": ("speaker", "fan", "Quieter, slower to reach temperature"),
    "silentSleepStatus": ("moon", "cool", "Eases the temperature through the night"),
    "echoStatus": ("bell", "heat", "Beeps when the AC gets a command"),
}
FEATURE_ORDER = ("ecoMode", "muteStatus", "silentSleepStatus", "echoStatus")
AIRFLOW_NOTES = {
    "Swing": "Louver moves up and down",
    "Position 1": "Most closed",
    "Position 2": "Slightly open",
    "Position 3": "Half open",
    "Position 4": "Mostly open",
    "Position 5": "Most open",
}
FAN_LEVELS = {"Low": 1, "Medium": 2, "High": 3}


def matches_search(item, query):
    """Match words in names, descriptions and user-facing adjustable options."""
    parts = [item["label"], item.get("description", ""), item.get("command_label", "")]
    specs = [item["spec"]] if item["kind"] == "setting" else item.get("form", {}).get("parameters", [])
    for spec in specs:
        parts.append(spec["label"])
        parts.extend(spec.get("options", {}))
    text = search_text(parts)
    return all(word in text for word in search_text([query]).split())


def section_items(device, section):
    items = []
    if section in {"settings", "maintenance"}:
        for key, spec in device.get("controls", {}).items():
            if key == "onOffStatus":
                continue
            group = function_group(key, label=spec["label"])
            if (section == "maintenance") != (group == "maintenance"):
                continue
            items.append(
                {
                    "kind": "setting",
                    "key": key,
                    "label": spec["label"],
                    "spec": spec,
                    "description": spec.get("description", ""),
                }
            )
    if section in {"everyday", "maintenance"}:
        for command, entry in device.get("commands", {}).items():
            for form in entry["forms"]:
                group = form.get("group", function_group(command, form["category"], form["label"]))
                if group != section:
                    continue
                items.append(
                    {
                        "kind": "function",
                        "command": command,
                        "form": form,
                        "label": form["label"],
                        "command_label": entry["label"],
                    }
                )
    if section == "everyday":
        existing = {item["label"].lower().replace(" ", "") for item in items}
        for option in mode_choices(device):
            if option["label"].endswith(" Night") and option["label"].lower().replace(" ", "") not in existing:
                items.append(
                    {
                        "kind": "night",
                        "label": option["label"],
                        "changes": option["value"],
                        "description": option["description"],
                    }
                )
    return items


def glyph_for(name):
    name = name.lower()
    if name in {"auto", "cool", "dry", "heat", "fan", "cool night", "heat night"}:
        return mode_icon(name)
    if "fan" in name:
        return "fan"
    if "airflow" in name or "wind" in name:
        return "swing"
    if "sleep" in name or "night" in name:
        return "moon"
    if "quiet" in name or "silent" in name or "mute" in name:
        return "speaker"
    if "buzzer" in name or "echo" in name:
        return "bell"
    if "eco" in name or "health" in name:
        return "leaf"
    if "clean" in name or "steril" in name:
        return "sparkle"
    if "temperature" in name:
        return "thermo"
    if "cool" in name or "mode" in name or "temp" in name:
        return "snow"
    return "sliders"


def is_toggle(spec):
    return (
        spec.get("kind") == "enum"
        and len(spec.get("options", {})) == 2
        and {code(value) for value in spec["options"].values()} == {"0", "1"}
    )


def option_label(spec, value):
    from ..dashboard import equal

    if value is None:
        return "Unknown"
    if spec.get("kind") == "enum":
        return next((label for label, option in spec.get("options", {}).items() if equal(option, value)), "Unknown")
    try:
        number = f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)
    return number + ("°" if spec.get("key") == "tempSel" else "")


def last_run_label(c, when):
    """A Maintenance card's last-run line, translated, with numbers and dates in the app's language."""
    text, fields = last_run_text(when)
    language = translator(c)
    shown = {}
    if "count" in fields:
        shown["count"] = language.number(fields["count"])
    if "date" in fields:
        local = fields["date"].astimezone()
        # "06 Dec 2025": the day and month as the app writes them, then the year.
        shown["date"] = language.date(local).split(" ", 1)[1] + f" {local.year}"
    return tr(c, text).format(**shown)


def louver_position(label):
    return int(label[-1]) if label.startswith("Position ") and label[-1].isdigit() else 0
