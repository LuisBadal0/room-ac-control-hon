"""The preset sheet in Everyday use: a preset's values, saving them and starting it."""

from ..choice_widgets import ChoicePanel
from ..controller import code
from ..i18n import tr
from ..theme import C, blend, icon, measure, rounded
from ..widgets import louver, section_label
from .model import (
    FEATURES,
    PRESET_DEFAULTS,
    glyph_for,
    is_toggle,
    louver_position,
    option_label,
    preset_key,
)
from .sheets import (
    SheetWheel,
)


def preset_parameters(app, item):
    """A preset's editable values as (spec, initial value): its defaults, then what was last used."""
    selected = app.selected
    controls = selected.get("controls", {})
    if item["kind"] == "night":
        values = {
            **PRESET_DEFAULTS.get(preset_key(item), {}),
            **app.memory.mode_values(selected, dict(item["changes"])),
        }
        return [
            (controls[key], values.get(key, app.current(key)))
            for key in ("tempSel", "windSpeed", "windDirectionVertical", "muteStatus", "ecoMode")
            if key in controls
        ]
    saved = {
        **PRESET_DEFAULTS.get(preset_key(item), {}),
        **app.memory.function_values(selected["id"], item["command"], item["form"]),
    }
    return [
        (spec, saved.get(spec["key"], spec.get("value")))
        for spec in item["form"].get("parameters", [])
        if spec["key"] != "machMode"
    ]


def preset_request(app, item, values=None):
    """The command that starts a preset: ("on", settings) for a Night mode, else ("execute", …).

    Without `values`, the preset starts with the values its sheet would show."""
    if values is None:
        values = {spec["key"]: value for spec, value in preset_parameters(app, item)}
    values = {key: value for key, value in values.items() if value is not None}
    if item["kind"] == "night":
        request = dict(app.memory.mode_values(app.selected, dict(item["changes"])))
        request.update(values)
        request.update(item["changes"])
        return "on", request
    return "execute", {"command": item["command"], "category": item["form"]["category"], "parameters": values}


