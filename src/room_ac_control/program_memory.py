"""Restore only supported parameters, keeping each mode/preset independent."""
import hashlib
from .diagnostics import diagnostics

from .controller import code, function_group

EXCLUDED = {"onOffStatus", "selfCleaningStatus", "selfCleaning56Status"}


def normalized(value):
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def mode_key(snapshot, changes=None):
    changes = changes or {}
    modes = snapshot.get("modes", {})
    spec = snapshot.get("controls", {}).get("machMode", {})
    current = spec.get("value") if spec.get("reported") else next((v for label, v in modes.items() if label == snapshot.get("mode")), None)
    mode = code(changes.get("machMode", current))
    sleep = snapshot.get("controls", {}).get("silentSleepStatus", {})
    night = code(changes.get("silentSleepStatus", sleep.get("value") if sleep.get("reported") else 0))
    return f"mode:{mode}:night:{int(mode in {'1','4'} and night == '1')}"


def supported(spec, value):
    if spec["kind"] == "enum":
        return normalized(value) in set(spec["options"].values())
    try:
        value = float(value)
        ticks = (value - spec["min"]) / spec["step"]
        return spec["min"] <= value <= spec["max"] and abs(ticks-round(ticks)) < 1e-6
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return False


class ProgramMemory:
    def __init__(self, state):
        self.state = state
        self.account = ""
        self.save_error = False

    def save(self, device, program, values):
        try:
            self.state.save_profile(self.account,device,program,values)
            self.save_error=False
        except OSError as error:
            diagnostics.record("state_save_failed", error)
            self.save_error=True

    def use_account(self, email):
        self.account = hashlib.sha256(email.strip().casefold().encode()).hexdigest()

    def remember_mode(self, snapshot, explicit=None):
        if snapshot.get("power") != "On" and not explicit:
            return
        values = {key: normalized(spec["value"]) for key, spec in snapshot.get("controls", {}).items()
                  if key not in EXCLUDED and spec.get("reported") and function_group(key,label=spec["label"])!="maintenance"}
        values.update({key: normalized(value) for key, value in (explicit or {}).items()
                       if key not in EXCLUDED and function_group(key)!="maintenance"})
        self.save(snapshot["id"],mode_key(snapshot,explicit),values)

    def mode_values(self, snapshot, patch):
        values = self.state.profile(self.account, snapshot["id"], mode_key(snapshot, patch))
        controls = snapshot.get("controls", {})
        restored = {key: value for key, value in values.items() if key not in EXCLUDED and key in controls and function_group(key,label=controls[key]["label"])!="maintenance" and supported(controls[key], value)}
        restored.update(patch)  # The selected mode/night identity always wins.
        return restored

    def remember_function(self, device_id, command, category, values):
        self.save(device_id,f"function:{command}:{category}",
                  {key: normalized(value) for key,value in values.items() if key!="onOffStatus"})

    def function_values(self, device_id, command, form):
        values = self.state.profile(self.account, device_id, f"function:{command}:{form['category']}")
        specs = {spec["key"]: spec for spec in form["parameters"]}
        return {key: value for key,value in values.items() if key in specs and supported(specs[key], value)}
