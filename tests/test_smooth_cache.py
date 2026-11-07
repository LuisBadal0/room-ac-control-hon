"""The shared image cache never deletes an image that is still on screen."""
import tkinter as tk
import unittest
from unittest.mock import patch

from room_ac_control import smooth
from room_ac_control.smooth import _images, aa_text
from room_ac_control.theme import icon


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.canvas = tk.Canvas(self.root)
        self.cache = _images(self.canvas)

    def tearDown(self):
        self.root.destroy()

    def shown(self, item):
        image = self.canvas.itemcget(item, "image")
        return bool(image) and bool(self.root.tk.call("image", "inuse", image))

    def test_passing_the_limit_keeps_what_is_on_screen_and_drops_the_rest(self):
        with patch.object(smooth, "CACHE_LIMIT", 20):
            on_screen = [aa_text(self.canvas, 0, 0, text=f"shown {n}", font=("Manrope", -12)) for n in range(10)]
            # Texts drawn and then removed, like an old "Connected · 13:00:01" after a refresh.
            for n in range(9):
                self.canvas.delete(aa_text(self.canvas, 0, 0, text=f"gone {n}", font=("Manrope", -12)))
            self.assertEqual(len(self.cache), 19)
            for n in range(5):
                aa_text(self.canvas, 0, 0, text=f"new {n}", font=("Manrope", -12))
        self.assertTrue(all(self.shown(item) for item in on_screen))
        self.assertFalse(any(key[1].startswith("gone") for key in self.cache))

    def test_a_cache_full_of_shown_images_still_keeps_them_all(self):
        with patch.object(smooth, "CACHE_LIMIT", 10):
            items = [aa_text(self.canvas, 0, 0, text=f"shown {n}", font=("Manrope", -12)) for n in range(30)]
        self.assertTrue(all(self.shown(item) for item in items))
        self.assertEqual(len(self.cache), 30)

    def test_redrawing_an_icon_reuses_its_image(self):
        # Each icon gets a new canvas tag; the tag must not make it a new image.
        icon(self.canvas, "clock", 20, 20, "#5CC8FF")
        size = len(self.cache)
        for _ in range(5):
            icon(self.canvas, "clock", 20, 20, "#5CC8FF")
        self.assertEqual(len(self.cache), size)


if __name__ == "__main__":
    unittest.main()