class PresetSheetMixin:
    def open_preset(self, item):
        """Review a preset, Night mode or maintenance routine, then start it explicitly."""
        color, glyph, description, features = self.preset_details(item)
        maintenance = item.get("section") == "maintenance" or (
            item["kind"] == "function" and item["form"].get("group") == "maintenance"
        )
        # Editable parameters: (spec, initial value).
        parameters = preset_parameters(self.app, item)
        values = {spec["key"]: value for spec, value in parameters}
        holder = {}

        def pick(key, value):
            values[key] = value
            self.sheet["draw"]()

        def draw(c, width):
            from ..dashboard import equal

            y = 30
            tint = self.app.soft(color)
            rounded(c, 24, y, 108, y + 84, 22, fill=tint, outline="")
            icon(c, glyph, 66, y + 42, color, scale=1.5, bg=tint)
            kind = "Maintenance routine" if maintenance else "Preset"
            self.text(c, 124, y + 12, tr(c, kind).upper(), -11, color, weight="black", translate=False)
            self.text(c, 124, y + 38, item["label"], -24, weight="black", width=width - 148)
            self.text(c, 124, y + 56, description, -13, C.MUTED, "nw", width=width - 148)
            y += 84 + 20
            temperature = next(((spec, value) for spec, value in parameters if spec["key"] == "tempSel"), None)
            airflows = [(spec, value) for spec, value in parameters if spec["key"].startswith("windDirection")]
            enums = [
                (spec, value)
                for spec, value in parameters
                if spec["key"] != "tempSel"
                and spec.get("kind") == "enum"
                and not is_toggle(spec)
                and not spec["key"].startswith("windDirection")
            ]
            toggles = [(spec, value) for spec, value in parameters if is_toggle(spec)]
            others = [
                (spec, value) for spec, value in parameters if spec["key"] != "tempSel" and spec.get("kind") != "enum"
            ]
            left = 24
            if temperature:
                spec, value = temperature
                rounded(c, 24, y, 156, y + 150, 18, fill=C.SURFACE, outline="")
                self.text(c, 36, y + 16, "Temperature", -11, C.MUTED, weight="bold")
                # One wheel for the sheet's lifetime, so a redraw keeps an in-progress drag.
                wheel = holder.get("wheel")
                if wheel is None or not wheel.winfo_exists():
                    wheel = SheetWheel(c, spec, values.get("tempSel", value), color)
                    holder["wheel"] = wheel
                    self.sheet["widgets"].append(wheel)
                    original = wheel.changed

                    def changed(wheel=wheel, original=original):
                        original()
                        values["tempSel"] = wheel.get()

                    wheel.changed = changed
                wheel.tone_color = color
                wheel.draw()
                c.create_window(36, y + 26, window=wheel, anchor="nw")
                left = 168
            ry = y
            for spec, value in enums:
                options = list(spec["options"].items())
                current = values.get(spec["key"], value)
                if len(options) <= 4:
                    box = 74
                    rounded(c, left, ry, width - 24, ry + box, 18, fill=C.SURFACE, outline="")
                    self.text(c, left + 12, ry + 16, spec["label"], -11, C.MUTED, weight="bold")
                    cell = (width - 24 - left - 24 - 4 * (len(options) - 1)) / len(options)
                    for index, (label, option) in enumerate(options):
                        x = left + 12 + index * (cell + 4)
                        on = equal(option, current)
                        fill = blend(color, C.SURFACE, 0.18) if on else C.SURFACE
                        rounded(c, x, ry + 30, x + cell, ry + 62, 9, fill=fill, outline="")
                        shown = tr(c, label)
                        while measure(c, shown, -12, "bold") > cell - 4 and len(shown) > 3:
                            shown = shown[:-2] + "."
                        self.text(
                            c,
                            x + cell / 2,
                            ry + 46,
                            shown,
                            -12,
                            color if on else C.MUTED,
                            "center",
                            "bold",
                            translate=False,
                        )
                        self.sheet_hit(
                            (x, ry + 30, x + cell, ry + 62), lambda key=spec["key"], option=option: pick(key, option)
                        )
                else:
                    box = 62
                    rounded(c, left, ry, width - 24, ry + box, 18, fill=C.SURFACE, outline="")
                    self.text(c, left + 12, ry + 20, spec["label"], -11, C.MUTED, weight="bold")
                    self.text(c, left + 12, ry + 42, option_label(spec, current), -14, weight="bold")
                    icon(c, "next", width - 40, ry + 31, C.MUTED, scale=0.6, bg=C.SURFACE)

                    def choose(spec=spec):
                        from ..control_choices import airflow_choices

                        choices = (
                            airflow_choices(spec)
                            if spec["key"].startswith("windDirection")
                            else [{"label": label, "value": option} for label, option in spec["options"].items()]
                        )
                        self.choice_panel = ChoicePanel(
                            self.window,
                            spec["label"],
                            choices,
                            values.get(spec["key"]),
                            lambda choice: pick(spec["key"], choice),
                        )

                    self.sheet_hit((left, ry, width - 24, ry + box), choose)
                ry += box + 10
            for spec, value in others:
                rounded(c, left, ry, width - 24, ry + 62, 18, fill=C.SURFACE, outline="")
                self.text(c, left + 12, ry + 20, spec["label"], -11, C.MUTED, weight="bold")
                self.text(c, left + 12, ry + 42, option_label(spec, values.get(spec["key"], value)), -14, weight="bold")
                ry += 72
            if temperature or enums or others:
                y = max(y + (160 if temperature else 0), ry)
            for spec, value in airflows:
                section_label(c, 24, y + 6, spec["label"])
                y += 22
                options = list(spec["options"].items())
                columns = min(6, len(options))
                cell = (width - 48 - 8 * (columns - 1)) / columns
                current = values.get(spec["key"], value)
                for index, (label, option) in enumerate(options):
                    x = 24 + (index % columns) * (cell + 8)
                    top = y + (index // columns) * 96
                    on = equal(option, current)
                    fill = self.app.soft(color) if on else C.SURFACE
                    rounded(c, x, top, x + cell, top + 88, 14, fill=fill, outline=color if on else fill, width=2)
                    louver(
                        c,
                        x + cell / 2 - 25,
                        top + 6,
                        louver_position(label),
                        C.TEXT,
                        color if on else C.FAINT,
                        scale=0.7,
                    )
                    shown = tr(c, label) if not label.startswith("Position ") else label[-1]
                    self.text(
                        c,
                        x + cell / 2,
                        top + 72,
                        shown,
                        -12,
                        color if on else C.TEXT,
                        "center",
                        "bold",
                        translate=False,
                    )
                    self.sheet_hit(
                        (x, top, x + cell, top + 88), lambda key=spec["key"], option=option: pick(key, option)
                    )
                y += ((len(options) + columns - 1) // columns) * 96 + 8
            if toggles:
                section_label(c, 24, y + 6, "Features")
                y += 22
                cell = (width - 48 - 16) / 3
                for index, (spec, value) in enumerate(toggles):
                    x = 24 + (index % 3) * (cell + 8)
                    top = y + (index // 3) * 58
                    on = code(values.get(spec["key"], value)) == "1"
                    fill = blend(color, C.CARD, 0.10) if on else C.SURFACE
                    rounded(
                        c,
                        x,
                        top,
                        x + cell,
                        top + 50,
                        14,
                        fill=fill,
                        outline=blend(color, C.BG, 0.45) if on else fill,
                        width=1.5,
                    )
                    symbol = FEATURES.get(spec["key"], (glyph_for(spec["label"]),))[0]
                    icon(c, symbol, x + 20, top + 25, color if on else C.MUTED, scale=0.55, bg=fill)
                    name = tr(c, spec["label"])
                    while measure(c, name, -12, "black") > cell - 46 and len(name) > 3:
                        name = name[:-2] + "…"
                    self.text(c, x + 36, top + 17, name, -12, weight="black", translate=False)
                    self.text(c, x + 36, top + 34, "On" if on else "Off", -11, color if on else C.MUTED, weight="black")
                    self.sheet_hit(
                        (x, top, x + cell, top + 50), lambda key=spec["key"], on=on: pick(key, "0" if on else "1")
                    )
                y += ((len(toggles) + 2) // 3) * 58 + 6
            if item["kind"] == "night":
                fill = blend(color, C.CARD, 0.10)
                rounded(c, 24, y, width - 24, y + 44, 14, fill=fill, outline="")
                icon(c, "moon", 46, y + 22, color, scale=0.55, bg=fill)
                self.text(c, 64, y + 22, "Sleep is on for this preset.", -12, color, weight="bold")
                y += 54
            warn = (
                "This routine may interrupt the current operation."
                if maintenance
                else "Starting this preset may turn the AC on and replace its current settings."
            )
            rounded(c, 24, y, width - 24, y + 48, 14, fill=C.WARN_BG, outline="")
            icon(c, "alert", 46, y + 24, C.WARN_TEXT, scale=0.55, bg=C.WARN_BG)
            self.text(c, 64, y + 24, warn, -12, C.WARN_TEXT, weight="semibold", width=width - 100)
            y += 48 + 18
            primary = (
                "Start maintenance routine"
                if maintenance
                else "Start preset"
                if item["kind"] == "night" or item.get("command") == "startProgram"
                else "Run function"
            )
            if maintenance:
                return self.sheet_buttons(
                    c, y, width, "Back to cards", primary, lambda: self.run_preset(item, values), 1.4
                )
            return self.preset_buttons(c, y, width, primary, item, values, color)

        self.open_sheet(draw)
        self.selected_function = item
        self.search_entry.configure(state="disabled")

    def preset_buttons(self, c, y, width, primary, item, values, color):
        """Back, Save (keep these values for next time) and Start."""
        gap = 8
        widths = (width - 48 - 2 * gap) * 0.28, (width - 48 - 2 * gap) * 0.28
        x = 24
        for label, action, fill, ink, outline in (
            ("Back", self.close_sheet, C.CARD, C.TEXT, C.STRONG),
            ("Save", lambda: self.save_preset(item, values), self.app.soft(color), color, color),
        ):
            w = widths[0]
            rounded(c, x, y, x + w, y + 50, 14, fill=fill, outline=outline, width=1.2)
            self.text(c, x + w / 2, y + 25, label, -14, ink, "center", "black")
            self.sheet_hit((x, y, x + w, y + 50), action)
            x += w + gap
        rounded(c, x, y, width - 24, y + 50, 14, fill=color, outline="")
        self.text(c, (x + width - 24) / 2, y + 25, primary, -14, C.ON_BRAND, "center", "black")
        self.sheet_hit((x, y, width - 24, y + 50), lambda: self.run_preset(item, values))
        return y + 50 + 28

    def save_preset(self, item, values):
        """Keep a preset's values for next time without starting it."""
        from ..program_memory import mode_key, normalized

        selected = self.app.selected
        chosen = {key: normalized(value) for key, value in values.items() if value is not None}
        if item["kind"] == "night":
            stored = {**self.app.memory.mode_values(selected, dict(item["changes"])), **chosen}
            stored.update({key: normalized(value) for key, value in item["changes"].items()})
            self.app.memory.save(selected["id"], mode_key(selected, item["changes"]), stored)
        else:
            self.app.memory.remember_function(selected["id"], item["command"], item["form"]["category"], chosen)
        failed = self.app.memory.save_error
        self.app.status.set(
            "Preset settings could not be saved on this computer." if failed else "Preset settings saved."
        )
        self.close_sheet()
        self.render(keep_scroll=True)

    def run_preset(self, item, values):
        action, request = preset_request(self.app, item, values)
        self.close()
        self.app.action(action, request)

    # Kept for callers of the earlier card view.
    configure_function = open_preset
