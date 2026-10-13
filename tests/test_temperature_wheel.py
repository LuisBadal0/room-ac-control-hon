"""Offline range and drag checks for the bounded temperature wheel."""
from types import SimpleNamespace
import tkinter as tk
import unittest

from room_ac_control.temperature_wheel import TemperatureWheel


class TemperatureWheelTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.spec = {"min": 16, "max": 30, "step": .5}
        self.wheel = TemperatureWheel(self.root, self.spec, 23)

    def tearDown(self):
        self.root.destroy()

    def pointer(self, y):
        return SimpleNamespace(y=y, y_root=200+y)

    def test_drag_and_fast_release_snap_to_decimal_steps_and_stop_at_limits(self):
        self.wheel.press(self.pointer(54))
        self.wheel.drag(self.pointer(20))
        self.assertEqual(self.wheel.get(), "23.5")
        self.assertEqual(self.wheel.drag_offset, -4)
        self.wheel.release(self.pointer(20))
        self.assertEqual(self.wheel.get(), "23.5")
        self.wheel.press(self.pointer(54))
        self.wheel.release(self.pointer(-5000))
        self.assertEqual(self.wheel.get(), "30")
        self.wheel.press(self.pointer(54))
        self.wheel.release(self.pointer(5000))
        self.assertEqual(self.wheel.get(), "16")
        self.wheel.step(-1)
        self.assertEqual(self.wheel.get(), "16")

    def test_wheel_accumulates_small_deltas_without_float_drift(self):
        wheel = TemperatureWheel(self.root, {"min": 16, "max": 16.3, "step": .1}, "16")
        for _ in range(4): wheel.wheel(SimpleNamespace(delta=30))
        self.assertEqual(wheel.get(), "16.1")
        wheel.step(2)
        self.assertEqual(wheel.get(), "16.3")
        wheel.step(100)
        self.assertEqual(wheel.get(), "16.3")
        self.assertEqual(wheel.wheel(SimpleNamespace(delta=-120)), "break")
        self.assertEqual(wheel.get(), "16.2")

    def test_unknown_or_off_grid_values_remain_unset_until_an_explicit_choice(self):
        for value in (None, "", "NaN", "Infinity", "24.25", "31"):
            wheel = TemperatureWheel(self.root, self.spec, value)
            self.assertIsNone(wheel.get())
            wheel.press(self.pointer(54))
            wheel.release(self.pointer(54))
            self.assertIsNone(wheel.get())
            wheel.step(-1)
            self.assertEqual(wheel.get(), "16")
            wheel.destroy()
        self.wheel.press(self.pointer(54))
        self.wheel.enabled = False
        self.wheel.draw()
        self.wheel.release(self.pointer(-500))
        self.assertEqual(self.wheel.get(), "23")

    def test_invalid_ranges_are_rejected_and_unaligned_maximum_is_not_offered(self):
        for spec in ({"min":16,"max":30,"step":0}, {"min":30,"max":16,"step":1},
                     {"min":16,"max":"Infinity","step":1}):
            with self.assertRaises(ValueError): TemperatureWheel(self.root, spec, 23)
        wheel = TemperatureWheel(self.root, {"min":16,"max":16.25,"step":.1}, 16)
        wheel.step(100)
        self.assertEqual(wheel.get(), "16.2")
