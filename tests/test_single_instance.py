"""One running copy per Windows session; a second start shows the first instead."""
import os
import unittest
import uuid

from room_ac_control.single_instance import SingleInstance


@unittest.skipUnless(os.name == "nt", "Windows named objects required")
class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        # A unique name, so a Room AC Control already running on this computer is never touched.
        self.name = f"RoomACControlTest-{uuid.uuid4().hex}"

    def test_a_second_start_asks_the_first_to_show_once(self):
        first = SingleInstance(self.name)
        second = SingleInstance(self.name)
        try:
            self.assertTrue(first.first)
            self.assertFalse(second.first)
            self.assertFalse(first.show_requested())
            second.show_running()
            self.assertTrue(first.show_requested())
            self.assertFalse(first.show_requested())  # Each start shows the window once.
        finally:
            second.close()
            first.close()

    def test_after_the_app_closes_the_next_start_is_first_again(self):
        SingleInstance(self.name).close()
        again = SingleInstance(self.name)
        try:
            self.assertTrue(again.first)
        finally:
            again.close()
