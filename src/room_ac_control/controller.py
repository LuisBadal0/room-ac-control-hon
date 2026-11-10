"""Cloud adapter; account persistence is handled by Windows-encrypted storage."""

import asyncio
import re
import time
from contextlib import suppress
from datetime import UTC, datetime

import aiohttp
from pyhon.appliance import HonAppliance
from pyhon.connection.api import HonAPI

from .live_updates import CloudUpdates

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


async def send_action(device, action, requested=None):
    """Refresh first; change only explicitly selected parameters."""
    if action not in {"on", "off", "apply", "configure", "execute"}:
        raise ControlError("Unknown action.")
    # Clear pyhOn's optimistic attribute locks before reading actual cloud status.
    device.attributes.clear()
    await device.update(force=True)
    if device.get("attributes.lastConnEvent.category") == "DISCONNECTED":
        raise ControlError("The cloud service reports this AC disconnected. Check it in the phone app.")
    if action == "execute":
        await execute_function(device, requested or {})
        return
    if action == "off":
        command = device.commands.get("stopProgram")
        if command is None:
            raise ControlError("This AC does not expose a power-off command.")
        if not await command.send():
            raise ControlError("The cloud service did not accept the command. Sign in again.")
        return
    command = device.commands.get("settings")
    if command is None:
        raise ControlError("This AC does not expose settings controls.")
    changes = dict(requested or {})
    allowed = set(capabilities(device)[0]) - {"onOffStatus"}
    if not set(changes).issubset(allowed):
        raise ControlError("Unsupported setting requested.")
    if action == "on":
        changes["onOffStatus"] = "1"
    elif action == "apply" and code(device.get("onOffStatus")) == "0":
        raise ControlError("The AC is off. Use Turn on with these settings.")
    elif code(device.get("onOffStatus")) not in {"0", "1"}:
        raise ControlError("Power status is unknown. Refresh or use the phone app.")
    if not changes:
        raise ControlError("No supported settings to apply.")
    # Validate the entire request before changing the command object.
    for key, value in changes.items():
        parameter = command.settings.get(key)
        if parameter is None:
            raise ControlError("A requested control is unavailable for this AC.")
        # hOn declares power as "fixed" on some ACs, then syncs its value to the
        # reported state. Only this explicit ON action may override that field.
        if (
            action == "on"
            and key == "onOffStatus"
            and parameter.typology == "fixed"
            and str(parameter.value) in {"0", "1"}
        ):
            continue
        validate(parameter, value)
    for key, value in changes.items():
        command.settings[key].value = str(value)
    if not await command.send_specific(list(changes)):
        raise ControlError("The cloud service did not accept the command. Sign in again.")


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


async def execute_function(device, request):
    name = request.get("command")
    if name not in capabilities(device)[2]:
        raise ControlError("This function is not exposed by this AC.")
    base = device.commands[name]
    category = request.get("category", "_")
    if category not in base.categories:
        raise ControlError("This preset is not exposed by this AC.")
    command = base.categories[category]
    changes = request.get("parameters", {})
    for key, value in changes.items():
        parameter = command.settings.get(key)
        if (
            parameter is None
            or key in INTERNAL
            or key == "onOffStatus"
            or parameter.typology not in {"enum", "range"}
            or parameter.group != "parameters"
        ):
            raise ControlError("Unsupported function parameter.")
        validate(parameter, value)
    previous = device.commands[name]
    device.commands[name] = command
    try:
        for key, value in changes.items():
            command.settings[key].value = str(value)
        # Set the active variant so pyhOn synchronizes the selected preset's state.
        if not await command.send():
            raise ControlError("The cloud service did not accept this function.")
    except BaseException:
        device.commands[name] = previous
        raise


