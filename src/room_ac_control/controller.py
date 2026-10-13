"""Cloud adapter; account persistence is handled by Windows-encrypted storage."""
import asyncio
import re
from contextlib import suppress
from datetime import datetime

import aiohttp
from pyhon.appliance import HonAppliance
from pyhon.connection.api import HonAPI
from .live_updates import CloudUpdates

MODES = {"0": "Auto", "1": "Cool", "2": "Dry", "3": "Dry", "4": "Heat", "5": "Fan", "6": "Fan"}
FANS = {"1": "High", "2": "Medium", "3": "Low", "4": "Auto", "5": "Auto"}
FIELDS = {
    "tempSel": "Target temperature", "machMode": "Mode", "windSpeed": "Fan speed",
    "ecoMode": "Eco mode", "silentSleepStatus": "Sleep", "muteStatus": "Quiet mode",
    "rapidMode": "Turbo / rapid mode", "healthMode": "Health / purification",
    "screenDisplayStatus": "Unit display", "echoStatus": "Voice / echo",
    "10degreeHeatingStatus": "10°C heating", "selfCleaningStatus": "Self cleaning",
    "selfCleaning56Status": "56°C self cleaning", "humanSensingStatus": "Eco pilot",
    "windDirectionHorizontal": "Horizontal airflow", "windDirectionVertical": "Vertical airflow",
    "onOffStatus": "Power", "lightStatus": "Light", "delayTime": "Start delay",
}
VERTICAL = {"2": "Position 1", "4": "Position 2", "5": "Position 3", "6": "Position 4", "7": "Position 5", "8": "Swing"}
HORIZONTAL = {"0": "Position 1", "3": "Position 2", "4": "Position 3", "5": "Position 4", "6": "Position 5", "7": "Swing"}
VALUE_LABELS = {"machMode": MODES, "windSpeed": FANS, "windDirectionVertical": VERTICAL,
                "windDirectionHorizontal": HORIZONTAL,
                "humanSensingStatus": {"0": "Off", "1": "Avoid direct airflow", "2": "Follow person", "3": "Other"}}
INTERNAL = {"prStr", "prCode", "program", "category", "favourite", "zoneMap"}
MAINTENANCE_TERMS = ("clean", "steriliz", "sterilis", "descal", "maintenance", "service", "diagnos", "calibrat", "reset", "filter", "test")


def function_group(command_name, category="", label="", parameters=None):
    """Classify each preset independently; ordinary Dry/Health modes are everyday use."""
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
    spec = {"key": key, "label": readable(key), "kind": parameter.typology,
            "value": parameter.value if current is None else current,
            "reported": current is not None}
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
        spec.update(options=choices(parameter, labels) if labels else {readable(v) if not v.isnumeric() else v: v for v in values})
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
            forms.append({"category": category, "label": label, "parameters": params,
                          "group": function_group(name, category, label, variant.settings)})
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
        result.append({"label": label, "value": patch, "description": "Standard mode",
                       "glyph": {"Auto":"leaf","Cool":"snow","Dry":"drop","Heat":"sun","Fan":"fan"}.get(label,"wind")})
    if "1" in sleep_values:
        for label, value in snapshot.get("modes", {}).items():
            if label in {"Cool", "Heat"}:
                result.append({"label": label + " Night", "value": {"machMode": value, "silentSleepStatus": "1"},
                               "description": ("Cooling" if label == "Cool" else "Heating") + " with Sleep enabled"})
    return result


def mode_label(snapshot, pending=None):
    pending = pending or {}
    mode = snapshot.get("controls", {}).get("machMode", {})
    current = mode.get("value") if mode.get("reported") else None
    selected = pending.get("machMode",current)
    label = next((label for label, value in snapshot.get("modes", {}).items()
                  if value == code(selected)), snapshot.get("mode", "Unknown"))
    sleep = snapshot.get("controls", {}).get("silentSleepStatus", {})
    sleep_value = pending.get("silentSleepStatus", sleep.get("value") if sleep.get("reported") else None)
    return label + " Night" if label in {"Cool", "Heat"} and code(sleep_value) == "1" else label


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
        "controls": controls, "programs": programs, "commands": commands,
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
        if parameter is None or key in INTERNAL or key == "onOffStatus" or parameter.typology not in {"enum", "range"} or parameter.group != "parameters":
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
        self.cloud_timers = None

    def remember(self, snapshot, explicit=None):
        if self.memory:
            try:
                self.memory.remember_mode(snapshot,explicit)
            except OSError as error:
                from .diagnostics import diagnostics
                diagnostics.record("state_save_failed", error)

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
                for zone in (range(1, zones + 1) if zones > 1 else [0]):
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
            snapshots = []
            for device in self.devices.values():
                snapshot = describe(device)
                snapshot["timers"] = await self.timer_status(device)
                snapshots.append(snapshot)
            return snapshots
        except BaseException:
            await self.close()
            raise

    async def refresh(self, device_id):
        device = self.devices[device_id]
        device.attributes.clear()
        await device.update(force=True)
        snapshot = describe(device)
        snapshot["timers"] = await self.timer_status(device)
        self.remember(snapshot)
        active = self.active_functions.get(device_id)
        if active and snapshot["power"] == "On" and self.memory and active.get("group")!="maintenance":
            from .program_memory import mode_key
            program=str(snapshot.get("program") or "").lower().split(".")[-1]
            wrong_program=program.startswith("iot_") and program!=active["category"].lower()
            if mode_key(snapshot) == active["mode"] and not wrong_program:
                active["confirmed"]=True
                command = device.commands.get(active["command"])
                variant = command.categories.get(active["category"]) if command else None
                if variant:
                    values = {key:device.get(key) for key,param in variant.settings.items()
                              if key not in INTERNAL and param.group == "parameters" and param.typology in {"range","enum"} and device.get(key) is not None}
                    with suppress(OSError):
                        self.memory.remember_function(device_id,active["command"],active["category"],values)
            elif active.get("confirmed"):
                self.active_functions.pop(device_id,None)
        return snapshot

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
        snapshot = describe(device)
        snapshot["timers"] = {"available": True, "values": values}
        return snapshot

    async def action(self, device_id, action, requested):
        device = self.devices[device_id]
        await send_action(device, action, requested)
        snapshot = describe(device)
        self.remember(snapshot,requested if action in {"on","apply","configure"} else None)
        if action == "execute" and self.memory:
            command,category=requested["command"],requested.get("category","_")
            variant=device.commands[command].categories[category]
            values={key:param.value for key,param in variant.settings.items()
                    if key not in INTERNAL and param.group=="parameters" and param.typology in {"enum","range"}}
            with suppress(OSError):
                self.memory.remember_function(device_id,command,category,values)
            from .program_memory import mode_key
            self.active_functions[device_id]={"command":command,"category":category,"mode":mode_key(snapshot),"confirmed":False,
                                             "group":function_group(command,category,parameters=variant.settings)}
        message="Command accepted by the cloud service. Wait a few seconds, then refresh to check the AC."
        if self.memory and self.memory.save_error:
            message+=" Program settings could not be saved locally."
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
                def changed(device_id):
                    if listener is not None and not listener.closed and not loop.is_closed():
                        with suppress(RuntimeError):
                            loop.call_soon_threadsafe(self.on_change, device_id)
                listener = CloudUpdates(token, signature, devices, changed)
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
                    try:listener.close()
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
        self.api = None
        self.cloud_timers = None
        if self.session:
            await self.session.close()
            self.session = None
