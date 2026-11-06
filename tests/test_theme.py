"""Palette contrast, Windows app-mode resolution and isolated theme persistence."""
from copy import deepcopy
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from room_ac_control import theme
from room_ac_control.theme import PALETTES, ACCENTS, Colors, accent, resolve_theme, windows_mode
from room_ac_control.secure_state import SecureState
from room_ac_control.translations import PORTUGUESE
from room_ac_control.dashboard import THEME_CHOICES


def luminance(color):
    channels = []
    for index in (1, 3, 5):
        value = int(color[index:index+2], 16) / 255
        channels.append(value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4)
    return .2126*channels[0] + .7152*channels[1] + .0722*channels[2]


def contrast(foreground, background):
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high+.05) / (low+.05)


class PaletteTests(unittest.TestCase):
    def test_both_palettes_define_the_same_valid_tokens(self):
        self.assertEqual(set(PALETTES["light"]), set(PALETTES["dark"]))
        for palette in PALETTES.values():
            for value in palette.values():
                self.assertRegex(value, re.compile(r"^#[0-9A-F]{6}$"))

    def test_text_pairs_meet_wcag_contrast_in_light_and_dark(self):
        text_pairs = [("TEXT","BG"),("TEXT","CARD"),("TEXT","SURFACE"),("MUTED","BG"),("MUTED","CARD"),
                      ("ON_BRAND","BRAND"),("ON_SOFT","SOFT"),("OK_TEXT","OK_BG"),("WARN_TEXT","WARN_BG"),("DANGER_TEXT","DANGER_BG"),
                      ("BRAND","CARD"),("BRAND","BG"),("TEXT","SEGMENT"),("TEXT","RAISED")]
        for mode, palette in PALETTES.items():
            for foreground, background in text_pairs:
                with self.subTest(mode=mode, pair=(foreground, background)):
                    self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 4.5)
            # Field borders, toggles and the slider fill are non-text UI (3:1).
            for foreground, background in (("FIELD","CARD"),("BRAND","TRACK"),("OK","BG")):
                with self.subTest(mode=mode, pair=(foreground, background)):
                    self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 3)

    def test_palettes_use_the_ambient_surfaces(self):
        light, dark = PALETTES["light"], PALETTES["dark"]
        self.assertEqual((light["BG"], light["CARD"], light["TEXT"]), ("#EEF1F5", "#FFFFFF", "#12161C"))
        self.assertEqual((dark["BG"], dark["CARD"], dark["TEXT"]), ("#0E1116", "#161B22", "#E8ECF1"))

    def test_mode_accents_are_readable_and_follow_the_mode(self):
        for mode, accents in ACCENTS.items():
            palette = PALETTES[mode]
            self.assertEqual(set(accents), {"cool", "heat", "dry", "fan", "auto", "off"})
            for name, color in accents.items():
                with self.subTest(mode=mode, accent=name):
                    self.assertRegex(color, re.compile(r"^#[0-9A-F]{6}$"))
                    if name != "off":  # Mode names and the selected mode's label use it as text.
                        self.assertGreaterEqual(contrast(color, palette["CARD"]), 4.5)
                        self.assertGreaterEqual(contrast(palette["ON_BRAND"], color), 4.5)
        try:
            theme.C.use("dark")
            self.assertEqual(accent("Heat Night"), ACCENTS["dark"]["heat"])
            self.assertEqual(accent("Cool"), ACCENTS["dark"]["cool"])
            self.assertEqual(accent("Unknown"), PALETTES["dark"]["BRAND"])
        finally:
            theme.C.use("light")

    def test_switching_updates_attributes_and_unknown_modes_fall_back_to_light(self):
        colors = Colors("dark")
        self.assertEqual((colors.mode, colors.BG), ("dark", "#0E1116"))
        colors.use("sepia")
        self.assertEqual((colors.mode, colors.BG), ("light", "#EEF1F5"))

    def test_bundled_lato_loads_privately(self):
        self.assertTrue(theme.load_fonts())
        self.assertEqual(theme.font(10, "bold"), ("Lato", 10, "bold"))
        self.assertEqual(theme.font(20, "black"), ("Lato Black", 20))
        fonts = Path(theme.__file__).parent / "assets" / "fonts"
        self.assertTrue((fonts / "OFL.txt").is_file())


class WindowsModeTests(unittest.TestCase):
    def registry(self, value=None, error=None):
        winreg = MagicMock()
        winreg.OpenKey.return_value.__enter__.return_value = "key"
        if error:
            winreg.OpenKey.side_effect = error
        winreg.QueryValueEx.return_value = (value, 4)
        return patch.dict("sys.modules", {"winreg": winreg})

    def test_apps_use_light_theme_selects_the_mode(self):
        with self.registry(0):
            self.assertEqual(windows_mode(), "dark")
            self.assertEqual(resolve_theme("system"), "dark")
        with self.registry(1):
            self.assertEqual(windows_mode(), "light")
        with self.registry(error=OSError("missing")):
            self.assertEqual(windows_mode(), "light")

    def test_explicit_preferences_ignore_windows(self):
        with self.registry(0):
            self.assertEqual(resolve_theme("light"), "light")
        with self.registry(1):
            self.assertEqual(resolve_theme("dark"), "dark")


class ThemePreferenceTests(unittest.TestCase):
    def test_preference_survives_restart_and_sign_out(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.dpapi"
            state = SecureState(path)
            self.assertEqual(state.theme(), "system")
            state.save_credentials("fixture@example.test", "fake-theme-test-password")
            state.save_theme("dark")
            reopened = SecureState(path)
            self.assertEqual(reopened.theme(), "dark")
            reopened.forget_credentials()
            self.assertEqual(SecureState(path).theme(), "dark")
            reopened.save_theme("system")
            self.assertEqual(SecureState(path).theme(), "system")

    def test_failed_write_rolls_back_and_invalid_values_are_safe(self):
        state = SecureState(persistent=False)
        before = deepcopy(state.data)
        with patch.object(state, "write", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                state.save_theme("dark")
        self.assertEqual(state.data, before)
        for value in ("sepia", {}, None):
            state.data["theme"] = value
            self.assertEqual(state.theme(), "system")
            with self.assertRaises(ValueError):
                state.save_theme(value)

    def test_appearance_choices_are_translated(self):
        for option in THEME_CHOICES:
            self.assertIn(option["label"], PORTUGUESE)
            self.assertIn(option["description"], PORTUGUESE)
        for text in ("Appearance", "Search functions", "Changed",
                     "Appearance changed for this session, but the preference could not be saved."):
            self.assertIn(text, PORTUGUESE)



class UnitArtworkTests(unittest.TestCase):
    def test_artwork_has_no_hard_outline_and_scales_smoothly(self):
        from PIL import Image
        with Image.open(theme.ASSETS / "unit.png") as image:
            image = image.convert("RGBA")
            # Shaded like hOn's unit: no grey outline ring around the body edge.
            middle = image.height // 2
            edge = next(x for x in range(image.width) if image.getpixel((x, middle))[3] == 255)
            self.assertGreater(sum(image.getpixel((edge, middle))[:3]) / 3, 200)
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display: {error}")
        try:
            root.withdraw()
            for width, expected in ((330, (300, 90)), (230, (200, 60)), (300, (300, 90))):
                photo = theme.unit_photo(root, width)
                self.assertEqual((photo.width(), photo.height()), expected)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
