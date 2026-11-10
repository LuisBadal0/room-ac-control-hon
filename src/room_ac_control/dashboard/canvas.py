"""Drawing the dashboard canvas: glow, status chip, readings, dial, modes, tiles and alerts."""

import math

from ..control_choices import mode_icon
from ..controller import code, mode_choices
from ..i18n import (
    tr,
)
from ..inline_timers import EndAtCard
from ..smooth import aa_arc, aa_line, aa_oval, aa_text, pil_font
from ..theme import (
    C,
    accent,
    blend,
    font,
    icon,
    measure,
    rounded,
)
from ..widgets import fan_bars
from .layout import (
    AIR_COLORS,
    ALERTS,
    BANNER,
    CANVAS_HEIGHT,
    CHIP,
    DIAL,
    DIAL_START,
    DIAL_SWEEP,
    DIAL_TOP,
    FAN_LEVELS,
    FLOW,
    MODES_HEIGHT,
    MODES_TOP,
    READINGS_HEIGHT,
    READINGS_TOP,
    TILE_HEIGHT,
    TILE_TOP,
    TIMER_TOP,
    UNIT,
    VERBS,
    WIDTH,
)


class CanvasMixin:
    def base_mode(self):
        """The displayed mode without its Night (Sleep) suffix, such as "Cool"."""
        return self.mode.get().replace(" Night", "")

    def settings_accent(self):
        """The selected mode's colour, kept while the AC is off; the brand blue before sign-in."""
        return accent(self.base_mode()) if self.selected else C.BRAND

    def dial_accent(self):
        if not self.selected:
            return C.BRAND
        return accent("off") if self.selected["power"] != "On" else accent(self.base_mode())

    def soft(self, color, base=None):
        """The mockup's accent tint: the colour at about 14% over a surface."""
        return blend(color, base or C.CARD, 0.14 if C.mode == "dark" else 0.10)

    def mode_options(self):
        """Standard modes for the mode bar; Night variants are Sleep on the Sleep tile."""
        return [option for option in mode_choices(self.selected) if not option["label"].endswith(" Night")]

    def draw(self):
        if not self.selected:
            return
        c = self.canvas
        c.delete("all")
        c.configure(bg=C.BG)
        self.hits = []
        width = max(c.winfo_width(), 480)
        s = width / WIDTH
        # Controls light up under the pointer only while the AC is on.
        self.canvas_hover.reset(s, enabled=not self.busy and self.ac_on())
        tone = self.dial_accent()
        text = lambda x, y, t, size=-13, color=None, anchor="w", weight="normal", translate=True: aa_text(
            c, x, y, text=tr(c, t) if translate else t, fill=color or C.TEXT, anchor=anchor, font=font(size, weight)
        )
        hit = lambda box, fn: self.hits.append((box, fn))
        self.draw_glow(c, tone)
        # The unit, its live airflow and the status chip; an alert banner covers the airflow.
        c.create_image(WIDTH / 2, UNIT[1], image=self.unit_image, anchor="n")
        if not self.draw_alert(c, text):
            self.draw_chip(c, text, tone)
        self.draw_readings(c, text, hit)
        self.draw_dial(c, text, hit, tone)
        self.draw_modes(c, text, hit)
        self.draw_tiles(c, text, hit)
        self.inline_timers.refresh(self.selected, self.busy)
        timer_row = c.create_window(
            0, TIMER_TOP, window=self.inline_timers, anchor="nw", width=WIDTH, height=EndAtCard.HEIGHT
        )
        c.itemconfigure(timer_row, tags="inline-timers")
        if s != 1:
            c.scale("all", 0, 0, s, s)
        # Canvas scaling also changes embedded window dimensions. Apply its final
        # width once, while preserving the native wheels' full height.
        c.itemconfigure(timer_row, width=round(WIDTH * s), height=EndAtCard.HEIGHT)
        self.canvas.configure(height=int(CANVAS_HEIGHT * s))
        flowing = self.selected if not c.find_withtag("alert") else None
        self.airflow.set_state(flowing, WIDTH / 2, FLOW[0], FLOW[1], FLOW[2], s)
        self.canvas_hover.update()
        self.apply_button.draw()
        if self.busy:
            self.hits = []

    def draw_glow(self, c, tone):
        """A soft accent glow around the dial, like the mockup's blurred shadow."""
        if self.selected["power"] != "On":
            return
        key = (tone, C.BG)
        if getattr(self, "glow_key", None) != key:
            from PIL import Image, ImageDraw, ImageTk

            size, inner = 420, 95
            strength = 0.22 if C.mode == "dark" else 0.19
            mask = Image.new("L", (size, size), 0)
            draw = ImageDraw.Draw(mask)
            centre = size / 2
            for d in range(int(centre), inner - 1, -1):
                a = strength * (1 if d < inner + 18 else math.exp(-(((d - inner - 18) / 45) ** 2)))
                draw.ellipse((centre - d, centre - d, centre + d, centre + d), fill=round(255 * a))
            draw.ellipse((centre - inner, centre - inner, centre + inner, centre + inner), fill=0)
            image = Image.composite(Image.new("RGB", (size, size), tone), Image.new("RGB", (size, size), C.BG), mask)
            self.glow_image = ImageTk.PhotoImage(image, master=c)
            self.glow_key = key
        c.create_image(DIAL[0], DIAL[1], image=self.glow_image)

    def draw_chip(self, c, text, tone):
        if self.pending_changes and not self.dirty:
            label = "Awaiting confirmation"
        elif self.selected["power"] == "On":
            label = tr(c, self.base_mode()) + " · " + tr(c, "running")
        else:
            label = "Standby"
        label = tr(c, label)
        on = self.selected["power"] == "On"
        fill, ink = (self.soft(tone, C.BG), tone) if on else (C.CARD, C.MUTED)
        # The chip sits beside the unit, so a long label drops the mode name.
        if measure(c, label, -11, "bold") + 36 > 112 and self.selected["power"] == "On" and not self.pending_changes:
            label = tr(c, "running").capitalize()
        width = measure(c, label, -11, "bold") + 36
        rounded(c, 0, CHIP[0], width, CHIP[1], 13, fill=fill, outline="")
        middle = (CHIP[0] + CHIP[1]) / 2
        aa_oval(c, 10, middle - 3, 16, middle + 3, fill=ink, outline="")
        text(22, middle, label, -11, ink, weight="bold", translate=False)

    def draw_readings(self, c, text, hit):
        """Room, outside, humidity and air quality, as one row of chips.

        A cloud marks a value from the weather at the AC's location rather than the AC's
        own sensor; selecting such a chip opens the Outside sheet with every weather value."""
        from ..weather import readings

        found = readings(self.selected)
        number = lambda value, places: self.i18n.number(f"{float(value):.{places}f}") + "°"
        try:
            room = number(self.selected["room"], 1)
        except (TypeError, ValueError):
            room = "—"
        outside, humidity, quality = found.get("outdoor"), found.get("humidity"), found.get("air")
        chips = [
            ("Room", room, None, None),
            ("Outside", number(outside[0], 0) if outside else "—", None, outside),
            ("Humidity", f"{float(humidity[0]):.0f}%" if humidity else "—", None, humidity),
            (
                "Air quality",
                tr(c, quality[0]) if quality else "—",
                getattr(C, AIR_COLORS.get(quality[0], "MUTED")) if quality else None,
                quality,
            ),
        ]
        gap = 8
        width = (WIDTH - gap * (len(chips) - 1)) / len(chips)
        top = READINGS_TOP
        weather = bool(self.selected.get("weather"))
        for index, (label, value, dot, source) in enumerate(chips):
            x = index * (width + gap)
            card = rounded(c, x, top, x + width, top + READINGS_HEIGHT, 14, fill=C.CARD, outline="")
            items = [card]
            from_weather = source is not None and source[1] == "weather"
            room_for_caption = width - 24 - (16 if from_weather else 0)
            caption = tr(c, label)
            while measure(c, caption, -11, "semibold") > room_for_caption and len(caption) > 3:
                caption = caption[:-2] + "…"
            items.append(text(x + 12, top + 19, caption, -11, C.MUTED, weight="semibold", translate=False))
            if from_weather:
                items.append(icon(c, "cloud", x + width - 17, top + 19, C.MUTED, scale=0.42, bg=C.CARD))
            value_x = x + 12
            if dot:
                items.append(aa_oval(c, x + 12, top + 36, x + 20, top + 44, fill=dot, outline=""))
                value_x += 14
            items.append(text(value_x, top + 40, value, -17, weight="bold", translate=False))
            for item in items:
                c.addtag_withtag("reading", item)
            if weather and index:
                box = (x, top, x + width, top + READINGS_HEIGHT)
                self.canvas_hover.add(box, card, {"fill": C.CARD}, {"fill": C.HOVER})
                hit(box, self.open_outside_sheet)

    def draw_dial(self, c, text, hit, tone):
        """A 270° ring: drag along it, click it, scroll on it or use −/+."""
        cx, cy, r = DIAL
        top = DIAL_TOP
        values = [float(v) for v in self.selected.get("temperatures", [])]
        try:
            current = float(self.temp.get())
        except ValueError:
            current = None
        low, high = (min(values), max(values)) if values else (16, 32)
        ratio = 0 if current is None or high == low else max(0, min(1, (current - low) / (high - low)))
        point = lambda angle, radius: (
            cx + radius * math.cos(math.radians(angle)),
            cy + radius * math.sin(math.radians(angle)),
        )
        for index in range(17):
            angle = DIAL_START + DIAL_SWEEP * index / 16
            aa_line(
                c,
                *point(angle, 135 if index % 4 == 0 else 139),
                *point(angle, 145),
                fill=C.FAINT,
                width=2,
                capstyle="round",
            )
        box = (cx - r, cy - r, cx + r, cy + r)
        aa_arc(c, *box, start=-45, extent=270, style="arc", outline=C.TRACK, width=14)
        cap = lambda angle, color: aa_oval(
            c,
            point(angle, r)[0] - 7,
            point(angle, r)[1] - 7,
            point(angle, r)[0] + 7,
            point(angle, r)[1] + 7,
            fill=color,
            outline="",
        )
        cap(DIAL_START + DIAL_SWEEP, C.TRACK)
        cap(DIAL_START, tone if values and current is not None else C.TRACK)
        if values and current is not None:
            if ratio > 0:
                aa_arc(c, *box, start=225, extent=-DIAL_SWEEP * ratio, style="arc", outline=tone, width=14)
            tx, ty = point(DIAL_START + DIAL_SWEEP * ratio, r)
            halo = blend(tone, C.BG, 0.28 if self.dial_drag else 0.14)
            aa_oval(c, tx - 22, ty - 22, tx + 22, ty + 22, fill=halo, outline="", tags="dial-halo")
            aa_oval(c, tx - 14, ty - 14, tx + 14, ty + 14, fill=C.BG, outline=tone, width=4, tags="dial-thumb")
            aa_oval(c, tx - 4, ty - 4, tx + 4, ty + 4, fill=tone, outline="")
            self.canvas_hover.add(
                (tx - 24, ty - 24, tx + 24, ty + 24),
                c.find_withtag("dial-halo")[0],
                {"fill": halo},
                {"fill": blend(tone, C.BG, 0.28)},
            )
        text(cx - 80, top + 262, self.i18n.number(f"{low:g}°"), -12, C.MUTED, "center", "semibold", translate=False)
        text(cx + 80, top + 262, self.i18n.number(f"{high:g}°"), -12, C.MUTED, "center", "semibold", translate=False)
        # Centre: what the AC is doing above the target. The digits are centred on the
        # ring by their drawn outline, with °C hanging off their top right.
        verb = "Off" if self.selected["power"] != "On" else VERBS.get(self.base_mode(), "Target temperature")
        value = "—" if current is None else self.i18n.number(f"{current:g}")
        size = 96
        face, unit_face = pil_font(c, font(-size, "light")), pil_font(c, font(-26, "normal"))
        middle = cy + 6
        if face is not None and unit_face is not None:
            # Whole degrees keep the mockup's 96 px; wider values such as 25,5 shrink to stay in the ring.
            unit_width = unit_face.getlength("°C")
            room = 2 * (r - 24)
            left, top_edge, right, bottom = face.getbbox(value)
            while size > 56 and (right - left) + 6 + unit_width > room:
                size -= 4
                face = pil_font(c, font(-size, "light"))
                left, top_edge, right, bottom = face.getbbox(value)
            x, y = cx - (left + right) / 2, middle - (top_edge + bottom) / 2
            # Keep °C inside the ring: shift the pair left only as far as needed.
            x -= max(0, x + right + 6 + unit_width - (cx + room / 2))
            number = text(x, y, value, -size, anchor="nw", weight="light", translate=False)
            unit_top = unit_face.getbbox("°C")[1]
            unit = text(x + right + 6, y + top_edge - unit_top, "°C", -26, C.MUTED, "nw", translate=False)
            digits_top = y + top_edge
        else:
            number = text(cx, middle, value, -96, anchor="center", weight="light", translate=False)
            box = c.bbox(number)
            unit = text(box[2] + 4, box[1] + 14, "°C", -26, C.MUTED, "nw", translate=False)
            digits_top = box[1] + 14
        c.itemconfigure(number, tags="target-temperature")
        c.itemconfigure(unit, tags="temperature-unit")
        text(cx, digits_top - 26, tr(c, verb).upper(), -12, tone, "center", "black", translate=False)
        # −/+ beside the ring's open end.
        for x, direction in ((48, -1), (WIDTH - 48, 1)):
            y = top + 222
            step = aa_oval(c, x - 26, y - 26, x + 26, y + 26, fill=C.CARD, outline="")
            mark = C.TEXT if values else C.FAINT
            aa_line(c, x - 8, y, x + 8, y, fill=mark, width=2.4, capstyle="round")
            if direction > 0:
                aa_line(c, x, y - 8, x, y + 8, fill=mark, width=2.4, capstyle="round")
            if values:
                self.canvas_hover.add((x - 26, y - 26, x + 26, y + 26), step, {"fill": C.CARD}, {"fill": C.HOVER})
                hit((x - 26, y - 26, x + 26, y + 26), lambda direction=direction: self.step_temp(direction))
        # Eco sits in the ring's opening.
        eco = self.selected.get("controls", {}).get("ecoMode")
        if eco:
            active = code(self.current("ecoMode")) == "1"
            label = tr(c, "Eco")
            width = measure(c, label, -12, "bold") + 44
            x1, x2, y1, y2 = cx - width / 2, cx + width / 2, top + 248, top + 280
            fill = self.soft(tone, C.BG) if active else C.BG
            ink = tone if active else C.MUTED
            chip = rounded(c, x1, y1, x2, y2, 16, fill=fill, outline=tone if active else C.TRACK, width=1.2)
            icon(c, "leaf", x1 + 18, (y1 + y2) / 2, ink, scale=0.55, bg=fill)
            text(x1 + 30, (y1 + y2) / 2, label, -12, ink, weight="bold", translate=False)
            self.canvas_hover.add((x1, y1, x2, y2), chip, {"outline": tone if active else C.TRACK}, {"outline": tone})
            hit((x1, y1, x2, y2), lambda: self.staged("ecoMode", "0" if active else "1"))

    def draw_modes(self, c, text, hit):
        """One button per standard mode; the selected one takes its own accent."""
        options = self.mode_options()
        top, bottom = MODES_TOP, MODES_TOP + MODES_HEIGHT
        rounded(c, 0, top, WIDTH, bottom, 18, fill=C.CARD, outline="")
        if not options:
            text(WIDTH / 2, (top + bottom) / 2, "Mode · Unavailable", -13, C.MUTED, "center")
            return
        gap = 4
        width = (WIDTH - 8 - gap * (len(options) - 1)) / len(options)
        selected = self.base_mode()
        for index, option in enumerate(options):
            x = 4 + index * (width + gap)
            label = option["label"]
            on = label == selected
            color = accent(label)
            fill = self.soft(color) if on else C.CARD
            segment = rounded(c, x, top + 4, x + width, bottom - 4, 14, fill=fill, outline="")
            if not on:
                self.canvas_hover.add((x, top + 4, x + width, bottom - 4), segment, {"fill": C.CARD}, {"fill": C.HOVER})
            ink = color if on else C.MUTED
            icon(c, mode_icon(label), x + width / 2, top + 21, ink, scale=0.72, bg=fill)
            caption = tr(c, label)
            size = -12 if measure(c, caption, -12, "bold") <= width - 6 else -10
            text(x + width / 2, top + 42, caption, size, ink, "center", "bold", translate=False)
            hit((x, top, x + width, bottom), lambda option=option: self.pick_mode(option))

    def draw_tiles(self, c, text, hit):
        controls = self.selected.get("controls", {})
        fan = self.fan.get() if "windSpeed" in controls else "Unavailable"
        tiles = [
            ("Fan speed", fan, "bars", self.cycle_fan),
            ("Airflow", self.airflow_value(), "swing", self.open_airflow_sheet),
            ("Sleep", self.toggle_label("silentSleepStatus"), "moon", self.toggle_sleep),
        ]
        gap = 8
        width = (WIDTH - gap * 2) / 3
        top, bottom = TILE_TOP, TILE_TOP + TILE_HEIGHT
        tone = self.dial_accent()
        for index, (label, value, glyph, command) in enumerate(tiles):
            x = index * (width + gap)
            card = rounded(c, x, top, x + width, bottom, 16, fill=C.CARD, outline="")
            text(x + 14, top + 19, label, -11, C.MUTED, weight="semibold")
            if glyph == "bars":
                fan_bars(
                    c, x + width - 14 - 18, top + 26, FAN_LEVELS.get(value, 0) if value != "Auto" else 0, tone, C.CARD
                )
            else:
                icon(c, glyph, x + width - 21, top + 19, C.MUTED, scale=0.5, bg=C.CARD)
            text(
                x + 14,
                top + 49,
                value,
                -16,
                C.TEXT if value not in {"Unavailable", "Unknown"} else C.MUTED,
                weight="bold",
            )
            if value != "Unavailable":
                self.canvas_hover.add((x, top, x + width, bottom), card, {"fill": C.CARD}, {"fill": C.HOVER})
                hit((x, top, x + width, bottom), command)

    def draw_alert(self, c, text):
        """A banner for an error, defrosting or filter cleaning; it clears with the condition."""
        alerts = [alert for alert in self.selected.get("alerts", []) if alert.get("kind") in ALERTS]
        if not alerts:
            return False
        alert = alerts[0]
        glyph, surface, ink, title, detail = ALERTS[alert["kind"]]
        fill, color = getattr(C, surface), getattr(C, ink)
        x1, y1, x2, y2 = BANNER
        items = [rounded(c, x1, y1, x2, y2, 12, fill=fill, outline="")]
        icon(c, glyph, 20, (y1 + y2) / 2, color, scale=0.62, bg=fill, tags=("alert",))
        items.append(text(38, y1 + 10, title.format(code=alert.get("code", "")), -12, color, weight="bold"))
        items.append(text(38, y1 + 24, detail, -11, color))
        if len(alerts) > 1:
            items.append(text(x2 - 12, (y1 + y2) / 2, f"+{len(alerts) - 1}", -12, color, "e", "bold", translate=False))
        for item in items:
            c.addtag_withtag("alert", item)
        return True
