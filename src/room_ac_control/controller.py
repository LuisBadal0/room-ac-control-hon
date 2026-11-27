"""Cloud adapter; account persistence is handled by Windows-encrypted storage."""

import asyncio
import time
from contextlib import suppress
from datetime import UTC, datetime

import aiohttp
from pyhon.appliance import HonAppliance
from pyhon.connection.api import HonAPI

from .ac_commands import execute_function, send_action
from .ac_model import (
    AIR_QUALITY,
    CONTROL_DESCRIPTIONS,
    FANS,
    FIELDS,
    HORIZONTAL,
    INTERNAL,
    MAINTENANCE_TERMS,
    MODES,
    NO_AIR_QUALITY_SERIES,
    VALUE_LABELS,
    VERTICAL,
    ControlError,
    alerts,
    capabilities,
    choices,
    code,
    describe,
    function_group,
    mode_choices,
    mode_label,
    parameter_spec,
    readable,
    reading,
    sensors,
    validate,
)
from .live_updates import CloudUpdates

# The device model and commands live in ac_model and ac_commands; importing them from
# here keeps working.
__all__ = [
    "Controller",
    "AIR_QUALITY",
    "CONTROL_DESCRIPTIONS",
    "ControlError",
    "FANS",
    "FIELDS",
    "HORIZONTAL",
    "INTERNAL",
    "MAINTENANCE_TERMS",
    "MODES",
    "NO_AIR_QUALITY_SERIES",
    "VALUE_LABELS",
    "VERTICAL",
    "alerts",
    "capabilities",
    "choices",
    "code",
    "describe",
    "execute_function",
    "function_group",
    "mode_choices",
    "mode_label",
    "parameter_spec",
    "readable",
    "reading",
    "send_action",
    "sensors",
    "validate",
]


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
        # Energy use per AC: when it was loaded, and its values.
        self.energy_cache: dict[str, tuple[float, dict]] = {}

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

    ENERGY_EVERY = 30 * 60  # hOn's statistics change at most every few minutes.

    async def energy(self, device_id):
        """Energy use from hOn's statistics service, as in its Energy consumption panel.

        Read only when asked (the History sheet), and loaded at most every 30 minutes."""
        if self.api is None:
            raise ControlError("The cloud service did not accept the command. Sign in again.")
        from . import energy

        device = self.devices[device_id]
        now = time.monotonic()
        cached = self.energy_cache.get(device_id)
        if cached and now - cached[0] < self.ENERGY_EVERY:
            return cached[1]
        values = await asyncio.wait_for(energy.load(self.api._hon, device), timeout=15)
        self.energy_cache[device_id] = (now, values)
        return values

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
        from .routine_history import new_hon_runs, running_programs, switched_on

        # hOn's own last self-clean dates count as runs too, once each. pyhOn reads them with
        # the appliance list at sign-in, so they are as fresh as the last connection.
        if hon := new_hon_runs(snapshot.get("self_cleans"), self.memory.routine_runs(snapshot["id"])):
            self.memory.record_routine_runs(snapshot["id"], hon)
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
            routines = switched_on(requested) if action in {"configure", "on"} else []
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
            # Each AC's timers and weather are read together, so more ACs do not add up their waits.
            snapshots = list(await asyncio.gather(*(self.snapshot(device) for device in self.devices.values())))
            if self.memory:
                for snapshot in snapshots:
                    self.memory.record_reading(snapshot)
            return snapshots
        except BaseException:
            await self.close()
            raise

    async def refresh(self, device_id):
        device = self.devices[device_id]
        device.attributes.clear()
        await device.update(force=True)
        snapshot = await self.snapshot(device)
        if self.memory:
            self.memory.record_reading(snapshot)
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
        self.remember(snapshot, requested if action in {"on", "configure"} else None)
        if action != "execute":
            self.record_started_routine(device_id, action, requested)
        if action in {"on", "configure"} and requested:
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
                # Read the session under the lock, but do not hold it while hOn answers:
                # commands would wait behind the token request.
                async with self.lock:
                    api, devices = self.api, list(self.devices.values())
                if api is None:
                    break
                signature = await asyncio.wait_for(api.load_aws_token(), timeout=12)
                if api is not self.api:
                    break  # Signed out or in again meanwhile; that session starts its own watch.
                token = api.auth.id_token

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
        self.energy_cache.clear()
        self.api = None
        self.cloud_timers = None
        if self.session:
            await self.session.close()
            self.session = None
