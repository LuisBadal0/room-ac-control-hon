"""Pointer, wheel and menu input on the dashboard; edits are staged, not sent."""

import math
import tkinter as tk
from tkinter import ttk

from ..choice_widgets import ChoicePanel, SelectField
from ..control_choices import airflow_choices, mode_icon
from ..controller import code, mode_choices
from ..i18n import (
    localized,
)
from ..temperature_wheel import TemperatureWheel
from ..theme import (
    font,
)
from .layout import (
    DIAL,
    DIAL_START,
    DIAL_SWEEP,
    WIDTH,
    equal,
)


class ControlsMixin:
    def toggle_power(self):
        if self.busy or not self.selected:
            return
        self.action("off" if self.selected["power"] == "On" else "on")

    def pick_mode(self, option):
        for name, value in self.memory.mode_values(self.selected, dict(option["value"])).items():
            self.staged(name, value)

    def airflow_spec(self):
        controls = self.selected.get("controls", {})
        return controls.get("windDirectionVertical") or controls.get("windDirectionHorizontal")

    def airflow_value(self):
        """The current airflow option's label, such as Swing or Position 2."""
        spec = self.airflow_spec()
        if not spec:
            return "Unavailable"
        value = self.current(spec["key"])
        if value is None:
            return "Unknown"
        return next((label for label, option in spec["options"].items() if equal(option, value)), "Unknown")

    def cycle(self, key, options):
        """Step to the next option, wrapping around, as the mockup's tiles do."""
        values = list(options.values())
        if not values:
            return
        current = self.current(key)
        index = next((i for i, value in enumerate(values) if equal(value, current)), -1)
        self.staged(key, values[(index + 1) % len(values)])

    def ac_on(self):
        return bool(self.selected) and self.selected.get("power") == "On"

    def open_airflow_sheet(self):
        """The same airflow picker as All functions › Settings."""
        if self.busy or not self.airflow_spec():
            return
        from ..functions_view import DashboardSheets

        if getattr(self, "sheets", None) is None:
            self.sheets = DashboardSheets(self)
        self.sheets.open_airflow_sheet()

    def cycle_fan(self):
        spec = self.selected.get("controls", {}).get("windSpeed")
        if spec:
            self.cycle("windSpeed", self.selected.get("fans") or spec["options"])

    def cycle_airflow(self):
        spec = self.airflow_spec()
        if spec:
            self.cycle(spec["key"], spec["options"])

    def toggle_sleep(self):
        if "silentSleepStatus" not in self.selected.get("controls", {}):
            return
        value = "0" if code(self.current("silentSleepStatus")) == "1" else "1"
        patch = {"silentSleepStatus": value}
        if code(self.current("machMode")) in {"1", "4"}:
            patch["machMode"] = code(self.current("machMode"))
            patch = self.memory.mode_values(self.selected, patch)
        for name, new_value in patch.items():
            self.staged(name, new_value)

    def scale(self):
        return max(self.canvas.winfo_width(), 480) / WIDTH

    def click(self, event):
        if self.busy:
            return
        self.canvas.focus_set()
        s = self.scale()
        x, y = event.x / s, event.y / s
        for (x1, y1, x2, y2), fn in self.hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                fn()
                return
        if self.dial_angle(x, y, strict=True) is not None:
            self.dial_drag = True
            self.dial_from_event(event)

    def release_dial(self, event=None):
        if self.dial_drag:
            self.dial_drag = False
            self.draw()

    def dial_angle(self, x, y, strict=False):
        """The ring position (0–1) under a point, or None away from the ring."""
        cx, cy, r = DIAL
        distance = math.hypot(x - cx, y - cy)
        if strict and not r - 34 <= distance <= r + 28:
            return None
        if distance < 8:
            return None
        angle = (math.degrees(math.atan2(y - cy, x - cx)) - DIAL_START) % 360
        if angle > DIAL_SWEEP:
            if strict:
                return None
            angle = 0 if angle > DIAL_SWEEP + (360 - DIAL_SWEEP) / 2 else DIAL_SWEEP
        return angle / DIAL_SWEEP

    def dial_from_event(self, event):
        values = [float(v) for v in self.selected.get("temperatures", [])]
        if not values:
            return
        s = self.scale()
        ratio = self.dial_angle(event.x / s, event.y / s)
        if ratio is None:
            return
        target = min(values) + ratio * (max(values) - min(values))
        value = min(values, key=lambda v: abs(v - target))
        try:
            same = float(self.temp.get()) == value
        except ValueError:
            same = False
        if not same:
            self.staged("tempSel", value)
        else:
            self.draw()

    def drag_temperature(self, event):
        if self.dial_drag and not self.busy and self.selected:
            self.dial_from_event(event)

    def wheel_temperature(self, event):
        if self.busy or not self.selected or not event.delta:
            return
        s = self.scale()
        cx, cy, r = DIAL
        if math.hypot(event.x / s - cx, event.y / s - cy) <= r + 30:
            self.step_temp(1 if event.delta > 0 else -1)

    def step_temp(self, direction):
        values = [float(v) for v in self.selected["temperatures"]]
        if not values:
            return
        try:
            current = float(self.temp.get())
        except ValueError:
            current = values[0]
        index = min(range(len(values)), key=lambda n: abs(values[n] - current))
        self.staged("tempSel", values[max(0, min(len(values) - 1, index + direction))])

    def toggle_label(self, key):
        if key not in self.selected.get("controls", {}):
            return "Unavailable"
        value = self.current(key)
        return {"0": "Off", "1": "On"}.get(code(value), "Unknown")

    def choice_menu(self, key):
        spec = self.selected.get("controls", {}).get(key)
        if not spec:
            return
        if key == "machMode":
            options = mode_choices(self.selected)
            current = {"machMode": self.current("machMode"), "silentSleepStatus": self.current("silentSleepStatus")}
            current.update(self.dirty)

            def selected(patch):
                for name, value in self.memory.mode_values(self.selected, patch).items():
                    self.staged(name, value)
        else:
            options = [
                {"label": label, "value": value, "glyph": "fan" if key == "windSpeed" else "moon"}
                for label, value in spec.get("options", {}).items()
            ]
            current = self.current(key)

            def selected(value):
                patch = {key: value}
                if key == "silentSleepStatus" and code(self.current("machMode")) in {"1", "4"}:
                    patch["machMode"] = code(self.current("machMode"))
                    patch = self.memory.mode_values(self.selected, patch)
                for name, new_value in patch.items():
                    self.staged(name, new_value)

        self.choice_panel = ChoicePanel(self.root, spec["label"], options, current, selected)

    def airflow_label(self):
        controls = self.selected.get("controls", {})
        if not any(k in controls for k in ("windDirectionVertical", "windDirectionHorizontal")):
            return "Unavailable"
        if all(self.current(k) is None for k in ("windDirectionVertical", "windDirectionHorizontal")):
            return "Unknown"
        vertical = code(self.current("windDirectionVertical")) == "8"
        horizontal = code(self.current("windDirectionHorizontal")) == "7"
        if vertical and horizontal:
            return "Both"
        if vertical:
            return "Vertical"
        if horizontal:
            return "Horizontal"
        return "Fixed"

    def airflow_menu(self):
        options = []
        current = {}
        for key in ("windDirectionVertical", "windDirectionHorizontal"):
            spec = self.selected.get("controls", {}).get(key)
            if not spec:
                continue
            current[key] = self.current(key)
            options.extend(airflow_choices(spec, patch=True))

        def selected(patch):
            for key, value in patch.items():
                self.staged(key, value)

        if options:
            self.choice_panel = ChoicePanel(self.root, "Airflow", options, current, selected)

    def field(self, parent, spec, override=None, use_reported=False, show_label=True):
        row = ttk.Frame(parent, padding=(0, 7))
        row.pack(fill="x")
        label = spec["label"]
        value = (
            override if override is not None else (spec["value"] if not use_reported or spec.get("reported") else "")
        )
        if show_label:
            localized(ttk.Label(row, text=label)).pack(side="left")
        if spec["kind"] == "enum":
            options = spec["options"]
            variable = tk.StringVar(value=next((k for k, v in options.items() if equal(v, value)), "Choose…"))
            choices = None
            if spec["key"] in {"windDirectionVertical", "windDirectionHorizontal"}:
                choices = [dict(option, value=option["label"]) for option in airflow_choices(spec)]
            elif spec["key"] == "machMode":
                choices = [{"label": label, "value": label, "glyph": mode_icon(label)} for label in options]
            widget = SelectField(row, variable, options, spec["label"], choices=choices)
            getter = lambda: options.get(variable.get())
        elif spec["key"] == "tempSel":
            widget = TemperatureWheel(row, spec, value)
            getter = widget.get
        else:
            variable = tk.StringVar(value=f"{float(value):g}" if value != "" else "")
            widget = ttk.Spinbox(
                row, textvariable=variable, from_=spec["min"], to=spec["max"], increment=spec["step"], width=20
            )
            getter = lambda: variable.get() or None
        widget.pack(side="right" if show_label else "top")
        if use_reported and value == "":
            localized(ttk.Label(parent, text="Current value not reported", style="Muted.TLabel", font=font(8))).pack(
                anchor="e"
            )
        return getter, value