class Controller:
    def __init__(self, on_change=None, memory=None):
        self.session = None
        self.api = None
        self.devices = {}
        self.lock = asyncio.Lock()
        self.on_change = on_change
        self.watch_task = None
        self.memory = memory
        self.active_functions = {}
        self.pending_changes = {}
        self.cloud_timers = None
        # Outside weather per AC: when it was loaded, when to load it next, and its values.
        self.weather_cache: dict[str, dict] = {}

    WEATHER_EVERY = 15 * 60  # hOn's forecast has one entry every three hours.
    WEATHER_KEEP = 3 * 60 * 60  # After a failed load, older values stay this long.
    WEATHER_TIMEOUT = 10  # Seconds; status refresh does not wait longer for the weather.

    async def weather(self, device, load=True):
        """Outside weather at the AC's location, as in hOn's Outdoor panel; {} when unknown.

        Loaded at most every 15 minutes; after a failure, tried again a minute later.
        Values older than three hours are not shown. Status refresh never waits long for it."""
        if self.api is None:
            return {}
        now = time.monotonic()
        entry = self.weather_cache.setdefault(device.unique_id, {"loaded": None, "retry": now, "values": {}})
        if load and now >= entry["retry"]:
            from . import weather

            try:
                values = await asyncio.wait_for(weather.load(self.api._hon, device), timeout=self.WEATHER_TIMEOUT)
                entry.update(loaded=now, retry=now + self.WEATHER_EVERY, values=values)
            except Exception as error:
                from .diagnostics import diagnostics

                diagnostics.record("weather_failed", error)
                entry["retry"] = now + 60
        if entry["loaded"] is None or now - entry["loaded"] > self.WEATHER_KEEP:
            return {}
        return dict(entry["values"])

    async def snapshot(self, device, timers=True, load_weather=True):
        """The device state the app shows: reported status, timers and outside weather."""
        snapshot = describe(device)
        if timers:
            snapshot["timers"] = await self.timer_status(device)
        snapshot["weather"] = await self.weather(device, load_weather)
        return snapshot

    def remember(self, snapshot, explicit=None):
        if self.memory:
            try:
                self.memory.remember_mode(snapshot, explicit)
            except OSError as error:
                from .diagnostics import diagnostics

                diagnostics.record("state_save_failed", error)
            self.note_running_routines(snapshot)

    def note_running_routines(self, snapshot):
        """Keep the time the AC reports a self-clean (switch on, or its program running), so runs
        started in the hOn app or with the remote count too while this app is open."""
        from .routine_history import running_programs, switched_on

        controls = snapshot.get("controls", {})
        running = switched_on({key: spec.get("value") for key, spec in controls.items() if spec.get("reported")})
        running += [routine for routine in running_programs(snapshot) if routine not in running]
        if running:
            now = datetime.now(UTC)
            self.memory.record_routine_runs(snapshot["id"], {routine: now for routine in running})

    def record_started_routine(self, device_id, action, requested, group=None):
        """Keep the time this app started a maintenance routine."""
        from .routine_history import routine_for, switched_on

        if not self.memory or not requested:
            return
        if action == "execute":
            routines = (
                [routine_for(requested["command"], requested.get("category", "_"))] if group == "maintenance" else []
            )
        else:
            routines = switched_on(requested) if action in {"configure", "apply", "on"} else []
        if routines:
            now = datetime.now(UTC)
            self.memory.record_routine_runs(device_id, {routine: now for routine in routines})

    async def routine_history(self, device_id):
        """Read (never change) hOn's recent command history for maintenance routine starts."""
        from .routine_history import runs_from_history

        if self.api is None:
            raise ControlError("The cloud service did not accept the command. Sign in again.")
        device = self.devices[device_id]
        return runs_from_history(await self.api.load_command_history(device))

    async def connect(self, email, password):
        await self.close()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35))
        try:
            self.api = await HonAPI(email, password, session=self.session).create()
            from .cloud_timers import CloudTimers

            self.cloud_timers = CloudTimers(self.api._hon)
            for info in await self.api.load_appliances():
                if info.get("applianceTypeName") != "AC":
                    continue
                zones = int(info.get("zone") or 0)
                for zone in range(1, zones + 1) if zones > 1 else [0]:
                    device = HonAppliance(self.api, info.copy(), zone=zone)
                    await device.load_commands()
                    await device.update(force=True)
                    self.devices[device.unique_id] = device
            if not self.devices:
                raise ControlError("No AC found. Use the same cloud account that controls it on your phone.")
            if self.memory:
                self.memory.use_account(email)
                for device in self.devices.values():
                    self.remember(describe(device))
            if self.on_change:
                self.watch_task = asyncio.create_task(self.watch_updates())
            return [await self.snapshot(device) for device in self.devices.values()]
        except BaseException:
            await self.close()
            raise

    async def refresh(self, device_id):
        device = self.devices[device_id]
        device.attributes.clear()
        await device.update(force=True)
        snapshot = await self.snapshot(device)
        self.confirm_changes(snapshot)
        if not snapshot.get("pending_changes"):
            self.remember(snapshot)
        active = self.active_functions.get(device_id)
        if active and snapshot["power"] == "On" and self.memory and active.get("group") != "maintenance":
            from .program_memory import mode_key

            program = str(snapshot.get("program") or "").lower().split(".")[-1]
            wrong_program = program.startswith("iot_") and program != active["category"].lower()
            if mode_key(snapshot) == active["mode"] and not wrong_program:
                active["confirmed"] = True
                command = device.commands.get(active["command"])
                variant = command.categories.get(active["category"]) if command else None
                if variant:
                    values = {
                        key: device.get(key)
                        for key, param in variant.settings.items()
                        if key not in INTERNAL
                        and param.group == "parameters"
                        and param.typology in {"range", "enum"}
                        and device.get(key) is not None
                    }
                    with suppress(OSError):
                        self.memory.remember_function(device_id, active["command"], active["category"], values)
            elif active.get("confirmed"):
                self.active_functions.pop(device_id, None)
        return snapshot

    def confirm_changes(self, snapshot):
        pending = self.pending_changes.get(snapshot["id"])
        if not pending:
            return
        controls = snapshot.get("controls", {})

        def matches(key, value):
            spec = controls.get(key, {})
            if not spec.get("reported"):
                return False
            try:
                return float(spec["value"]) == float(value)
            except (TypeError, ValueError):
                return str(spec["value"]) == str(value)

        remaining = {key: value for key, value in pending["values"].items() if not matches(key, value)}
        if not remaining or time.monotonic() >= pending["deadline"]:
            self.pending_changes.pop(snapshot["id"], None)
            if remaining:
                snapshot["confirmation_expired"] = True
        else:
            pending["values"] = remaining
            snapshot["pending_changes"] = dict(remaining)

    async def timer_status(self, device):
        if self.cloud_timers is None:
            return {"available": False, "error": "Timers unavailable"}
        try:
            state, _ = await asyncio.wait_for(self.cloud_timers.read(device), timeout=10)
            return {"available": True, "values": state}
        except Exception as error:
            from .diagnostics import diagnostics

            diagnostics.record("timer_status_failed", error)
            return {"available": False, "error": "Timers unavailable · Refresh"}

    async def change_timer(self, device_id, action, due, expected=None, requested=None):
        if self.cloud_timers is None:
            raise ControlError("The hOn timer connection is unavailable. Sign in again.")
        device = self.devices[device_id]
        values = await self.cloud_timers.change(device, action, due, expected, requested)
        snapshot = await self.snapshot(device, timers=False, load_weather=False)
        snapshot["timers"] = {"available": True, "values": values}
        return snapshot

    def schedules(self):
        if self.cloud_timers is None:
            raise ControlError("The hOn timer connection is unavailable. Sign in again.")
        from .schedules import Schedules

        return Schedules(self.cloud_timers)

    async def schedule_list(self, device_id):
        return await self.schedules().rows(self.devices[device_id])

    async def change_schedule(self, device_id, operation, **options):
        """Save, switch on/off or delete a schedule, then refresh the inline timers."""
        device = self.devices[device_id]
        service = self.schedules()
        if operation == "save":
            result = await service.save(device, **options)
        elif operation == "active":
            result = {
                "saved": True,
                "rows": await service.set_active(device, options["ident"], options["active"]),
                "conflicts": [],
            }
        elif operation == "delete":
            result = {"saved": True, "rows": await service.delete(device, options["ident"]), "conflicts": []}
        else:
            raise ControlError("Unknown schedule action.")
        result["snapshot"] = await self.snapshot(device, load_weather=False)
        return result

    async def action(self, device_id, action, requested):
        device = self.devices[device_id]
        await send_action(device, action, requested)
        snapshot = describe(device)
        self.remember(snapshot, requested if action in {"on", "apply", "configure"} else None)
        if action != "execute":
            self.record_started_routine(device_id, action, requested)
        if action in {"on", "apply", "configure"} and requested:
            previous = self.pending_changes.get(device_id, {}).get("values", {})
            self.pending_changes[device_id] = {
                "values": {
                    **previous,
                    **{key: str(value) for key, value in requested.items() if key in snapshot["controls"]},
                },
                "deadline": time.monotonic() + 60,
            }
        elif action in {"off", "execute"}:
            self.pending_changes.pop(device_id, None)
        if action == "execute" and self.memory:
            command, category = requested["command"], requested.get("category", "_")
            variant = device.commands[command].categories[category]
            values = {
                key: param.value
                for key, param in variant.settings.items()
                if key not in INTERNAL and param.group == "parameters" and param.typology in {"enum", "range"}
            }
            with suppress(OSError):
                self.memory.remember_function(device_id, command, category, values)
            from .program_memory import mode_key

            self.active_functions[device_id] = {
                "command": command,
                "category": category,
                "mode": mode_key(snapshot),
                "confirmed": False,
                "group": function_group(command, category, parameters=variant.settings),
            }
            self.record_started_routine(device_id, action, requested, self.active_functions[device_id]["group"])
        message = "Command accepted by the cloud service. Wait a few seconds, then refresh to check the AC."
        if self.memory and self.memory.save_error:
            message += " Program settings could not be saved locally."
        return message

    async def watch_updates(self):
        loop = asyncio.get_running_loop()
        while self.api is not None:
            listener = None
            retry = 60
            try:
                async with self.lock:
                    signature = await asyncio.wait_for(self.api.load_aws_token(), timeout=12)
                    token = self.api.auth.id_token
                    devices = list(self.devices.values())

                own: list[CloudUpdates] = []

                def changed(device_id, own=own):
                    current = own[0] if own else None
                    if current is not None and not current.closed and not loop.is_closed():
                        with suppress(RuntimeError):
                            loop.call_soon_threadsafe(self.on_change, device_id)

                listener = CloudUpdates(token, signature, devices, changed)
                own.append(listener)
                listener.start()
                # Rotate tokens periodically. Native MQTT handles reconnects in between.
                await asyncio.sleep(1800)
                retry = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                from .diagnostics import diagnostics

                diagnostics.record("notification_failed", error)
            finally:
                if listener is not None:
                    try:
                        listener.close()
                    except Exception as error:
                        from .diagnostics import diagnostics

                        diagnostics.record("notification_close_failed", error)
            await asyncio.sleep(retry)

    async def close(self):
        if self.watch_task:
            self.watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.watch_task
            self.watch_task = None
        self.devices.clear()
        self.active_functions.clear()
        self.pending_changes.clear()
        self.weather_cache.clear()
        self.api = None
        self.cloud_timers = None
        if self.session:
            await self.session.close()
            self.session = None
