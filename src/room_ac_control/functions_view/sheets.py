"""Bottom sheets shared by All functions and the dashboard, and their number wheel."""

import tkinter as tk

from ..i18n import tr, translator
from ..smooth import aa_text
from ..temperature_wheel import TemperatureWheel
from ..theme import C, blend, font, rounded
from ..widgets import Overlay, louver, raise_widget, section_label
from .model import (
    SIZE,
    louver_position,
)


class SheetWheel(TemperatureWheel):
    """The preset sheet's temperature column: neighbours above and below a tinted band."""

    ROW_HEIGHT = 34
    CLICK_TOP, CLICK_BOTTOM = 38, 82

    def __init__(self, parent, spec, value, tone):
        self.tone_color = tone
        super().__init__(parent, spec, value)
        self.configure(width=108, height=120)
        self.draw()

    def draw(self):
        if not self.enabled:
            self.cancel_drag()
        self.delete("all")
        self.configure(bg=C.SURFACE, cursor="sb_v_double_arrow" if self.enabled else "arrow")
        tone = getattr(self, "tone_color", C.BRAND)
        rounded(self, 0, 36, 108, 84, 12, fill=blend(tone, C.SURFACE, 0.16), outline="")
        for offset in range(-1, 2):
            index = self.value + offset
            if not 0 <= index < self.limit:
                continue
            y = 60 + offset * self.ROW_HEIGHT + self.drag_offset
            centre = abs(y - 60) < self.ROW_HEIGHT / 2
            text = (
                "—"
                if offset == 0 and not self.chosen
                else translator(self).number(self.number(index)) + ("°" if centre else "")
            )
            aa_text(
                self, 54, y, text=text, fill=tone if centre else C.FAINT, font=font(-40 if centre else -18, "light")
            )


class SheetHost:
    """Bottom sheets over a dimmed window, shared by All functions and the dashboard.

    A host provides `window`, `app` and `sheet` (None while closed)."""

    def tone(self):
        """The accent for this host: the dashboard's dial colour (grey while the AC is off)."""
        return self.app.dial_accent()

    def text(self, c, x, y, value, size, color=None, anchor="w", weight="normal", width=None, translate=True):
        options = {"width": width} if width else {}
        return aa_text(
            c,
            x,
            y,
            text=tr(c, value) if translate else value,
            anchor=anchor,
            fill=color or C.TEXT,
            font=font(size, weight),
            **options,
        )

    def open_sheet(self, draw):
        self.close_sheet()
        self.overlay = Overlay(self.window, self.close_sheet)
        canvas = tk.Canvas(self.window, highlightthickness=0, takefocus=True)
        canvas.bind("<Button-1>", self.sheet_click)
        canvas.bind("<Escape>", lambda event: self.close_sheet())
        self.sheet = {"canvas": canvas, "draw": lambda: self.draw_sheet(draw), "hits": [], "widgets": []}
        self.draw_sheet(draw)
        canvas.place(x=0, rely=1, relwidth=1, anchor="sw")
        raise_widget(canvas)
        canvas.focus_set()

    def draw_sheet(self, draw):
        sheet = self.sheet
        c = sheet["canvas"]
        c.delete("all")
        c.configure(bg=C.BG)
        sheet["hits"] = []
        width = SIZE[0]
        height = draw(c, width)
        c.configure(height=height)
        sheet["height"] = height
        background = rounded(c, 0, 0, width, height + 40, 26, fill=C.CARD, outline=C.TRACK)
        c.tag_lower(background)
        rounded(c, width / 2 - 20, 12, width / 2 + 20, 17, 3, fill=C.STRONG, outline="")

    def sheet_hit(self, box, action):
        self.sheet["hits"].append((box, action))

    def sheet_click(self, event):
        for (x1, y1, x2, y2), action in list(self.sheet["hits"]):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                action()
                return

    def close_sheet(self):
        if not self.sheet:
            return
        for widget in self.sheet["widgets"]:
            widget.destroy()
        if self.sheet["canvas"].winfo_exists():
            self.sheet["canvas"].destroy()
        self.sheet = None
        self.overlay.destroy()
        self.sheet_closed()

    def sheet_buttons(self, c, y, width, back, primary, run, primary_flex=2):
        tone = self.tone()
        gap = 10
        left_width = (width - 48 - gap) / (1 + primary_flex)
        x1, x2 = 24, 24 + left_width
        rounded(c, x1, y, x2, y + 50, 14, fill=C.CARD, outline=C.STRONG, width=1.2)
        self.text(c, (x1 + x2) / 2, y + 25, back, -14, C.TEXT, "center", "bold")
        self.sheet_hit((x1, y, x2, y + 50), self.close_sheet)
        x1, x2 = x2 + gap, width - 24
        rounded(c, x1, y, x2, y + 50, 14, fill=tone, outline="")
        self.text(c, (x1 + x2) / 2, y + 25, primary, -14, C.ON_BRAND, "center", "black")
        self.sheet_hit((x1, y, x2, y + 50), run)
        return y + 50 + 28

    def open_airflow_sheet(self):
        controls = self.app.selected.get("controls", {})
        specs = [controls[key] for key in ("windDirectionVertical", "windDirectionHorizontal") if key in controls]
        if not specs:
            return
        self.sheet_choice = {spec["key"]: self.app.current(spec["key"]) for spec in specs}

        def choose(key, value):
            self.sheet_choice[key] = value
            self.sheet["draw"]()

        def done():
            for key, value in self.sheet_choice.items():
                if value is not None:
                    self.app.staged(key, value)
            self.close_sheet()
            self.sheet_done()

        def draw(c, width):
            from ..dashboard import equal

            tone = self.tone()
            y = 30
            self.text(c, 24, y + 12, "Airflow", -22, weight="black")
            self.text(
                c,
                24,
                y + 38,
                "Vertical louver. Position 1 is the most closed, 5 the most open.",
                -13,
                C.MUTED,
                width=width - 48,
            )
            y += 62
            for spec in specs:
                if len(specs) > 1:
                    section_label(c, 24, y + 6, spec["label"])
                    y += 22
                options = list(spec["options"].items())
                cell = (width - 48 - 20) / 3
                for index, (label, value) in enumerate(options):
                    x = 24 + (index % 3) * (cell + 10)
                    top = y + (index // 3) * 128
                    on = equal(value, self.sheet_choice.get(spec["key"]))
                    fill = self.app.soft(tone) if on else C.SURFACE
                    rounded(c, x, top, x + cell, top + 118, 18, fill=fill, outline=tone if on else fill, width=2)
                    louver(c, x + cell / 2 - 36, top + 14, louver_position(label), C.TEXT, tone if on else C.FAINT)
                    self.text(c, x + cell / 2, top + 96, label, -13, tone if on else C.TEXT, "center", "bold")
                    self.sheet_hit(
                        (x, top, x + cell, top + 118), lambda key=spec["key"], value=value: choose(key, value)
                    )
                y += ((len(options) + 2) // 3) * 128 + 6
            return self.sheet_buttons(c, y + 6, width, "Cancel", "Set value", done)

        self.open_sheet(draw)

    def sheet_closed(self):
        """Called after a sheet closes."""

    def sheet_done(self):
        """Called after a sheet's choice is staged."""


class DashboardSheets(SheetHost):
    """The airflow picker opened from the dashboard's Airflow tile."""

    def __init__(self, app):
        self.app, self.window, self.sheet = app, app.root, None

    def sheet_done(self):
        self.app.draw()
