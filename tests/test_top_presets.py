"""Choosing up to four top presets in Everyday use, with offline fixtures only."""
import os
from pathlib import Path
import tempfile
import unittest

from room_ac_control.functions_view import PRESETS_UP_FRONT, everyday_layout, preset_key, toggle_top_preset
from room_ac_control.program_memory import ProgramMemory
from room_ac_control.secure_state import TOP_PRESET_LIMIT, SecureState


def preset(label):
    return {"kind": "function", "label": label}


ITEMS = [preset(label) for label in ("Cool", "Dry", "Turbo", "Heat Night", "Heat", "10°C Heat", "Cool Night", "Turbo")]
MODES = {"auto", "cool", "dry", "heat", "fan"}


def keys(items):
    return [preset_key(item) for item in items]


class LayoutTests(unittest.TestCase):
    def test_the_limit_is_four(self):
        self.assertEqual(TOP_PRESET_LIMIT, 4)

    def test_defaults_show_cool_and_heat_first_and_the_rest_in_more(self):
        choices, top, more = everyday_layout(ITEMS, MODES)
        self.assertEqual(keys(top), list(PRESETS_UP_FRONT))
        self.assertEqual(keys(more), ["turbo", "10°cheat"])
        # Dry only repeats the mode bar; Turbo is listed once.
        self.assertEqual(keys(choices), [*PRESETS_UP_FRONT, "turbo", "10°cheat"])

    def test_chosen_presets_go_first_in_order_and_the_rest_go_in_more(self):
        choices, top, more = everyday_layout(ITEMS, MODES, ["turbo", "heat"])
        self.assertEqual(keys(top), ["turbo", "heat"])
        self.assertEqual(keys(more), ["cool", "coolnight", "heatnight", "10°cheat"])
        self.assertEqual(len(top)+len(more), len(choices))

    def test_no_top_presets_puts_everything_in_more(self):
        choices, top, more = everyday_layout(ITEMS, MODES, [])
        self.assertEqual(top, [])
        self.assertEqual(more, choices)

    def test_unknown_duplicate_and_excess_choices_are_dropped(self):
        chosen = ["gone", "turbo", "turbo", "heat", "cool", "coolnight", "heatnight"]
        choices, top, more = everyday_layout(ITEMS, MODES, chosen)
        self.assertEqual(keys(top), ["turbo", "heat", "cool", "coolnight"])
        self.assertEqual(keys(more), ["heatnight", "10°cheat"])

    def test_a_fifth_preset_is_refused_until_one_is_removed(self):
        chosen, refused = [], False
        for key in ("cool", "heat", "turbo", "coolnight"):
            chosen, refused = toggle_top_preset(chosen, key)
            self.assertFalse(refused)
        chosen, refused = toggle_top_preset(chosen, "heatnight")
        self.assertTrue(refused)
        self.assertEqual(chosen, ["cool", "heat", "turbo", "coolnight"])
        chosen, refused = toggle_top_preset(chosen, "heat")
        self.assertFalse(refused)
        chosen, refused = toggle_top_preset(chosen, "heatnight")
        self.assertEqual((chosen, refused), (["cool", "turbo", "coolnight", "heatnight"], False))


class StorageTests(unittest.TestCase):
    def test_choices_are_kept_per_account_and_unit(self):
        state = SecureState(persistent=False)
        self.assertIsNone(state.top_presets("account", "unit"))
        state.save_top_presets("account", "unit", ["turbo", "heat"])
        state.save_top_presets("account", "other-unit", [])
        self.assertEqual(state.top_presets("account", "unit"), ["turbo", "heat"])
        self.assertEqual(state.top_presets("account", "other-unit"), [])
        self.assertIsNone(state.top_presets("someone-else", "unit"))

    def test_more_than_four_or_repeated_presets_are_rejected(self):
        state = SecureState(persistent=False)
        with self.assertRaises(ValueError):
            state.save_top_presets("account", "unit", ["a", "b", "c", "d", "e"])
        with self.assertRaises(ValueError):
            state.save_top_presets("account", "unit", ["a", "a"])
        self.assertIsNone(state.top_presets("account", "unit"))

    def test_malformed_saved_choices_fall_back_to_the_defaults(self):
        state = SecureState(persistent=False)
        for value in ("cool", ["cool", 3], {"cool": 1}):
            state.data["top_presets"] = {"account": {"unit": value}}
            self.assertIsNone(state.top_presets("account", "unit"))
        state.data["top_presets"] = {"account": {"unit": ["a", "b", "a", "c", "d", "e"]}}
        self.assertEqual(state.top_presets("account", "unit"), ["a", "b", "c", "d"])

    def test_a_failed_write_keeps_the_choice_for_this_session_and_reports_it(self):
        state = SecureState(persistent=False)
        memory = ProgramMemory(state)
        memory.use_account("sample@example.test")

        def denied():
            raise OSError("test access failure")
        state.write = denied
        memory.save_top_presets("unit", ["heat"])
        self.assertTrue(memory.save_error)
        self.assertEqual(memory.top_presets("unit"), ["heat"])
        del state.write
        memory.save_top_presets("unit", ["cool"])
        self.assertFalse(memory.save_error)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI required")
    def test_choices_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"state.dpapi"
            SecureState(path).save_top_presets("account", "unit", ["heatnight", "turbo"])
            self.assertEqual(SecureState(path).top_presets("account", "unit"), ["heatnight", "turbo"])


if __name__ == "__main__":
    unittest.main()
