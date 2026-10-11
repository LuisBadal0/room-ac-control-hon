"""Actual Windows DPAPI and per-program state checks using disposable test data."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

from room_ac_control.secure_state import SecureState, protect
from room_ac_control.program_memory import ProgramMemory
from room_ac_control.controller import Controller, describe
from pyhon.commands import HonCommand
from tests.test_controller import make_device


@unittest.skipUnless(os.name=="nt","Windows DPAPI required")
class EncryptionTests(unittest.TestCase):
    def test_encrypted_restart_and_forget_preserves_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"state.dpapi"
            store=SecureState(path)
            store.save_credentials("sample@example.test","fake-password-for-encryption-test")
            store.save_profile("account","unit","mode:1:night:0",{"tempSel":"25"})
            blob=path.read_bytes()
            self.assertTrue(b"fake-password-for-encryption-test" not in blob)
            self.assertTrue(b"sample@example.test" not in blob)
            reopened=SecureState(path)
            self.assertEqual(reopened.credentials(),store.credentials())
            self.assertEqual(reopened.profile("account","unit","mode:1:night:0"),{"tempSel":"25"})
            reopened.forget_credentials()
            self.assertIsNone(SecureState(path).credentials())
            self.assertEqual(SecureState(path).profile("account","unit","mode:1:night:0"),{"tempSel":"25"})
            self.assertEqual([p.name for p in Path(directory).iterdir()],["state.dpapi"])

    def test_corrupt_ciphertext_never_falls_back_to_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"state.dpapi"
            store=SecureState(path)
            store.save_credentials("sample@example.test","dummy-test-value")
            blob=bytearray(path.read_bytes())
            blob[len(blob)//2]^=1
            path.write_bytes(blob)
            reopened=SecureState(path)
            self.assertTrue(reopened.load_error)
            self.assertIsNone(reopened.credentials())

    def test_failed_write_retries_even_when_values_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"state.dpapi"
            store=SecureState(path)
            original=store.write
            def denied():raise OSError("test access failure")
            store.write=denied
            with self.assertRaises(OSError):store.save_profile("account","unit","cool",{"tempSel":"24"})
            store.write=original
            store.save_profile("account","unit","cool",{"tempSel":"24"})
            self.assertEqual(SecureState(path).profile("account","unit","cool"),{"tempSel":"24"})


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=SecureState(persistent=False)
        self.memory=ProgramMemory(self.store)
        self.memory.use_account("sample@example.test")
        self.device,self.api=make_device()
        await self.device.update(force=True)
        self.snapshot=describe(self.device)

    def configuration(self,mode,temp,fan="3",night="0"):
        snapshot=copy.deepcopy(self.snapshot)
        snapshot["mode"]=mode
        for key,value in {"machMode":{"Cool":"1","Heat":"4"}[mode],"tempSel":temp,"windSpeed":fan,"silentSleepStatus":night}.items():
            snapshot["controls"][key]["value"]=value
            snapshot["controls"][key]["reported"]=True
        return snapshot

    async def test_modes_nights_accounts_and_units_remain_independent(self):
        self.memory.remember_mode(self.configuration("Cool",22))
        self.memory.remember_mode(self.configuration("Heat",28,"1"))
        self.memory.remember_mode(self.configuration("Cool",24,"2","1"))
        self.assertEqual(self.memory.mode_values(self.snapshot,{"machMode":"1","silentSleepStatus":"0"})["tempSel"],"22")
        self.assertEqual(self.memory.mode_values(self.snapshot,{"machMode":"4","silentSleepStatus":"0"})["tempSel"],"28")
        night=self.memory.mode_values(self.snapshot,{"machMode":"1","silentSleepStatus":"1"})
        self.assertEqual((night["tempSel"],night["windSpeed"]),("24","2"))
        other=copy.deepcopy(self.snapshot);other["id"]="other-unit"
        self.assertNotIn("tempSel",self.memory.mode_values(other,{"machMode":"1"}))
        self.memory.use_account("other@example.test")
        self.assertNotIn("tempSel",self.memory.mode_values(self.snapshot,{"machMode":"1"}))

    async def test_latest_config_updates_and_unsupported_values_are_dropped(self):
        self.memory.remember_mode(self.configuration("Cool",22))
        self.memory.remember_mode(self.configuration("Cool",25,"1"))
        restored=self.memory.mode_values(self.snapshot,{"machMode":"1","silentSleepStatus":"0"})
        self.assertEqual((restored["tempSel"],restored["windSpeed"]),("25","1"))
        changed=copy.deepcopy(self.snapshot)
        changed["controls"]["tempSel"]["max"]=20
        self.assertNotIn("tempSel",self.memory.mode_values(changed,{"machMode":"1"}))
        self.assertNotIn("onOffStatus",restored)
        self.assertNotIn("selfCleaningStatus",restored)

    async def test_controller_saves_accepted_config_and_not_rejected_commands(self):
        controller=Controller(memory=self.memory)
        controller.devices[self.device.unique_id]=self.device
        await controller.action(self.device.unique_id,"configure",{"tempSel":"26","windSpeed":"1"})
        restored=self.memory.mode_values(self.snapshot,{"machMode":"1","silentSleepStatus":"0"})
        self.assertEqual((restored["tempSel"],restored["windSpeed"]),("26","1"))
        self.api.accepted=False
        with self.assertRaises(Exception):
            await controller.action(self.device.unique_id,"configure",{"tempSel":"29"})
        self.assertEqual(self.memory.mode_values(self.snapshot,{"machMode":"1","silentSleepStatus":"0"})["tempSel"],"26")

    async def test_native_preset_parameters_are_saved_per_category(self):
        spec=self.snapshot["controls"]["tempSel"]
        cool={"category":"iot_cool","parameters":[spec]}
        heat={"category":"iot_heat","parameters":[spec]}
        self.memory.remember_function(self.snapshot["id"],"startProgram","iot_cool",{"tempSel":"23"})
        self.memory.remember_function(self.snapshot["id"],"startProgram","iot_heat",{"tempSel":"28"})
        self.assertEqual(self.memory.function_values(self.snapshot["id"],"startProgram",cool),{"tempSel":"23"})
        self.assertEqual(self.memory.function_values(self.snapshot["id"],"startProgram",heat),{"tempSel":"28"})

    async def test_persistence_failure_does_not_report_accepted_command_as_failed(self):
        def unavailable(*args):raise OSError("test disk error")
        self.store.save_profile=unavailable
        controller=Controller(memory=self.memory)
        controller.devices[self.device.unique_id]=self.device
        result=await controller.action(self.device.unique_id,"configure",{"tempSel":"26"})
        self.assertIn("Command accepted",result)
        self.assertIn("could not be saved",result)

    async def test_native_preset_switch_synchronizes_the_selected_mode(self):
        categories={}
        for name,mode in (("iot_cool","1"),("iot_heat","4")):
            categories[name]=HonCommand("startProgram",{"parameters":{
                "onOffStatus":{"typology":"fixed","fixedValue":"1"},
                "machMode":{"typology":"fixed","fixedValue":mode},
                "tempSel":{"typology":"range","minimumValue":"16","maximumValue":"30","incrementValue":"1","defaultValue":"22"},
            }},self.device,categories=categories,category_name="PROGRAM."+name.upper())
        self.device.commands["startProgram"]=categories["iot_cool"]
        controller=Controller(memory=self.memory)
        controller.devices[self.device.unique_id]=self.device
        await controller.action(self.device.unique_id,"execute",{"command":"startProgram","category":"iot_heat","parameters":{"tempSel":"28"}})
        self.assertEqual(describe(self.device)["mode"],"Heat")
        self.assertEqual(self.memory.mode_values(self.snapshot,{"machMode":"4","silentSleepStatus":"0"})["tempSel"],"28")
        form={"category":"iot_heat","parameters":[self.snapshot["controls"]["tempSel"]]}
        self.assertEqual(self.memory.function_values(self.snapshot["id"],"startProgram",form),{"tempSel":"28"})
