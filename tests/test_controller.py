"""Offline checks using real pyhOn command and parameter objects."""
import unittest

from pyhon.appliance import HonAppliance
from pyhon.attributes import HonAttribute
from pyhon.commands import HonCommand

from room_ac_control.controller import ControlError, describe, send_action, function_group, mode_choices, mode_label


class FakeAPI:
    def __init__(self, power="1", accepted=True):
        self.power = power
        self.accepted = accepted
        self.fan = "3"
        self.sent = []

    async def load_attributes(self, device):
        return {
            "shadow": {"parameters": {key: {"parNewVal": value} for key, value in {
                "onOffStatus": self.power, "tempSel": "23", "tempIndoor": "24.5",
                "machMode": "1", "windSpeed": self.fan, "ecoMode": "1",
                "silentSleepStatus": "0", "windDirectionVertical": "8", "windDirectionHorizontal": "0",
                "rapidMode": "0", "healthMode": "0", "screenDisplayStatus": "1",
                "muteStatus": "0", "echoStatus": "0",
            }.items()}},
            "lastConnEvent": {"category": "CONNECTED"},
        }

    async def send_command(self, device, command, params, ancillary, program):
        self.sent.append((command, dict(params)))
        return self.accepted


def make_device(power="1", accepted=True):
    api = FakeAPI(power, accepted)
    device = HonAppliance(api, {"applianceTypeName": "AC", "modelName": "DEMO-AC", "nickName": "Office", "macAddress": "test-device"})
    enum = lambda values: {"typology": "enum", "enumValues": values, "defaultValue": values[0]}
    device.commands["settings"] = HonCommand("settings", {"parameters": {
        "onOffStatus": {**enum(["0", "1"]), "mandatory": 1},
        "machMode": enum(["0", "1", "3", "4", "6"]),
        "windSpeed": enum(["1", "2", "3", "5"]),
        "tempSel": {"typology": "range", "minimumValue": "16", "maximumValue": "30", "incrementValue": "1", "defaultValue": "22"},
        "ecoMode": enum(["0", "1"]),
        "silentSleepStatus": enum(["0", "1"]),
        "windDirectionVertical": enum(["2", "4", "5", "6", "7", "8"]),
        "windDirectionHorizontal": enum(["0", "3", "4", "5", "6", "7"]),
        "rapidMode": enum(["0", "1"]),
        "healthMode": enum(["0", "1"]),
        "screenDisplayStatus": enum(["0", "1"]),
        "muteStatus": enum(["0", "1"]),
        "echoStatus": enum(["0", "1"]),
    }}, device)
    device.commands["stopProgram"] = HonCommand("stopProgram", {"parameters": {
        "onOffStatus": {"typology": "fixed", "fixedValue": "0"},
    }}, device)
    return device, api


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_fan_waits_for_cloud_confirmation_without_overwriting_saved_choice(self):
        from room_ac_control.controller import Controller
        from room_ac_control.program_memory import ProgramMemory
        from room_ac_control.secure_state import SecureState
        device,api=make_device()
        api.fan="5"
        memory=ProgramMemory(SecureState(persistent=False))
        memory.use_account("fixture@example.test")
        controller=Controller(memory=memory)
        controller.devices[device.unique_id]=device
        await controller.action(device.unique_id,"configure",{"windSpeed":"3"})
        snapshot=await controller.refresh(device.unique_id)
        self.assertEqual(snapshot["fan"],"Auto")  # Reported state remains honest.
        self.assertEqual(snapshot["pending_changes"],{"windSpeed":"3"})
        self.assertEqual(memory.mode_values(snapshot,{})["windSpeed"],"3")
        api.fan="3"
        snapshot=await controller.refresh(device.unique_id)
        self.assertEqual(snapshot["fan"],"Low")
        self.assertNotIn("pending_changes",snapshot)
        self.assertNotIn(device.unique_id,controller.pending_changes)
        self.assertEqual(len(api.sent),1)

    async def test_unconfirmed_fan_expires_to_reported_state_without_resending(self):
        from room_ac_control.controller import Controller
        device,api=make_device()
        api.fan="5"
        controller=Controller()
        controller.devices[device.unique_id]=device
        await controller.action(device.unique_id,"configure",{"windSpeed":"3"})
        controller.pending_changes[device.unique_id]["deadline"]=0
        snapshot=await controller.refresh(device.unique_id)
        self.assertTrue(snapshot["confirmation_expired"])
        self.assertEqual(snapshot["fan"],"Auto")
        self.assertNotIn("pending_changes",snapshot)
        self.assertEqual(len(api.sent),1)

    async def test_rejected_command_does_not_create_pending_selection(self):
        from room_ac_control.controller import Controller
        device,api=make_device(accepted=False)
        controller=Controller()
        controller.devices[device.unique_id]=device
        with self.assertRaises(Exception):
            await controller.action(device.unique_id,"configure",{"windSpeed":"3"})
        self.assertFalse(controller.pending_changes)

    async def test_turn_on_with_fixed_power_parameter_after_applying_each_mode(self):
        for mode in ("0","1","2","4","6"):
            for night in ("0","1") if mode in {"1","4"} else ("0",):
                device,api=make_device("0")
                from pyhon.parameter.fixed import HonParameterFixed
                from pyhon.parameter.range import HonParameterRange
                device.commands["settings"].settings["onOffStatus"]=HonParameterFixed(
                    "onOffStatus",{"typology":"fixed","fixedValue":"0","mandatory":1},"parameters")
                device.commands["settings"].settings["machMode"].values=["0","1","2","4","6"]
                device.commands["settings"].settings["silentSleepStatus"]=HonParameterRange("silentSleepStatus",
                    {"typology":"range","minimumValue":"0","maximumValue":"1","incrementValue":"1"},"parameters")
                patch={"machMode":mode,"silentSleepStatus":night}
                await send_action(device,"configure",patch)
                self.assertEqual(api.sent[-1][1]["onOffStatus"],"0")
                await send_action(device,"on",patch)
                self.assertEqual(api.sent[-1][1],{"onOffStatus":"1","machMode":mode,"silentSleepStatus":float(night)})
                with self.assertRaises(ControlError):
                    await send_action(device,"configure",{"onOffStatus":"1"})

    async def test_night_modes_use_real_hvac_and_sleep_parameters(self):
        device,api=make_device("0")
        await device.update(force=True)
        snapshot=describe(device)
        choices={option["label"]:option["value"] for option in mode_choices(snapshot)}
        self.assertEqual(choices["Cool Night"],{"machMode":"1","silentSleepStatus":"1"})
        self.assertEqual(choices["Heat Night"],{"machMode":"4","silentSleepStatus":"1"})
        await send_action(device,"on",choices["Heat Night"])
        self.assertEqual(api.sent,[("settings",{"onOffStatus":"1","machMode":"4","silentSleepStatus":"1"})])
        self.assertEqual(mode_label(snapshot,choices["Cool Night"]),"Cool Night")
        self.assertEqual(mode_label(snapshot,choices["Cool"]),"Cool")
        snapshot["controls"].pop("silentSleepStatus")
        self.assertFalse(any(option["label"].endswith(" Night") for option in mode_choices(snapshot)))

    async def test_maintenance_is_classified_per_preset_and_all_variants_are_kept(self):
        self.assertEqual(function_group("muteStatus", label="Silent mode"), "everyday")
        self.assertEqual(function_group("echoStatus", label="Buzzer (Echo)"), "everyday")
        self.assertEqual(function_group("selfCleaningStatus"), "maintenance")
        self.assertEqual(function_group("startProgram", "iot_dry"), "everyday")
        self.assertEqual(function_group("startProgram", "iot_health"), "everyday")
        self.assertEqual(function_group("startProgram", "iot_self_clean"), "maintenance")
        self.assertEqual(function_group("startProgram", "iot_sterilization_56"), "maintenance")
        self.assertEqual(function_group("filterReset"), "maintenance")
        device, api = make_device()
        categories = {}
        for name in ("iot_cool", "iot_self_clean"):
            categories[name] = HonCommand("startProgram", {"parameters": {"onOffStatus": {"typology": "fixed", "fixedValue": "1"}}}, device, categories=categories, category_name="PROGRAM." + name.upper())
        device.commands["startProgram"] = categories["iot_cool"]
        forms = describe(device)["commands"]["startProgram"]["forms"]
        self.assertEqual({form["category"]: form["group"] for form in forms}, {"iot_cool": "everyday", "iot_self_clean": "maintenance"})
        self.assertEqual(api.sent, [])

    async def test_extra_features_are_discovered_and_only_changed_fields_are_sent(self):
        device, api = make_device()
        await device.update(force=True)
        self.assertIn("rapidMode",describe(device)["controls"])
        self.assertIn("healthMode",describe(device)["controls"])
        await send_action(device,"configure",{"ecoMode":"0","silentSleepStatus":"1","windDirectionVertical":"8"})
        self.assertEqual(api.sent,[("settings",{"onOffStatus":"1","ecoMode":"0","silentSleepStatus":"1","windDirectionVertical":"8"})])

    async def test_feature_change_while_off_keeps_power_off(self):
        device,api=make_device("0")
        await send_action(device,"configure",{"ecoMode":"0"})
        self.assertEqual(api.sent,[("settings",{"onOffStatus":"0","ecoMode":"0"})])

    async def test_preset_categories_and_dedicated_function(self):
        device,api=make_device()
        categories={}
        for name,mode in (("iot_cool","1"),("iot_heat","4")):
            categories[name]=HonCommand("startProgram",{"parameters":{"onOffStatus":{"typology":"fixed","fixedValue":"1"},"machMode":{"typology":"fixed","fixedValue":mode}}},device,categories=categories,category_name="PROGRAM."+name.upper())
        device.commands["startProgram"]=categories["iot_cool"]
        self.assertEqual(len(describe(device)["commands"]["startProgram"]["forms"]),2)
        await send_action(device,"execute",{"command":"startProgram","category":"iot_heat","parameters":{}})
        self.assertEqual(api.sent,[("startProgram",{"onOffStatus":"1","machMode":"4"})])

    async def test_unknown_function_or_power_injection_is_rejected(self):
        device,api=make_device()
        with self.assertRaises(ControlError):
            await send_action(device,"execute",{"command":"resetWifi"})
        with self.assertRaises(ControlError):
            await send_action(device,"configure",{"onOffStatus":"1"})
        self.assertEqual(api.sent,[])

    async def test_temperature_change_preserves_power_and_omits_unrequested_features(self):
        device, api = make_device()
        await send_action(device, "apply", {"tempSel": "25"})
        self.assertEqual(api.sent, [("settings", {"onOffStatus": "1", "tempSel": 25.0})])

    async def test_settings_do_not_start_an_ac_that_is_off(self):
        device, api = make_device("0")
        with self.assertRaisesRegex(ControlError, "AC is off"):
            await send_action(device, "apply", {"tempSel": "25"})
        self.assertEqual(api.sent, [])

    async def test_turn_on_sends_selected_temperature_mode_fan(self):
        device, api = make_device("0")
        await send_action(device, "on", {"tempSel": "24", "machMode": "4", "windSpeed": "5"})
        self.assertEqual(api.sent, [("settings", {"onOffStatus": "1", "machMode": "4", "windSpeed": "5", "tempSel": 24.0})])

    async def test_turn_off_uses_stop_command(self):
        device, api = make_device()
        await send_action(device, "off")
        self.assertEqual(api.sent, [("stopProgram", {"onOffStatus": "0"})])

    async def test_invalid_temperature_and_extra_parameters_do_not_send(self):
        for request in ({"tempSel": "31"}, {"tempSel": "23.5"}, {"onOffStatus": "1"}, {"windSpeed": "9"}):
            device, api = make_device()
            with self.assertRaises(ControlError):
                await send_action(device, "apply", request)
            self.assertEqual(api.sent, [])

    async def test_rejection_is_not_reported_as_success(self):
        device, api = make_device(accepted=False)
        with self.assertRaises(Exception):
            await send_action(device, "on", {"tempSel": "24"})
        self.assertEqual(len(api.sent), 1)

    async def test_refresh_ignores_optimistic_power_from_previous_command(self):
        device, api = make_device("0")
        device.attributes["parameters"] = {"onOffStatus": HonAttribute("1")}
        device.attributes["parameters"]["onOffStatus"].update("1", shield=True)
        with self.assertRaisesRegex(ControlError, "AC is off"):
            await send_action(device, "apply", {"tempSel": "25"})
        self.assertEqual(api.sent, [])

    async def test_live_capabilities_and_float_sensor_values(self):
        device, api = make_device()
        await device.update(force=True)
        snapshot = describe(device)
        self.assertEqual(snapshot["power"], "On")
        self.assertEqual(snapshot["room"], 24.5)
        self.assertEqual(snapshot["modes"]["Heat"], "4")
        self.assertEqual(snapshot["fans"]["Auto"], "5")
        self.assertEqual([float(v) for v in snapshot["temperatures"]], list(range(16, 31)))


if __name__ == "__main__":
    unittest.main()
