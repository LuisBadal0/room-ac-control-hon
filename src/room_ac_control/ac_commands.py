"""Sending commands to an AC: power, settings and presets, after a fresh status read."""

from .ac_model import INTERNAL, ControlError, capabilities, code, validate


async def send_action(device, action, requested=None):
    """Refresh first; change only explicitly selected parameters."""
    if action not in {"on", "off", "configure", "execute"}:
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
    # "configure" changes settings with the AC on or off, as hOn does; only "on" powers it on.
    if action == "on":
        changes["onOffStatus"] = "1"
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
