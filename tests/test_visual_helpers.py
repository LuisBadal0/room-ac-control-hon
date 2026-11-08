"""Mode and airflow choices, canvas hover highlighting and the ttk button theme."""

import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from room_ac_control import canvas_hover
from room_ac_control.button_theme import configure_styles, install_button_theme
from room_ac_control.canvas_hover import CanvasHover
from room_ac_control.control_choices import airflow_choices, airflow_icon, mode_icon
from room_ac_control.theme import C

VERTICAL = {
    "key": "windDirectionVertical",
    "label": "Vertical airflow",
    "options": {"Position 1": "2", "Position 5": "7", "Swing": "8", "Fixed": "9"},
}


class ControlChoiceTests(unittest.TestCase):
    def test_mode_icons_cover_every_mode_and_night_variants(self):
        self.assertEqual(
            [mode_icon(label) for label in ("Auto", "Cool", "Dry", "Heat", "Fan")],
            ["leaf", "snow", "drop", "sun", "fan"],
        )
        self.assertEqual(mode_icon("Cool Night"), "moon")
        self.assertEqual(mode_icon("HEAT NIGHT"), "moon")
        self.assertEqual(mode_icon("Purify"), "wind")

    def test_airflow_icons_follow_position_labels(self):
        self.assertEqual(airflow_icon("Swing"), "swing")
        self.assertEqual([airflow_icon(f"Position {n}") for n in range(1, 6)], [f"vane_{n}" for n in range(1, 6)])
        self.assertEqual(airflow_icon("Position 6"), "wind")
        self.assertEqual(airflow_icon("Fixed"), "wind")

    def test_airflow_choices_keep_wire_codes_and_describe_positions(self):
        choices = airflow_choices(VERTICAL)
        self.assertEqual([choice["value"] for choice in choices], ["2", "7", "8", "9"])
        self.assertEqual(
            [choice["description"] for choice in choices],
            [
                "Vertical airflow · Most closed",
                "Vertical airflow · Most open",
                "Vertical airflow · Automatic swing",
                "Vertical airflow",
            ],
        )
        self.assertEqual([choice["glyph"] for choice in choices], ["vane_1", "vane_5", "swing", "wind"])

    def test_airflow_choices_as_patches_name_their_axis(self):
        choices = airflow_choices(VERTICAL, patch=True)
        self.assertEqual(choices[0]["value"], {"windDirectionVertical": "2"})
        self.assertEqual(airflow_choices({"key": "windDirectionHorizontal", "label": "Horizontal"}), [])


class FakeCanvas:
    def __init__(self):
        self.bindings = {}
        self.cursor = None

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def configure(self, cursor):
        self.cursor = cursor


class CanvasHoverTests(unittest.TestCase):
    def setUp(self):
        self.canvas = FakeCanvas()
        self.styled = []
        patcher = patch.object(canvas_hover, "restyle", lambda canvas, item, **style: self.styled.append((item, style)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.hover = CanvasHover(self.canvas)
        self.hover.add((0, 0, 10, 10), "power", {"fill": "grey"}, {"fill": "blue"})
        self.hover.add((20, 0, 30, 10), "eco", {"fill": "grey"}, {"fill": "green"})

    def move(self, x, y):
        self.canvas.bindings["<Motion>"](SimpleNamespace(x=x, y=y))

    def test_binds_pointer_motion_and_leave(self):
        self.assertEqual(set(self.canvas.bindings), {"<Motion>", "<Leave>"})

    def test_highlights_only_on_entering_and_leaving_a_region(self):
        self.move(5, 5)
        self.move(6, 6)  # Still inside: no repeated restyle.
        self.assertEqual(self.styled, [("power", {"fill": "blue"})])
        self.assertEqual(self.canvas.cursor, "hand2")
        self.move(25, 5)
        self.assertEqual(self.styled[1:], [("power", {"fill": "grey"}), ("eco", {"fill": "green"})])
        self.canvas.bindings["<Leave>"](None)
        self.assertEqual(self.styled[-1], ("eco", {"fill": "grey"}))
        self.assertEqual(self.canvas.cursor, "")

    def test_pointer_positions_follow_the_canvas_scale(self):
        self.hover.scale = 2
        self.move(50, 10)  # (25, 5) in design units: the Eco region.
        self.assertEqual(self.styled, [("eco", {"fill": "green"})])

    def test_disabled_or_reset_regions_do_not_highlight(self):
        self.hover.reset(enabled=False)
        self.hover.add((0, 0, 10, 10), "power", {"fill": "grey"}, {"fill": "blue"})
        self.move(5, 5)
        self.assertEqual(self.styled, [])
        self.assertEqual(self.canvas.cursor, "")


class ButtonThemeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(C.use, C.mode)

    def test_styles_follow_the_active_palette_and_can_be_reapplied(self):
        for mode in ("light", "dark", "light"):
            C.use(mode)
            style = configure_styles(self.root)
            self.assertEqual(style.theme_use(), "clam")
            self.assertEqual(style.lookup("TFrame", "background").upper(), C.BG.upper())
            self.assertEqual(style.lookup("Accent.TButton", "foreground").upper(), C.ON_BRAND.upper())
            surface = style.layout("Accent.TButton")[0][0]
            self.assertEqual(surface, f"RoomAC.{mode}.Accent.TButton.surface")
        # Each palette's nine-slice images are made once and kept alive.
        images = self.root.__dict__["button_theme_images"]
        self.assertEqual(set(images), {"light", "dark"})
        self.assertEqual(len(images["light"]), 15)

    def test_earlier_entry_point_still_configures_styles(self):
        style = install_button_theme(self.root)
        self.assertEqual(style.lookup("Card.TFrame", "background").upper(), C.CARD.upper())


if __name__ == "__main__":
    unittest.main()
