"""The Everyday use tab: presets, the chosen top presets and the preset sheet."""

from ..choice_widgets import ChoicePanel
from ..control_choices import mode_icon
from ..controller import code
from ..i18n import tr, translator
from ..secure_state import TOP_PRESET_LIMIT
from ..smooth import aa_line, aa_oval
from ..theme import C, accent, blend, icon, measure, rounded
from ..widgets import louver, section_label
from .model import (
    FEATURES,
    GRID_TILES,
    HIDDEN_IN_GRID,
    PRESET_DEFAULTS,
    WIDTH,
    everyday_layout,
    glyph_for,
    is_toggle,
    louver_position,
    option_label,
    preset_key,
    section_items,
    toggle_top_preset,
)
from .sheets import (
    SheetWheel,
)


class EverydayTabMixin:
    # Everyday use

    def preset_details(self, item):
        """Colour, glyph, description and the settings a preset applies, as (label, value, glyph, on)."""
        selected = self.app.selected
        controls = selected.get("controls", {})
        features = []
        if item["kind"] == "night":
            mode = item["label"].replace(" Night", "")
            values = {
                **PRESET_DEFAULTS.get(preset_key(item), {}),
                **self.app.memory.mode_values(selected, dict(item["changes"])),
            }
            color = accent(mode)
            features.append(("Mode", mode, mode_icon(mode), True))
            temperature = values.get("tempSel", selected.get("target"))
            if temperature is not None:
                features.append(("Temperature", option_label({"key": "tempSel"}, temperature), "thermo", True))
            for key, label, glyph in (("windSpeed", "Fan speed", "fan"), ("windDirectionVertical", "Airflow", "swing")):
                if key in controls:
                    value = values.get(key, self.app.current(key))
                    features.append((label, option_label(controls[key], value), glyph, True))
            features.append(("Sleep", "On", "moon", True))
            for key in ("muteStatus", "ecoMode"):
                if key in values and key in controls:
                    on = code(values[key]) == "1"
                    features.append((controls[key]["label"], "On" if on else "Off", FEATURES[key][0], on))
            description = (
                "Cooling with the unit’s Sleep feature, for the night."
                if mode == "Cool"
                else "Heating with the unit’s Sleep feature, for the night."
            )
            return color, mode_icon(mode), description, features[:6]
        form = item["form"]
        saved = {
            **PRESET_DEFAULTS.get(preset_key(item), {}),
            **self.app.memory.function_values(selected["id"], item["command"], form),
        }
        color, glyph = C.BRAND, glyph_for(item["label"])
        for spec in form.get("parameters", []):
            key = spec["key"]
            if key in HIDDEN_IN_GRID:
                continue
            value = saved.get(key, spec.get("value"))
            label = option_label(spec, value)
            if key == "machMode":
                color, glyph = accent(label), mode_icon(label)
                features.insert(0, ("Mode", label, mode_icon(label), True))
            elif is_toggle(spec):
                on = code(value) == "1"
                features.append(
                    (spec["label"], "On" if on else "Off", FEATURES.get(key, (glyph_for(spec["label"]),))[0], on)
                )
            else:
                features.append(
                    (spec["label"], label, "thermo" if key == "tempSel" else glyph_for(spec["label"]), True)
                )
        # Target temperature always shows: if a long list would push it past the sixth tile, it takes that tile.
        temperature = next((index for index, feature in enumerate(features) if feature[2] == "thermo"), None)
        if temperature is not None and temperature >= GRID_TILES:
            features.insert(GRID_TILES - 1, features.pop(temperature))
        maintenance = item.get("section") == "maintenance" or form.get("group") == "maintenance"
        description = "Cleaning / service routine" if maintenance else "Everyday comfort preset"
        return color, glyph, description, features[:GRID_TILES]

    def draw_everyday(self, c, y):
        self.text(
            c, 4, y + 9, "Presets for normal use. Open one to review it, then start it.", -13, C.MUTED, width=WIDTH - 8
        )
        y += 32
        items, choices, primary, others = self.everyday_presets()
        self.visible_items = items
        # The presets the user chose (up to four) first, in their order; the rest go in More.
        if choices:
            y = self.draw_top_header(c, y, len(primary))
        for item in primary:
            y = self.draw_preset_card(c, y, item) + 10
        if choices and not primary:
            rounded(c, 0, y, WIDTH, y + 56, 18, fill=C.CARD, outline="")
            hint = tr(c, "No top presets. Choose up to {limit} to show them here.").format(
                limit=translator(c).number(TOP_PRESET_LIMIT)
            )
            self.text(c, 20, y + 28, hint, -13, C.MUTED, weight="semibold", width=WIDTH - 40, translate=False)
            self.hit((0, y, WIDTH, y + 56), self.open_top_presets)
            y += 56 + 10
        if others:
            y += 6
            section_label(c, 4, y + 7, "More")
            count = translator(c).number(len(others))
            chip = measure(c, count, -11, "black") + 16
            rounded(c, WIDTH - 48 - chip, y - 4, WIDTH - 48, y + 18, 9, fill=C.SURFACE, outline="")
            self.text(c, WIDTH - 48 - chip / 2, y + 7, count, -11, C.MUTED, "center", "black", translate=False)
            icon(c, "chevron", WIDTH - 28, y + 7, C.MUTED, scale=0.7, bg=C.BG, rotate=180 if self.more_open else 0)
            self.hit((0, y - 8, WIDTH, y + 22), self.toggle_more)
            y += 30
            if self.more_open:
                for item in others:
                    y = self.draw_preset_card(c, y, item) + 10
        if not items:
            self.text(c, WIDTH / 2, y + 30, "No presets are exposed by your AC.", -13, C.MUTED, "center")
            y += 60
        # What each mode restores when the AC is turned on in it.
        options = self.app.mode_options()
        if options:
            y += 6
            section_label(c, 4, y + 7, "Remembered per mode")
            self.text(c, 4, y + 26, "Turning on in a mode brings back what you last used in it.", -12, C.MUTED)
            y += 42
            width = (WIDTH - 20) / 3
            controls = self.app.selected.get("controls", {})
            for index, option in enumerate(options):
                bx, by = (index % 3) * (width + 10), y + (index // 3) * 110
                label = option["label"]
                color = accent(label)
                values = self.app.memory.mode_values(self.app.selected, dict(option["value"]))
                rounded(c, bx, by, bx + width, by + 100, 18, fill=C.CARD, outline="")
                icon(c, mode_icon(label), bx + 22, by + 22, color, scale=0.6, bg=C.CARD)
                self.text(c, bx + 36, by + 22, label, -12, color, weight="bold")
                temperature = option_label({"key": "tempSel"}, values["tempSel"]) if "tempSel" in values else "—"
                self.text(c, bx + 14, by + 56, translator(c).number(temperature), -30, weight="light", translate=False)
                parts = []
                if "windSpeed" in values and "windSpeed" in controls:
                    parts.append(tr(c, option_label(controls["windSpeed"], values["windSpeed"])))
                spec = self.app.airflow_spec()
                if spec and spec["key"] in values:
                    parts.append(tr(c, option_label(spec, values[spec["key"]])))
                detail = " · ".join(parts) or tr(c, "Not used yet")
                self.text(
                    c, bx + 14, by + 84, detail, -11, C.MUTED, weight="semibold", width=width - 20, translate=False
                )
            y += ((len(options) + 2) // 3) * 110
        return y

    def draw_preset_card(self, c, y, item):
        """A preset header, a settings toggle and, when open, the settings grid."""
        color, glyph, description, features = self.preset_details(item)
        expanded = item["label"] in self.expanded_presets
        toggle = y + 88
        rows = (len(features) + 2) // 3 if expanded else 0
        height = 128 + rows * 50 + 4 if expanded else 128
        tint = self.app.soft(color)
        rounded(c, 16, y + 16, 80, y + 80, 18, fill=tint, outline="")
        icon(c, glyph, 48, y + 48, color, scale=1.3, bg=tint)
        review = tr(c, "Review")
        chip = measure(c, review, -12, "black") + 30
        self.text(c, 94, y + 36, item["label"], -17, weight="black", width=WIDTH - 94 - chip - 28)
        self.text(c, 94, y + 60, description, -12, C.MUTED, width=WIDTH - 94 - chip - 28)
        rounded(c, WIDTH - 16 - chip, y + 31, WIDTH - 16, y + 65, 11, fill=tint, outline="")
        self.text(c, WIDTH - 16 - chip + 12, y + 48, review, -12, color, weight="black", translate=False)
        icon(c, "next", WIDTH - 28, y + 48, color, scale=0.5, bg=tint)
        aa_line(c, 16, toggle, WIDTH - 16, toggle, fill=C.TRACK)
        self.text(c, 16, toggle + 18, "Hide settings" if expanded else "Show settings", -13, weight="bold")
        icon(c, "chevron", WIDTH - 26, toggle + 18, C.MUTED, scale=0.7, rotate=180 if expanded else 0)
        if expanded:
            cell = (WIDTH - 32 - 12) / 3
            for index, (label, value, symbol, on) in enumerate(features):
                fx = 16 + (index % 3) * (cell + 6)
                fy = y + 128 + (index // 3) * 50
                rounded(c, fx, fy, fx + cell, fy + 44, 12, fill=C.SURFACE, outline="")
                square = self.app.soft(color, C.SURFACE) if on else C.STRONG
                rounded(c, fx + 10, fy + 9, fx + 36, fy + 35, 8, fill=square, outline="")
                icon(c, symbol, fx + 23, fy + 22, color if on else C.MUTED, scale=0.5, bg=square)
                caption = tr(c, label)
                while measure(c, caption, -11, "semibold") > cell - 50 and len(caption) > 3:
                    caption = caption[:-2] + "…"
                self.text(c, fx + 44, fy + 14, caption, -11, C.MUTED, weight="semibold", translate=False)
                shown = tr(c, value)
                while measure(c, shown, -13, "black") > cell - 50 and len(shown) > 3:
                    shown = shown[:-2] + "…"
                self.text(c, fx + 44, fy + 30, shown, -13, C.TEXT if on else C.MUTED, weight="black", translate=False)
        self.card(c, 0, y, WIDTH, y + height, 22)
        self.hit((0, y, WIDTH, y + 88), lambda item=item: self.open_preset(item))
        self.hit((0, toggle, WIDTH, toggle + 36), lambda item=item: self.toggle_preset(item))
        return y + height

    def toggle_preset(self, item):
        label = item["label"]
        if label in self.expanded_presets:
            self.expanded_presets.discard(label)
        else:
            self.expanded_presets.add(label)
        self.render(keep_scroll=True)

    def toggle_more(self):
        self.more_open = not self.more_open
        self.render(keep_scroll=True)

    def everyday_presets(self):
        """(items, choices, top, more) for the selected AC's Everyday use tab."""
        selected = self.app.selected
        items = [dict(item, section="everyday") for item in section_items(selected, "everyday")]
        modes = {preset_key(option) for option in self.app.mode_options()}
        return (items, *everyday_layout(items, modes, self.app.memory.top_presets(selected["id"])))

    def draw_top_header(self, c, y, count):
        """TOP PRESETS, how many of the four places are used, and a button to choose them."""
        number = translator(c).number
        section_label(c, 4, y + 7, "Top presets")
        used = tr(c, "{count} of {limit}").format(count=number(count), limit=number(TOP_PRESET_LIMIT))
        left = 4 + measure(c, tr(c, "Top presets").upper(), -11, "black") + 10
        self.text(c, left, y + 7, used, -11, C.MUTED, weight="semibold", translate=False)
        tone = self.tone()
        tint = self.app.soft(tone)
        caption = tr(c, "Choose up to {limit}").format(limit=number(TOP_PRESET_LIMIT))
        chip = measure(c, caption, -12, "black") + 42
        rounded(c, WIDTH - chip, y - 7, WIDTH, y + 21, 14, fill=tint, outline="")
        icon(c, "sliders", WIDTH - chip + 17, y + 7, tone, scale=0.5, bg=tint)
        self.text(c, WIDTH - chip + 30, y + 7, caption, -12, tone, weight="black", translate=False)
        self.hit((WIDTH - chip, y - 10, WIDTH, y + 24), self.open_top_presets)
        return y + 34

    def open_top_presets(self):
        """A sheet to pick up to four presets for the top of Everyday use; the rest go in More."""
        items, choices, top, more = self.everyday_presets()
        if not choices:
            return
        self.top_choice = [preset_key(item) for item in top]
        self.top_refused = False

        def choose(key):
            self.top_choice, self.top_refused = toggle_top_preset(self.top_choice, key)
            self.sheet["draw"]()

        def draw(c, width):
            number = translator(c).number
            tone = self.tone()
            full = len(self.top_choice) >= TOP_PRESET_LIMIT
            y = 30
            self.text(c, 24, y + 14, "Top presets", -22, weight="black")
            count = tr(c, "{count} of {limit} chosen").format(
                count=number(len(self.top_choice)), limit=number(TOP_PRESET_LIMIT)
            )
            chip = measure(c, count, -12, "black") + 28
            tint = self.app.soft(tone)
            rounded(c, width - 24 - chip, y + 1, width - 24, y + 27, 13, fill=tint, outline="")
            self.text(c, width - 24 - chip / 2, y + 14, count, -12, tone, "center", "black", translate=False)
            intro = tr(
                c, "Choose up to {limit} presets to show first, in the order you pick them. The rest go in More."
            ).format(limit=number(TOP_PRESET_LIMIT))
            self.text(c, 24, y + 38, intro, -13, C.MUTED, "nw", width=width - 48, translate=False)
            y += 92
            cell = (width - 48 - 10) / 2
            for index, item in enumerate(choices):
                key = preset_key(item)
                x, top_y = 24 + (index % 2) * (cell + 10), y + (index // 2) * 74
                color, glyph = self.preset_details(item)[:2]
                position = self.top_choice.index(key) + 1 if key in self.top_choice else 0
                blocked = full and not position
                fill = self.app.soft(color) if position else C.SURFACE
                rounded(
                    c, x, top_y, x + cell, top_y + 64, 16, fill=fill, outline=color if position else fill, width=1.5
                )
                rounded(c, x + 12, top_y + 14, x + 48, top_y + 50, 11, fill=C.CARD, outline="")
                icon(c, glyph, x + 30, top_y + 32, C.FAINT if blocked else color, scale=0.6, bg=C.CARD)
                self.text(
                    c,
                    x + 58,
                    top_y + 32,
                    item["label"],
                    -13,
                    C.FAINT if blocked else C.TEXT,
                    weight="bold",
                    width=cell - 58 - 44,
                )
                cx, cy = x + cell - 24, top_y + 32
                if position:
                    aa_oval(c, cx - 12, cy - 12, cx + 12, cy + 12, fill=color, outline="")
                    self.text(c, cx, cy, number(position), -12, C.ON_BRAND, "center", "black", translate=False)
                else:
                    aa_oval(
                        c,
                        cx - 11,
                        cy - 11,
                        cx + 11,
                        cy + 11,
                        fill="",
                        outline=C.TRACK if blocked else C.STRONG,
                        width=1.5,
                    )
                self.sheet_hit((x, top_y, x + cell, top_y + 64), lambda key=key: choose(key))
            y += ((len(choices) + 1) // 2) * 74 + 2
            # What a selection does; once the four places are taken, how to free one.
            background, ink = (C.WARN_BG, C.WARN_TEXT) if self.top_refused else (C.SURFACE, C.MUTED)
            note = (
                "All {limit} places are taken. Remove a chosen preset to add another."
                if full
                else "Select a preset to add it, or select it again to remove it."
            )
            rounded(c, 24, y, width - 24, y + 46, 14, fill=background, outline="")
            icon(c, "alert" if full else "check", 46, y + 23, ink, scale=0.5, bg=background)
            self.text(
                c,
                64,
                y + 23,
                tr(c, note).format(limit=number(TOP_PRESET_LIMIT)),
                -12,
                ink,
                weight="semibold",
                width=width - 100,
                translate=False,
            )
            y += 46 + 20
            return self.sheet_buttons(
                c, y, width, "Cancel", "Save", lambda: self.save_top_presets(list(self.top_choice))
            )

        self.open_sheet(draw)

    def save_top_presets(self, keys):
        self.app.memory.save_top_presets(self.app.selected["id"], keys)
        failed = self.app.memory.save_error
        self.app.status.set(
            "Top presets changed for this session, but could not be saved on this computer."
            if failed
            else "Top presets saved."
        )
        self.close_sheet()
        self.render(keep_scroll=True)

    # Sheets

    def open_preset(self, item):
        """Review a preset, Night mode or maintenance routine, then start it explicitly."""
        selected = self.app.selected
        controls = selected.get("controls", {})
        color, glyph, description, features = self.preset_details(item)
        maintenance = item.get("section") == "maintenance" or (
            item["kind"] == "function" and item["form"].get("group") == "maintenance"
        )
        # Editable parameters: (spec, initial value).
        if item["kind"] == "night":
            values = {
                **PRESET_DEFAULTS.get(preset_key(item), {}),
                **self.app.memory.mode_values(selected, dict(item["changes"])),
            }
            parameters = [
                (controls[key], values.get(key, self.app.current(key)))
                for key in ("tempSel", "windSpeed", "windDirectionVertical", "muteStatus", "ecoMode")
                if key in controls
            ]
        else:
            saved = {
                **PRESET_DEFAULTS.get(preset_key(item), {}),
                **self.app.memory.function_values(selected["id"], item["command"], item["form"]),
            }
            parameters = [
                (spec, saved.get(spec["key"], spec.get("value")))
                for spec in item["form"].get("parameters", [])
                if spec["key"] != "machMode"
            ]
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

    # Kept for callers of the earlier card view.
    configure_function = open_preset

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
        values = {key: value for key, value in values.items() if value is not None}
        if item["kind"] == "night":
            request = dict(self.app.memory.mode_values(self.app.selected, dict(item["changes"])))
            request.update(values)
            request.update(item["changes"])
            self.close()
            self.app.action("on", request)
            return
        request = {"command": item["command"], "category": item["form"]["category"], "parameters": values}
        self.close()
        self.app.action("execute", request)
