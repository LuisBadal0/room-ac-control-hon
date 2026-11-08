"""Contract checks against the pyhOn version in requirements.lock.

The app relies on pyhOn to turn hOn's cloud payloads into commands and
parameters. These tests feed an anonymized hOn data archive (see
tests/fixtures/pyhon/README.md) through pyhOn's own loader, then through the
app, so a pyhOn upgrade that changes parsing, names or internals fails here
offline instead of in a user's app. Nothing is sent to hOn.
"""

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

from pyhon import const, exceptions
from pyhon.appliance import HonAppliance
from pyhon.connection.api import HonAPI, TestAPI
from pyhon.connection.handler.hon import HonConnectionHandler

from room_ac_control.cloud_timers import command_payload
from room_ac_control.controller import describe, send_action

ARCHIVE = Path(__file__).resolve().parent / "fixtures" / "pyhon"


class RecordingAPI(TestAPI):
    """pyhOn's offline archive API, recording commands instead of logging them."""

    def __init__(self):
        super().__init__(ARCHIVE)
        self.sent = []

    async def send_command(self, appliance, command, parameters, ancillary_parameters, program_name=""):
        self.sent.append((command, dict(parameters), program_name))
        return True


async def load_device():
    api = RecordingAPI()
    infos = await api.load_appliances()
    device = HonAppliance(api, infos[0], zone=0)
    # The same sequence Controller.connect uses.
    await device.load_commands()
    await device.update(force=True)
    return api, device


class PyhonInterfaceTests(unittest.TestCase):
    """Names and internals the app uses directly."""

    def test_api_methods_and_session_argument(self):
        self.assertIn("session", inspect.signature(HonAPI).parameters)
        for name in (
            "create",
            "close",
            "load_appliances",
            "load_commands",
            "load_attributes",
            "load_command_history",
            "load_aws_token",
            "send_command",
        ):
            self.assertTrue(inspect.iscoroutinefunction(getattr(HonAPI, name)), name)
        for name in ("auth", "_hon"):  # Live updates read auth.id_token; cloud timers reuse _hon.
            self.assertIsInstance(inspect.getattr_static(HonAPI, name), property, name)

    def test_connection_handler_used_by_cloud_timers(self):
        for name in ("get", "post", "_intercept", "session", "device"):
            self.assertTrue(hasattr(HonConnectionHandler, name), name)

    def test_live_update_constants_and_sign_in_errors(self):
        for name in ("AWS_ENDPOINT", "AWS_AUTHORIZER"):
            self.assertIsInstance(getattr(const, name), str, name)
            self.assertTrue(getattr(const, name), name)
        for name in ("ApiError", "HonAuthenticationError", "NoAuthenticationException"):
            self.assertTrue(issubclass(getattr(exceptions, name), Exception), name)


class PyhonArchiveTests(unittest.IsolatedAsyncioTestCase):
    """An anonymized hOn AC archive, parsed by pyhOn, read by the app."""

    async def test_dashboard_state_from_archive(self):
        _, device = await load_device()
        state = describe(device)
        self.assertEqual(state["power"], "On")
        self.assertEqual(state["mode"], "Dry")
        self.assertEqual(state["fan"], "Auto")
        self.assertEqual((state["room"], state["target"]), (28.5, 27.0))
        self.assertEqual(state["connection"], "CONNECTED")
        self.assertEqual(state["modes"], {"Auto": "0", "Cool": "1", "Dry": "2", "Heat": "4", "Fan": "6"})
        self.assertEqual(state["fans"], {"High": "1", "Medium": "2", "Low": "3", "Auto": "5"})
        self.assertEqual(state["temperatures"][0], "16")
        self.assertEqual(state["temperatures"][-1], "30")
        self.assertTrue(state["can_on"] and state["can_off"] and state["can_apply"])
        temperature = state["controls"]["tempSel"]
        self.assertEqual((temperature["min"], temperature["max"], temperature["step"]), (16, 30, 1))
        self.assertEqual(
            state["controls"]["windDirectionVertical"]["options"],
            {
                "Position 1": "2",
                "Position 2": "4",
                "Position 3": "5",
                "Position 4": "6",
                "Position 5": "7",
                "Swing": "8",
            },
        )
        programs = {program["value"] for program in state["programs"]}
        self.assertTrue({"iot_simple_start", "iot_cool", "iot_heat", "iot_self_clean"} <= programs)

    async def test_settings_change_is_sent_through_pyhon(self):
        api, device = await load_device()
        await send_action(device, "configure", {"tempSel": "24"})
        self.assertEqual(len(api.sent), 1)
        command, parameters, _ = api.sent[0]
        self.assertEqual(command, "settings")
        self.assertEqual(float(parameters["tempSel"]), 24)
        self.assertEqual(parameters["machMode"], "2")

    async def test_scheduled_start_payload_uses_the_simple_start_program(self):
        _, device = await load_device()
        handler = SimpleNamespace(device=SimpleNamespace(get=lambda mobile=False: {"mobileOs": "windows"}))
        payload = command_payload(device, "on", handler, {"tempSel": "25"})
        self.assertEqual(payload["commandName"], "startProgram")
        self.assertEqual(payload["applianceType"], "AC")
        self.assertEqual(payload["parameters"]["onOffStatus"], "1")
        self.assertEqual(payload["parameters"]["tempSel"], "25.00")
        stop = command_payload(device, "off", handler)
        self.assertEqual((stop["commandName"], stop["parameters"]["onOffStatus"]), ("stopProgram", "0"))


if __name__ == "__main__":
    unittest.main()
