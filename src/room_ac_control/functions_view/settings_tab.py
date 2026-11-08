"""The Settings tab: comfort controls, feature switches and setting editors."""

import tkinter as tk

from ..choice_widgets import ChoicePanel
from ..control_choices import mode_icon
from ..controller import code, function_group
from ..i18n import localized_title, tr, translator
from ..smooth import aa_line, aa_oval
from ..theme import C, accent, blend, icon, measure, paint, rounded
from ..widgets import fan_bars, louver, section_label, switch
from .model import (
    AIRFLOW_NOTES,
    COMFORT,
    FAN_LEVELS,
    FEATURE_ORDER,
    FEATURES,
    WIDTH,
    glyph_for,
    is_toggle,
    louver_position,
    option_label,
    section_items,
)


class SettingsTabMixin:
    # Settings

    def draw_settings(self, c, y):
        selected = self.app.selected
        controls = selected.get("controls", {})
        tone = self.tone()
        x0, x1 = 16, WIDTH - 16
        section_label(c, 4, y + 7, "Comfort")
        y += 24
        top = y
        y += 16
        blocks = []
        options = self.app.mode_options()
        if options:
            blocks.append("mode")
        if "windSpeed" in controls and selected.get("fans"):
            blocks.append("fan")
        if self.app.airflow_spec():
            blocks.append("airflow")
        if "tempSel" in controls:
            blocks.append("temperature")
        for index, block in enumerate(blocks):
            if index:
                self.divider(c, y)
                y += 16
            if block == "mode":
                self.text(c, x0, y + 9, "Mode", -14, weight="bold")
                self.text(c, x1, y + 9, "Takes effect after Apply", -12, C.MUTED, "e", "semibold")
                y += 26
                gap = 6
                width = (x1 - x0 - gap * (len(options) - 1)) / len(options)
                current = self.app.base_mode()
                for i, option in enumerate(options):
                    bx = x0 + i * (width + gap)
                    label = option["label"]
                    on = label == current
                    color = accent(label)
                    fill = self.app.soft(color) if on else C.SURFACE
                    rounded(c, bx, y, bx + width, y + 66, 14, fill=fill, outline=color if on else fill, width=1.5)
                    ink = color if on else C.MUTED
                    icon(c, mode_icon(label), bx + width / 2, y + 24, ink, scale=0.8, bg=fill)
                    caption = tr(c, label)
                    size = -12 if measure(c, caption, -12, "bold") <= width - 6 else -10
                    self.text(c, bx + width / 2, y + 48, caption, size, ink, "center", "bold", translate=False)
                    self.hit((bx, y, bx + width, y + 66), lambda option=option: self.stage_mode(option))
                y += 66 + 16
            elif block == "fan":
                self.text(c, x0, y + 9, "Fan speed", -14, weight="bold")
                y += 26
                fans = list(selected["fans"].items())
                gap = 6
                width = (x1 - x0 - gap * (len(fans) - 1)) / len(fans)
                for i, (label, value) in enumerate(fans):
                    bx = x0 + i * (width + gap)
                    on = label == self.app.fan.get()
                    fill = self.app.soft(tone) if on else C.SURFACE
                    rounded(c, bx, y, bx + width, y + 60, 14, fill=fill, outline=tone if on else fill, width=1.5)
                    ink = tone if on else C.MUTED
                    fan_bars(
                        c,
                        bx + width / 2 - 9,
                        y + 26,
                        FAN_LEVELS.get(label, 0),
                        ink if on else C.FAINT,
                        fill,
                        heights=(7, 11, 15),
                        width=5,
                    )
                    self.text(c, bx + width / 2, y + 43, label, -12, ink, "center", "bold")
                    self.hit((bx, y, bx + width, y + 60), lambda value=value: self.stage("windSpeed", value))
                y += 60 + 16
            elif block == "airflow":
                value = self.app.airflow_value()
                rounded(c, x0, y, x0 + 64, y + 52, 14, fill=C.SURFACE, outline="")
                louver(c, x0 + 4, y + 1, louver_position(value), C.TEXT, tone, scale=0.78)
                self.text(c, x0 + 78, y + 16, "Airflow", -14, weight="bold")
                note = tr(c, value) + (" · " + tr(c, AIRFLOW_NOTES[value]) if value in AIRFLOW_NOTES else "")
                self.text(c, x0 + 78, y + 36, note, -12, C.MUTED, weight="semibold", translate=False)
                icon(c, "next", x1 - 8, y + 26, C.MUTED, scale=0.7, bg=C.CARD)
                self.hit((x0, y, x1, y + 52), self.open_airflow_sheet)
                y += 52 + 16
            elif block == "temperature":
                spec = controls["tempSel"]
                self.text(c, x0, y + 11, "Target temperature", -14, weight="bold")
                number = translator(c).number
                low, high = number(f"{spec['min']:g}"), number(f"{spec['max']:g}")
                note = f"{low}–{high} °C · " + tr(c, "{value}° steps").format(value=number(f"{spec['step']:g}"))
                self.text(c, x0, y + 31, note, -12, C.MUTED, weight="semibold", translate=False)
                try:
                    value = number(f"{float(self.app.temp.get()):g}") + "°"
                except ValueError:
                    value = "—"
                plus, minus = x1 - 20, x1 - 20 - 40 - 56
                for x, direction in ((minus, -1), (plus, 1)):
                    aa_oval(c, x - 20, y + 1, x + 20, y + 41, fill=C.SURFACE, outline="")
                    aa_line(c, x - 7, y + 21, x + 7, y + 21, fill=C.TEXT, width=2.4, capstyle="round")
                    if direction > 0:
                        aa_line(c, x, y + 14, x, y + 28, fill=C.TEXT, width=2.4, capstyle="round")
                    self.hit((x - 20, y + 1, x + 20, y + 41), lambda direction=direction: self.step_temp(direction))
                self.text(c, (minus + plus) / 2, y + 21, value, -24, tone, "center", "light", translate=False)
                y += 42 + 16
        if blocks:
            self.card(c, 0, top, WIDTH, y)
        else:
            self.text(c, WIDTH / 2, y + 20, "No comfort controls are exposed by your AC.", -13, C.MUTED, "center")
            y += 40
        y += 16
        # Features: on/off settings as tiles.
        toggles = [(key, controls[key]) for key in FEATURE_ORDER if key in controls and is_toggle(controls[key])]
        toggles += [
            (key, spec)
            for key, spec in controls.items()
            if key not in FEATURE_ORDER
            and key not in COMFORT
            and is_toggle(spec)
            and function_group(key, label=spec["label"]) != "maintenance"
        ]
        if toggles:
            section_label(c, 4, y + 7, "Features")
            y += 24
            width = (WIDTH - 10) / 2
            for index, (key, spec) in enumerate(toggles):
                bx, by = (index % 2) * (width + 10), y + (index // 2) * 126
                self.draw_feature(c, bx, by, width, key, spec)
            y += ((len(toggles) + 1) // 2) * 126
            y += 6
        # Anything else the AC exposes, as rows.
        others = [
            item
            for item in section_items(self.app.selected, "settings")
            if item["key"] not in COMFORT and not is_toggle(item["spec"])
        ]
        if others:
            section_label(c, 4, y + 7, "More settings")
            y += 24
            top = y
            for index, item in enumerate(others):
                if index:
                    aa_line(c, 16, y, WIDTH, y, fill=C.TRACK)
                spec = item["spec"]
                self.text(c, 16, y + 26, spec["label"], -14, weight="bold")
                value = tr(c, option_label(spec, self.app.current(spec["key"])))
                self.text(c, WIDTH - 36, y + 26, value, -13, C.MUTED, "e", "semibold", translate=False)
                icon(c, "next", WIDTH - 18, y + 26, C.MUTED, scale=0.6, bg=C.CARD)
                self.hit((0, y, WIDTH, y + 52), lambda spec=spec: self.edit_setting(spec))
                y += 52
            self.card(c, 0, top, WIDTH, y)
            y += 16
        self.visible_items = [dict(item, section="settings") for item in section_items(selected, "settings")]
        return y

    def draw_feature(self, c, x, y, width, key, spec):
        glyph, tone_key, description = FEATURES.get(key, (glyph_for(spec["label"]), "auto", ""))
        if key not in FEATURES and spec.get("description"):
            description = spec["description"]
        color = accent(tone_key)
        on = code(self.app.current(key)) == "1"
        fill = blend(color, C.CARD, 0.08) if on else C.CARD
        rounded(c, x, y, x + width, y + 116, 18, fill=fill, outline=blend(color, C.BG, 0.35) if on else fill, width=1.5)
        square = blend(color, C.CARD, 0.16) if on else C.SURFACE
        rounded(c, x + 14, y + 14, x + 50, y + 50, 12, fill=square, outline="")
        icon(c, glyph, x + 32, y + 32, color if on else C.MUTED, scale=0.7, bg=square)
        switch(c, x + width - 54, y + 20, on, color)
        self.text(c, x + 14, y + 70, spec["label"], -14, weight="bold")
        if description:
            self.text(c, x + 14, y + 82, description, -12, C.MUTED, "nw", width=width - 28)
        self.hit((x, y, x + width, y + 116), lambda: self.toggle_feature(key))

    def stage(self, key, value):
        self.app.staged(key, value)
        self.render(keep_scroll=True)

    def stage_mode(self, option):
        self.app.pick_mode(option)
        self.render(keep_scroll=True)

    def step_temp(self, direction):
        self.app.step_temp(direction)
        self.render(keep_scroll=True)

    def toggle_feature(self, key):
        if key == "silentSleepStatus":
            self.app.toggle_sleep()
        else:
            self.app.staged(key, "0" if code(self.app.current(key)) == "1" else "1")
        self.render(keep_scroll=True)

    def edit_setting(self, spec, card=None):
        """An editor for settings outside the Comfort card: a choice panel, or a value field."""
        key = spec["key"]
        if spec["kind"] == "enum":
            from ..control_choices import airflow_choices

            if key in {"windDirectionVertical", "windDirectionHorizontal"}:
                options = airflow_choices(spec)
            else:
                options = [
                    {
                        "label": label,
                        "value": value,
                        "glyph": glyph_for(spec["label"]),
                        "description": spec.get("description", ""),
                    }
                    for label, value in spec["options"].items()
                ]
            self.choice_panel = ChoicePanel(
                self.window, spec["label"], options, self.app.current(key), lambda value: self.stage(key, value)
            )
            return
        from tkinter import ttk

        from ..i18n import localized

        window = tk.Toplevel(self.window)
        localized_title(window, spec["label"])
        paint(window, bg="BG")
        window.resizable(False, False)
        window.transient(self.window)
        window.grab_set()

        def close_detail():
            window.destroy()
            self.window.grab_set()

        from ..window_header import WindowHeader

        window.header = WindowHeader(window, spec["label"], close_detail, maximize=False)
        body = ttk.Frame(window, padding=22)
        body.pack(fill="both", expand=True)
        getter, initial = self.app.field(
            body, spec, self.app.current(key), use_reported=True, show_label=key != "tempSel"
        )
        hint = (
            f"Drag, scroll or use ↑ ↓ · {spec['min']:g}–{spec['max']:g}°C · Step {spec['step']:g}"
            if key == "tempSel"
            else f"Range {spec['min']:g}–{spec['max']:g} · Step {spec['step']:g}"
        )
        localized(ttk.Label(body, text=hint, style="Muted.TLabel")).pack(anchor="w", pady=12)

        def done():
            value = getter()
            if value is not None:
                self.stage(key, value)
            close_detail()

        localized(ttk.Button(body, text="Set value", style="Accent.TButton", command=done)).pack(fill="x")
        window.protocol("WM_DELETE_WINDOW", close_detail)
