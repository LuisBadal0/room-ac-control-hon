"""All functions, as in the Ambient mockup: Settings, Everyday use, Maintenance and Schedules.

Choices made here are staged on the dashboard, so Apply (here or there) sends them together."""
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox

from .i18n import tr, localized_title, refresh_on_language, translator, search_text
from .controller import function_group, mode_choices, code
from .choice_widgets import ChoicePanel
from .control_choices import mode_icon
from .routine_history import item_routine, last_run_text
from .schedules import clock_text, day_labels, DAY_NAMES
from .secure_state import TOP_PRESET_LIMIT
from .temperature_wheel import TemperatureWheel
from .theme import C, font, measure, paint, icon, rounded, blend, accent, unit_photo, refresh_on_theme
from .widgets import PillButton, Overlay, raise_widget, section_label, switch, fan_bars, louver
from .smooth import aa_line, aa_oval, restyle, aa_text

SECTIONS = (("settings", "Settings"), ("everyday", "Everyday use"), ("maintenance", "Maintenance"))
TABS = SECTIONS + (("schedules", "Schedules"),)
SECTION_GLYPHS = {"settings": "sliders", "everyday": "sparkle", "maintenance": "wrench", "schedules": "clock"}
SIZE = (540, 920)
WIDTH = 500
NEUTRAL = {"Off", "Unknown", "Unavailable"}
# The everyday presets shown ahead of the "More" section until the user picks their own
# (at most TOP_PRESET_LIMIT).
PRESETS_UP_FRONT = ("cool", "coolnight", "heat", "heatnight")
# A preset card's settings grid shows this many tiles. 10°C heating is a separate preset,
# not a setting of Heat, so Heat presets show their target temperature there instead, like Cool.
GRID_TILES = 6
HIDDEN_IN_GRID = {"10degreeHeatingStatus"}
# Maintenance cards: height plus the gap below.
ROUTINE_STEP = 236
# Starting values for presets that have not been saved yet.
PRESET_DEFAULTS = {"heat": {"tempSel": "24"}, "heatnight": {"tempSel": "24", "muteStatus": "1"}}


def preset_key(item):
    return item["label"].lower().replace(" ", "")


def everyday_layout(items, modes, chosen=None):
    """Split Everyday use presets into (choices, top, more), each preset once.

    `chosen` lists the preset keys picked to show first, in order (None: the defaults).
    Presets that only repeat a mode from the mode bar (Auto, Dry, Fan, a second Cool…)
    are left out, except the default top presets; whatever is not on top goes in More."""
    repeats = set(modes) | {mode+"night" for mode in modes}
    choices, seen = [], set()
    for item in items:
        key = preset_key(item)
        if key not in seen and (key in PRESETS_UP_FRONT or key not in repeats):
            seen.add(key)
            choices.append(item)
    rank = {key: index for index, key in enumerate(PRESETS_UP_FRONT)}
    choices.sort(key=lambda item: rank.get(preset_key(item), len(rank)))
    by_key = {preset_key(item): item for item in choices}
    picked = PRESETS_UP_FRONT if chosen is None else chosen
    top = [by_key[key] for key in dict.fromkeys(picked) if key in by_key][:TOP_PRESET_LIMIT]
    on_top = {preset_key(item) for item in top}
    return choices, top, [item for item in choices if preset_key(item) not in on_top]


def toggle_top_preset(chosen, key):
    """Add or remove one top preset: (new choice, refused). Adding a fifth is refused."""
    if key in chosen:
        return [other for other in chosen if other != key], False
    if len(chosen) >= TOP_PRESET_LIMIT:
        return list(chosen), True
    return [*chosen, key], False
# Shown in the Comfort card rather than as feature tiles or extra rows.
COMFORT = {"machMode", "windSpeed", "windDirectionVertical", "windDirectionHorizontal", "tempSel", "onOffStatus"}
# Feature tiles: glyph, the accent they take, and a short explanation.
FEATURES = {
    "ecoMode": ("leaf", "dry", "Limits power use"),
    "muteStatus": ("speaker", "fan", "Quieter, slower to reach temperature"),
    "silentSleepStatus": ("moon", "cool", "Eases the temperature through the night"),
    "echoStatus": ("bell", "heat", "Beeps when the AC gets a command"),
}
FEATURE_ORDER = ("ecoMode", "muteStatus", "silentSleepStatus", "echoStatus")
AIRFLOW_NOTES = {"Swing": "Louver moves up and down", "Position 1": "Most closed", "Position 2": "Slightly open",
                 "Position 3": "Half open", "Position 4": "Mostly open", "Position 5": "Most open"}
FAN_LEVELS = {"Low": 1, "Medium": 2, "High": 3}


def matches_search(item, query):
    """Match words in names, descriptions and user-facing adjustable options."""
    parts = [item["label"], item.get("description", ""), item.get("command_label", "")]
    specs = [item["spec"]] if item["kind"] == "setting" else item.get("form", {}).get("parameters", [])
    for spec in specs:
        parts.append(spec["label"])
        parts.extend(spec.get("options", {}))
    text = search_text(parts)
    return all(word in text for word in search_text([query]).split())


def section_items(device, section):
    items = []
    if section in {"settings", "maintenance"}:
        for key, spec in device.get("controls", {}).items():
            if key == "onOffStatus":
                continue
            group = function_group(key, label=spec["label"])
            if (section == "maintenance") != (group == "maintenance"):
                continue
            items.append({"kind": "setting", "key": key, "label": spec["label"], "spec": spec,
                          "description": spec.get("description", "")})
    if section in {"everyday", "maintenance"}:
        for command, entry in device.get("commands", {}).items():
            for form in entry["forms"]:
                group = form.get("group", function_group(command, form["category"], form["label"]))
                if group != section:
                    continue
                items.append({"kind": "function", "command": command, "form": form,
                              "label": form["label"], "command_label": entry["label"]})
    if section == "everyday":
        existing = {item["label"].lower().replace(" ", "") for item in items}
        for option in mode_choices(device):
            if option["label"].endswith(" Night") and option["label"].lower().replace(" ", "") not in existing:
                items.append({"kind": "night", "label": option["label"], "changes": option["value"], "description": option["description"]})
    return items


def glyph_for(name):
    name = name.lower()
    if name in {"auto", "cool", "dry", "heat", "fan", "cool night", "heat night"}: return mode_icon(name)
    if "fan" in name: return "fan"
    if "airflow" in name or "wind" in name: return "swing"
    if "sleep" in name or "night" in name: return "moon"
    if "quiet" in name or "silent" in name or "mute" in name: return "speaker"
    if "buzzer" in name or "echo" in name: return "bell"
    if "eco" in name or "health" in name: return "leaf"
    if "clean" in name or "steril" in name: return "sparkle"
    if "temperature" in name: return "thermo"
    if "cool" in name or "mode" in name or "temp" in name: return "snow"
    return "sliders"


def is_toggle(spec):
    return spec.get("kind") == "enum" and len(spec.get("options", {})) == 2 and \
        {code(value) for value in spec["options"].values()} == {"0", "1"}


def option_label(spec, value):
    from .dashboard import equal
    if value is None:
        return "Unknown"
    if spec.get("kind") == "enum":
        return next((label for label, option in spec.get("options", {}).items() if equal(option, value)), "Unknown")
    try:
        number = f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)
    return number + ("°" if spec.get("key") == "tempSel" else "")


def last_run_label(c, when):
    """A Maintenance card's last-run line, translated, with numbers and dates in the app's language."""
    text, fields = last_run_text(when)
    language = translator(c)
    shown = {}
    if "count" in fields:
        shown["count"] = language.number(fields["count"])
    if "date" in fields:
        local = fields["date"].astimezone()
        # "06 Dec 2025": the day and month as the app writes them, then the year.
        shown["date"] = language.date(local).split(" ", 1)[1]+f" {local.year}"
    return tr(c, text).format(**shown)


def louver_position(label):
    return int(label[-1]) if label.startswith("Position ") and label[-1].isdigit() else 0


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
        rounded(self, 0, 36, 108, 84, 12, fill=blend(tone, C.SURFACE, .16), outline="")
        for offset in range(-1, 2):
            index = self.value+offset
            if not 0 <= index < self.limit:
                continue
            y = 60+offset*self.ROW_HEIGHT+self.drag_offset
            centre = abs(y-60) < self.ROW_HEIGHT/2
            text = "—" if offset == 0 and not self.chosen else translator(self).number(self.number(index))+("°" if centre else "")
            aa_text(self, 54, y, text=text, fill=tone if centre else C.FAINT,
                             font=font(-40 if centre else -18, "light"))


class SheetHost:
    """Bottom sheets over a dimmed window, shared by All functions and the dashboard.

    A host provides `window`, `app` and `sheet` (None while closed)."""

    def tone(self):
        """The accent for this host: the dashboard's dial colour (grey while the AC is off)."""
        return self.app.dial_accent()

    def text(self, c, x, y, value, size, color=None, anchor="w", weight="normal", width=None, translate=True):
        options = {"width": width} if width else {}
        return aa_text(c, x, y, text=tr(c, value) if translate else value, anchor=anchor, fill=color or C.TEXT,
                             font=font(size, weight), **options)

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
        background = rounded(c, 0, 0, width, height+40, 26, fill=C.CARD, outline=C.TRACK)
        c.tag_lower(background)
        rounded(c, width/2-20, 12, width/2+20, 17, 3, fill=C.STRONG, outline="")

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
        left_width = (width-48-gap)/(1+primary_flex)
        x1, x2 = 24, 24+left_width
        rounded(c, x1, y, x2, y+50, 14, fill=C.CARD, outline=C.STRONG, width=1.2)
        self.text(c, (x1+x2)/2, y+25, back, -14, C.TEXT, "center", "bold")
        self.sheet_hit((x1, y, x2, y+50), self.close_sheet)
        x1, x2 = x2+gap, width-24
        rounded(c, x1, y, x2, y+50, 14, fill=tone, outline="")
        self.text(c, (x1+x2)/2, y+25, primary, -14, C.ON_BRAND, "center", "black")
        self.sheet_hit((x1, y, x2, y+50), run)
        return y+50+28

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
            from .dashboard import equal
            tone = self.tone()
            y = 30
            self.text(c, 24, y+12, "Airflow", -22, weight="black")
            self.text(c, 24, y+38, "Vertical louver. Position 1 is the most closed, 5 the most open.", -13, C.MUTED,
                      width=width-48)
            y += 62
            for spec in specs:
                if len(specs) > 1:
                    section_label(c, 24, y+6, spec["label"])
                    y += 22
                options = list(spec["options"].items())
                cell = (width-48-20)/3
                for index, (label, value) in enumerate(options):
                    x = 24+(index % 3)*(cell+10)
                    top = y+(index//3)*128
                    on = equal(value, self.sheet_choice.get(spec["key"]))
                    fill = self.app.soft(tone) if on else C.SURFACE
                    rounded(c, x, top, x+cell, top+118, 18, fill=fill, outline=tone if on else fill, width=2)
                    louver(c, x+cell/2-36, top+14, louver_position(label), C.TEXT, tone if on else C.FAINT)
                    self.text(c, x+cell/2, top+96, label, -13, tone if on else C.TEXT, "center", "bold")
                    self.sheet_hit((x, top, x+cell, top+118), lambda key=spec["key"], value=value: choose(key, value))
                y += ((len(options)+2)//3)*128+6
            return self.sheet_buttons(c, y+6, width, "Cancel", "Set value", done)
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


class FunctionsView(SheetHost):
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        app.dialog = self.window
        app.dialog_view = self
        localized_title(self.window, "Room AC Control · All functions")
        self.window.geometry("{}x{}".format(*SIZE))
        self.window.resizable(False, False)
        paint(self.window, bg="BG")
        self.window.transient(app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, "Room AC Control", self.close, maximize=False, size=SIZE, owner=app.root)
        self.photo = unit_photo(self.window, 92)
        self.section = "settings"
        self.rows, self.loading, self.schedule_error = None, False, None
        self.hits, self.visible_items = [], []
        # Preset settings start closed; "More" starts closed too.
        self.expanded_presets, self.more_open = set(), False
        self.started = {}  # Maintenance routines started from this window, by label.
        # hOn's recent command history, read once per window for each routine's last run.
        self.history_state = None  # None, "queued", "loading", "loaded" or "failed"
        self.sheet = None
        self.selected_function = None
        self.scrollable = False
        self.wheel_remainder = 0
        self.body = paint(tk.Frame(self.window, padx=20), bg="BG")
        self.body.pack(fill="both", expand=True)
        self.top = tk.Canvas(self.body, height=48, highlightthickness=0)
        self.top.pack(fill="x", pady=(0, 14))
        self.top.bind("<Button-1>", lambda event: self.close() if event.x <= 48 else None)
        self.top.bind("<Motion>", lambda event: self.top.configure(cursor="hand2" if event.x <= 48 else ""))
        # Search: a rounded field with the glass, the entry and a Ctrl F hint.
        self.search = tk.StringVar()
        self.search_bar = tk.Canvas(self.body, height=48, highlightthickness=0)
        self.search_bar.pack(fill="x", pady=(0, 14))
        self.search_entry = tk.Entry(self.search_bar, textvariable=self.search, relief="flat", bd=0, font=font(-14, "semibold"))
        self.search_bar.bind("<Configure>", lambda event: self.draw_search())
        self.search_bar.bind("<Button-1>", lambda event: self.search_entry.focus_set())
        self.search_entry.bind("<FocusIn>", lambda event: self.draw_search())
        self.search_entry.bind("<FocusOut>", lambda event: self.draw_search())
        self.search_entry.bind("<Escape>", self.reset_search)
        self.window.bind("<Control-f>", self.focus_search)
        self.window.bind("<Escape>", lambda event: self.close_sheet() if self.sheet else None)
        self.tabs = tk.Canvas(self.body, height=48, highlightthickness=0, cursor="hand2")
        self.tabs.pack(fill="x", pady=(0, 16))
        self.tabs.bind("<Button-1>", lambda event: self.navigate(int(event.x // (max(self.tabs.winfo_width(), WIDTH)/len(TABS)))))
        self.footer = paint(tk.Frame(self.body), bg="BG")
        self.apply_button = PillButton(self.footer, "Apply", self.apply, kind="accent", size=-14, tone=app.settings_accent)
        self.discard_button = PillButton(self.footer, "Discard", self.discard, kind="ghost")
        self.content = tk.Canvas(self.body, highlightthickness=0, yscrollincrement=1)
        self.content.pack(fill="both", expand=True)
        self.content.bind("<Configure>", lambda event: self.render(keep_scroll=True))
        self.content.bind("<Button-1>", self.click)
        self.content.bind("<Motion>", self.motion)
        self.window.bind("<MouseWheel>", self.wheel)
        self.search.trace_add("write", lambda *args: (self.draw_search(), self.render()))
        refresh_on_theme(self.top, self.repaint)
        refresh_on_language(self.top, self.repaint)
        self.repaint()

    def tone(self):
        """All functions keeps the mode's colour while the AC is off, like Settings."""
        return self.app.settings_accent()

    # Frame

    def repaint(self):
        if not self.window.winfo_exists():
            return
        self.draw_top()
        self.draw_search()
        self.render(keep_scroll=True)
        if self.sheet:
            self.sheet["draw"]()

    def draw_top(self):
        c = self.top
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), WIDTH)
        rounded(c, 0, 2, 44, 46, 14, fill=C.CARD, outline="")
        icon(c, "back", 22, 24, C.TEXT, scale=.8, bg=C.CARD)
        aa_text(c, 56, 13, text=tr(c, "All functions"), anchor="w", fill=C.TEXT, font=font(-24, "black"))
        selected = self.app.selected
        aa_text(c, 56, 37, text=f"{selected['name']} · {selected['model']}", anchor="w", fill=C.MUTED, font=font(-12, "semibold"))
        c.create_image(width, 24, image=self.photo, anchor="e")

    def draw_search(self):
        c = self.search_bar
        if not c.winfo_exists():
            return
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), WIDTH)
        focused = self.window.focus_get() is self.search_entry
        rounded(c, 1, 1, width-1, 47, 14, fill=C.CARD, outline=C.BRAND if focused else C.TRACK, width=1.2)
        icon(c, "search", 24, 24, C.MUTED, scale=.75, bg=C.CARD)
        hint = "Ctrl F"
        chip = measure(c, hint, -11, "black")+14
        rounded(c, width-14-chip, 14, width-14, 34, 6, fill=C.SURFACE, outline="")
        aa_text(c, width-14-chip/2, 24, text=hint, fill=C.MUTED, font=font(-11, "black"))
        self.search_entry.configure(bg=C.CARD, fg=C.TEXT, insertbackground=C.TEXT, disabledbackground=C.CARD,
                                    selectbackground=C.SOFT, selectforeground=C.ON_SOFT)
        c.create_window(44, 24, window=self.search_entry, anchor="w", width=width-44-chip-30, height=28)
        if not self.search.get() and not focused:
            aa_text(c, 46, 24, text=tr(c, "Search settings, presets and schedules"), anchor="w", fill=C.MUTED,
                          font=font(-14, "semibold"), tags="placeholder")
            c.tag_bind("placeholder", "<Button-1>", lambda event: self.search_entry.focus_set())

    def draw_tabs(self):
        c = self.tabs
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), WIDTH)
        rounded(c, 0, 0, width, 48, 16, fill=C.CARD, outline="")
        segment = (width-8-4*(len(TABS)-1))/len(TABS)
        query = self.search.get().strip()
        tone = self.tone()
        for index, (key, label) in enumerate(TABS):
            x = 4+index*(segment+4)
            on = key == self.section and not query
            fill = blend(tone, C.CARD, .14) if on else C.CARD
            rounded(c, x, 4, x+segment, 44, 12, fill=fill, outline="")
            caption = tr(c, label)
            size = -12 if measure(c, caption, -12, "bold")+22 <= segment-8 else -11
            left = x+segment/2-(measure(c, caption, size, "bold")+20)/2
            ink = tone if on else C.MUTED
            icon(c, SECTION_GLYPHS[key], left+7, 24, ink, scale=.55, bg=fill)
            aa_text(c, left+20, 24, text=caption, anchor="w", fill=ink, font=font(size, "bold"))

    def navigate(self, index):
        index = max(0, min(len(TABS)-1, index))
        self.section = TABS[index][0]
        if self.search.get():
            self.search.set("")
        else:
            self.render()

    def focus_search(self, event=None):
        if self.sheet is None:
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, "end")
        return "break"

    def reset_search(self, event=None):
        self.search.set("")
        return "break"

    # Content

    def render(self, keep_scroll=False):
        if not self.window.winfo_exists() or not self.app.selected:
            return
        c = self.content
        position = c.yview()[0] if keep_scroll else 0
        c.delete("all")
        c.configure(bg=C.BG)
        self.hits = []
        self.draw_tabs()
        query = self.search.get().strip()
        if query:
            height = self.draw_results(c, 0, query)
        else:
            draw = {"settings": self.draw_settings, "everyday": self.draw_everyday,
                    "maintenance": self.draw_maintenance, "schedules": self.draw_schedules}[self.section]
            height = draw(c, 0)
        visible = max(1, c.winfo_height())
        c.configure(scrollregion=(0, 0, WIDTH, max(visible, height+16)))
        self.scrollable = height+16 > visible
        c.yview_moveto(position if self.scrollable else 0)
        self.update_footer()

    # Kept for callers of the earlier card view.
    render_section = render

    def hit(self, box, action):
        self.hits.append((box, action))

    def card(self, c, x1, y1, x2, y2, radius=20, fill=None):
        item = rounded(c, x1, y1, x2, y2, radius, fill=fill or C.CARD, outline="")
        c.tag_lower(item)
        return item

    def divider(self, c, y):
        aa_line(c, 16, y, WIDTH-16, y, fill=C.TRACK)

    # Settings

    def draw_settings(self, c, y):
        selected = self.app.selected
        controls = selected.get("controls", {})
        tone = self.tone()
        x0, x1 = 16, WIDTH-16
        section_label(c, 4, y+7, "Comfort")
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
                self.text(c, x0, y+9, "Mode", -14, weight="bold")
                self.text(c, x1, y+9, "Takes effect after Apply", -12, C.MUTED, "e", "semibold")
                y += 26
                gap = 6
                width = (x1-x0-gap*(len(options)-1))/len(options)
                current = self.app.base_mode()
                for i, option in enumerate(options):
                    bx = x0+i*(width+gap)
                    label = option["label"]
                    on = label == current
                    color = accent(label)
                    fill = self.app.soft(color) if on else C.SURFACE
                    rounded(c, bx, y, bx+width, y+66, 14, fill=fill, outline=color if on else fill, width=1.5)
                    ink = color if on else C.MUTED
                    icon(c, mode_icon(label), bx+width/2, y+24, ink, scale=.8, bg=fill)
                    caption = tr(c, label)
                    size = -12 if measure(c, caption, -12, "bold") <= width-6 else -10
                    self.text(c, bx+width/2, y+48, caption, size, ink, "center", "bold", translate=False)
                    self.hit((bx, y, bx+width, y+66), lambda option=option: self.stage_mode(option))
                y += 66+16
            elif block == "fan":
                self.text(c, x0, y+9, "Fan speed", -14, weight="bold")
                y += 26
                fans = list(selected["fans"].items())
                gap = 6
                width = (x1-x0-gap*(len(fans)-1))/len(fans)
                for i, (label, value) in enumerate(fans):
                    bx = x0+i*(width+gap)
                    on = label == self.app.fan.get()
                    fill = self.app.soft(tone) if on else C.SURFACE
                    rounded(c, bx, y, bx+width, y+60, 14, fill=fill, outline=tone if on else fill, width=1.5)
                    ink = tone if on else C.MUTED
                    fan_bars(c, bx+width/2-9, y+26, FAN_LEVELS.get(label, 0), ink if on else C.FAINT, fill,
                             heights=(7, 11, 15), width=5)
                    self.text(c, bx+width/2, y+43, label, -12, ink, "center", "bold")
                    self.hit((bx, y, bx+width, y+60), lambda value=value: self.stage("windSpeed", value))
                y += 60+16
            elif block == "airflow":
                value = self.app.airflow_value()
                rounded(c, x0, y, x0+64, y+52, 14, fill=C.SURFACE, outline="")
                louver(c, x0+4, y+1, louver_position(value), C.TEXT, tone, scale=.78)
                self.text(c, x0+78, y+16, "Airflow", -14, weight="bold")
                note = tr(c, value) + (" · " + tr(c, AIRFLOW_NOTES[value]) if value in AIRFLOW_NOTES else "")
                self.text(c, x0+78, y+36, note, -12, C.MUTED, weight="semibold", translate=False)
                icon(c, "next", x1-8, y+26, C.MUTED, scale=.7, bg=C.CARD)
                self.hit((x0, y, x1, y+52), self.open_airflow_sheet)
                y += 52+16
            elif block == "temperature":
                spec = controls["tempSel"]
                self.text(c, x0, y+11, "Target temperature", -14, weight="bold")
                number = translator(c).number
                note = f"{number(f'{spec['min']:g}')}–{number(f'{spec['max']:g}')} °C · " + \
                    tr(c, "{value}° steps").format(value=number(f"{spec['step']:g}"))
                self.text(c, x0, y+31, note, -12, C.MUTED, weight="semibold", translate=False)
                try:
                    value = number(f"{float(self.app.temp.get()):g}") + "°"
                except ValueError:
                    value = "—"
                plus, minus = x1-20, x1-20-40-56
                for x, direction in ((minus, -1), (plus, 1)):
                    aa_oval(c, x-20, y+1, x+20, y+41, fill=C.SURFACE, outline="")
                    aa_line(c, x-7, y+21, x+7, y+21, fill=C.TEXT, width=2.4, capstyle="round")
                    if direction > 0:
                        aa_line(c, x, y+14, x, y+28, fill=C.TEXT, width=2.4, capstyle="round")
                    self.hit((x-20, y+1, x+20, y+41), lambda direction=direction: self.step_temp(direction))
                self.text(c, (minus+plus)/2, y+21, value, -24, tone, "center", "light", translate=False)
                y += 42+16
        if blocks:
            self.card(c, 0, top, WIDTH, y)
        else:
            self.text(c, WIDTH/2, y+20, "No comfort controls are exposed by your AC.", -13, C.MUTED, "center")
            y += 40
        y += 16
        # Features: on/off settings as tiles.
        toggles = [(key, controls[key]) for key in FEATURE_ORDER if key in controls and is_toggle(controls[key])]
        toggles += [(key, spec) for key, spec in controls.items() if key not in FEATURE_ORDER and key not in COMFORT
                    and is_toggle(spec) and function_group(key, label=spec["label"]) != "maintenance"]
        if toggles:
            section_label(c, 4, y+7, "Features")
            y += 24
            width = (WIDTH-10)/2
            for index, (key, spec) in enumerate(toggles):
                bx, by = (index % 2)*(width+10), y+(index//2)*126
                self.draw_feature(c, bx, by, width, key, spec)
            y += ((len(toggles)+1)//2)*126
            y += 6
        # Anything else the AC exposes, as rows.
        others = [item for item in section_items(self.app.selected, "settings")
                  if item["key"] not in COMFORT and not is_toggle(item["spec"])]
        if others:
            section_label(c, 4, y+7, "More settings")
            y += 24
            top = y
            for index, item in enumerate(others):
                if index:
                    aa_line(c, 16, y, WIDTH, y, fill=C.TRACK)
                spec = item["spec"]
                self.text(c, 16, y+26, spec["label"], -14, weight="bold")
                value = tr(c, option_label(spec, self.app.current(spec["key"])))
                self.text(c, WIDTH-36, y+26, value, -13, C.MUTED, "e", "semibold", translate=False)
                icon(c, "next", WIDTH-18, y+26, C.MUTED, scale=.6, bg=C.CARD)
                self.hit((0, y, WIDTH, y+52), lambda spec=spec: self.edit_setting(spec))
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
        fill = blend(color, C.CARD, .08) if on else C.CARD
        rounded(c, x, y, x+width, y+116, 18, fill=fill, outline=blend(color, C.BG, .35) if on else fill, width=1.5)
        square = blend(color, C.CARD, .16) if on else C.SURFACE
        rounded(c, x+14, y+14, x+50, y+50, 12, fill=square, outline="")
        icon(c, glyph, x+32, y+32, color if on else C.MUTED, scale=.7, bg=square)
        switch(c, x+width-54, y+20, on, color)
        self.text(c, x+14, y+70, spec["label"], -14, weight="bold")
        if description:
            self.text(c, x+14, y+82, description, -12, C.MUTED, "nw", width=width-28)
        self.hit((x, y, x+width, y+116), lambda: self.toggle_feature(key))

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
            from .control_choices import airflow_choices
            if key in {"windDirectionVertical", "windDirectionHorizontal"}:
                options = airflow_choices(spec)
            else:
                options = [{"label": label, "value": value, "glyph": glyph_for(spec["label"]),
                            "description": spec.get("description", "")} for label, value in spec["options"].items()]
            self.choice_panel = ChoicePanel(self.window, spec["label"], options, self.app.current(key),
                                            lambda value: self.stage(key, value))
            return
        from tkinter import ttk
        from .i18n import localized
        window = tk.Toplevel(self.window)
        localized_title(window, spec["label"])
        paint(window, bg="BG")
        window.resizable(False, False)
        window.transient(self.window)
        window.grab_set()

        def close_detail():
            window.destroy()
            self.window.grab_set()
        from .window_header import WindowHeader
        window.header = WindowHeader(window, spec["label"], close_detail, maximize=False)
        body = ttk.Frame(window, padding=22)
        body.pack(fill="both", expand=True)
        getter, initial = self.app.field(body, spec, self.app.current(key), use_reported=True,
                                         show_label=key != "tempSel")
        hint = (f"Drag, scroll or use ↑ ↓ · {spec['min']:g}–{spec['max']:g}°C · Step {spec['step']:g}"
                if key == "tempSel" else f"Range {spec['min']:g}–{spec['max']:g} · Step {spec['step']:g}")
        localized(ttk.Label(body, text=hint, style="Muted.TLabel")).pack(anchor="w", pady=12)

        def done():
            value = getter()
            if value is not None:
                self.stage(key, value)
            close_detail()
        localized(ttk.Button(body, text="Set value", style="Accent.TButton", command=done)).pack(fill="x")
        window.protocol("WM_DELETE_WINDOW", close_detail)

    # Everyday use

    def preset_details(self, item):
        """Colour, glyph, description and the settings a preset applies, as (label, value, glyph, on)."""
        selected = self.app.selected
        controls = selected.get("controls", {})
        features = []
        if item["kind"] == "night":
            mode = item["label"].replace(" Night", "")
            values = {**PRESET_DEFAULTS.get(preset_key(item), {}),
                      **self.app.memory.mode_values(selected, dict(item["changes"]))}
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
            description = ("Cooling with the unit’s Sleep feature, for the night." if mode == "Cool" else
                           "Heating with the unit’s Sleep feature, for the night.")
            return color, mode_icon(mode), description, features[:6]
        form = item["form"]
        saved = {**PRESET_DEFAULTS.get(preset_key(item), {}),
                 **self.app.memory.function_values(selected["id"], item["command"], form)}
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
                features.append((spec["label"], "On" if on else "Off", FEATURES.get(key, (glyph_for(spec["label"]),))[0], on))
            else:
                features.append((spec["label"], label, "thermo" if key == "tempSel" else glyph_for(spec["label"]), True))
        # Target temperature always shows: if a long list would push it past the sixth tile, it takes that tile.
        temperature = next((index for index, feature in enumerate(features) if feature[2] == "thermo"), None)
        if temperature is not None and temperature >= GRID_TILES:
            features.insert(GRID_TILES-1, features.pop(temperature))
        maintenance = item.get("section") == "maintenance" or form.get("group") == "maintenance"
        description = "Cleaning / service routine" if maintenance else "Everyday comfort preset"
        return color, glyph, description, features[:GRID_TILES]

    def draw_everyday(self, c, y):
        self.text(c, 4, y+9, "Presets for normal use. Open one to review it, then start it.", -13, C.MUTED, width=WIDTH-8)
        y += 32
        items, choices, primary, others = self.everyday_presets()
        self.visible_items = items
        # The presets the user chose (up to four) first, in their order; the rest go in More.
        if choices:
            y = self.draw_top_header(c, y, len(primary))
        for item in primary:
            y = self.draw_preset_card(c, y, item)+10
        if choices and not primary:
            rounded(c, 0, y, WIDTH, y+56, 18, fill=C.CARD, outline="")
            hint = tr(c, "No top presets. Choose up to {limit} to show them here.").format(
                limit=translator(c).number(TOP_PRESET_LIMIT))
            self.text(c, 20, y+28, hint, -13, C.MUTED, weight="semibold", width=WIDTH-40, translate=False)
            self.hit((0, y, WIDTH, y+56), self.open_top_presets)
            y += 56+10
        if others:
            y += 6
            section_label(c, 4, y+7, "More")
            count = translator(c).number(len(others))
            chip = measure(c, count, -11, "black")+16
            rounded(c, WIDTH-48-chip, y-4, WIDTH-48, y+18, 9, fill=C.SURFACE, outline="")
            self.text(c, WIDTH-48-chip/2, y+7, count, -11, C.MUTED, "center", "black", translate=False)
            icon(c, "chevron", WIDTH-28, y+7, C.MUTED, scale=.7, bg=C.BG, rotate=180 if self.more_open else 0)
            self.hit((0, y-8, WIDTH, y+22), self.toggle_more)
            y += 30
            if self.more_open:
                for item in others:
                    y = self.draw_preset_card(c, y, item)+10
        if not items:
            self.text(c, WIDTH/2, y+30, "No presets are exposed by your AC.", -13, C.MUTED, "center")
            y += 60
        # What each mode restores when the AC is turned on in it.
        options = self.app.mode_options()
        if options:
            y += 6
            section_label(c, 4, y+7, "Remembered per mode")
            self.text(c, 4, y+26, "Turning on in a mode brings back what you last used in it.", -12, C.MUTED)
            y += 42
            width = (WIDTH-20)/3
            controls = self.app.selected.get("controls", {})
            for index, option in enumerate(options):
                bx, by = (index % 3)*(width+10), y+(index//3)*110
                label = option["label"]
                color = accent(label)
                values = self.app.memory.mode_values(self.app.selected, dict(option["value"]))
                rounded(c, bx, by, bx+width, by+100, 18, fill=C.CARD, outline="")
                icon(c, mode_icon(label), bx+22, by+22, color, scale=.6, bg=C.CARD)
                self.text(c, bx+36, by+22, label, -12, color, weight="bold")
                temperature = option_label({"key": "tempSel"}, values["tempSel"]) if "tempSel" in values else "—"
                self.text(c, bx+14, by+56, translator(c).number(temperature), -30, weight="light", translate=False)
                parts = []
                if "windSpeed" in values and "windSpeed" in controls:
                    parts.append(tr(c, option_label(controls["windSpeed"], values["windSpeed"])))
                spec = self.app.airflow_spec()
                if spec and spec["key"] in values:
                    parts.append(tr(c, option_label(spec, values[spec["key"]])))
                detail = " · ".join(parts) or tr(c, "Not used yet")
                self.text(c, bx+14, by+84, detail, -11, C.MUTED, weight="semibold", width=width-20, translate=False)
            y += ((len(options)+2)//3)*110
        return y

    def draw_preset_card(self, c, y, item):
        """A preset header, a settings toggle and, when open, the settings grid."""
        color, glyph, description, features = self.preset_details(item)
        expanded = item["label"] in self.expanded_presets
        toggle = y+88
        rows = (len(features)+2)//3 if expanded else 0
        height = 128+rows*50+4 if expanded else 128
        tint = self.app.soft(color)
        rounded(c, 16, y+16, 80, y+80, 18, fill=tint, outline="")
        icon(c, glyph, 48, y+48, color, scale=1.3, bg=tint)
        review = tr(c, "Review")
        chip = measure(c, review, -12, "black")+30
        self.text(c, 94, y+36, item["label"], -17, weight="black", width=WIDTH-94-chip-28)
        self.text(c, 94, y+60, description, -12, C.MUTED, width=WIDTH-94-chip-28)
        rounded(c, WIDTH-16-chip, y+31, WIDTH-16, y+65, 11, fill=tint, outline="")
        self.text(c, WIDTH-16-chip+12, y+48, review, -12, color, weight="black", translate=False)
        icon(c, "next", WIDTH-28, y+48, color, scale=.5, bg=tint)
        aa_line(c, 16, toggle, WIDTH-16, toggle, fill=C.TRACK)
        self.text(c, 16, toggle+18, "Hide settings" if expanded else "Show settings", -13, weight="bold")
        icon(c, "chevron", WIDTH-26, toggle+18, C.MUTED, scale=.7, rotate=180 if expanded else 0)
        if expanded:
            cell = (WIDTH-32-12)/3
            for index, (label, value, symbol, on) in enumerate(features):
                fx = 16+(index % 3)*(cell+6)
                fy = y+128+(index//3)*50
                rounded(c, fx, fy, fx+cell, fy+44, 12, fill=C.SURFACE, outline="")
                square = self.app.soft(color, C.SURFACE) if on else C.STRONG
                rounded(c, fx+10, fy+9, fx+36, fy+35, 8, fill=square, outline="")
                icon(c, symbol, fx+23, fy+22, color if on else C.MUTED, scale=.5, bg=square)
                caption = tr(c, label)
                while measure(c, caption, -11, "semibold") > cell-50 and len(caption) > 3:
                    caption = caption[:-2]+"…"
                self.text(c, fx+44, fy+14, caption, -11, C.MUTED, weight="semibold", translate=False)
                shown = tr(c, value)
                while measure(c, shown, -13, "black") > cell-50 and len(shown) > 3:
                    shown = shown[:-2]+"…"
                self.text(c, fx+44, fy+30, shown, -13, C.TEXT if on else C.MUTED, weight="black", translate=False)
        self.card(c, 0, y, WIDTH, y+height, 22)
        self.hit((0, y, WIDTH, y+88), lambda item=item: self.open_preset(item))
        self.hit((0, toggle, WIDTH, toggle+36), lambda item=item: self.toggle_preset(item))
        return y+height

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
        section_label(c, 4, y+7, "Top presets")
        used = tr(c, "{count} of {limit}").format(count=number(count), limit=number(TOP_PRESET_LIMIT))
        left = 4+measure(c, tr(c, "Top presets").upper(), -11, "black")+10
        self.text(c, left, y+7, used, -11, C.MUTED, weight="semibold", translate=False)
        tone = self.tone()
        tint = self.app.soft(tone)
        caption = tr(c, "Choose up to {limit}").format(limit=number(TOP_PRESET_LIMIT))
        chip = measure(c, caption, -12, "black")+42
        rounded(c, WIDTH-chip, y-7, WIDTH, y+21, 14, fill=tint, outline="")
        icon(c, "sliders", WIDTH-chip+17, y+7, tone, scale=.5, bg=tint)
        self.text(c, WIDTH-chip+30, y+7, caption, -12, tone, weight="black", translate=False)
        self.hit((WIDTH-chip, y-10, WIDTH, y+24), self.open_top_presets)
        return y+34

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
            self.text(c, 24, y+14, "Top presets", -22, weight="black")
            count = tr(c, "{count} of {limit} chosen").format(count=number(len(self.top_choice)),
                                                              limit=number(TOP_PRESET_LIMIT))
            chip = measure(c, count, -12, "black")+28
            tint = self.app.soft(tone)
            rounded(c, width-24-chip, y+1, width-24, y+27, 13, fill=tint, outline="")
            self.text(c, width-24-chip/2, y+14, count, -12, tone, "center", "black", translate=False)
            intro = tr(c, "Choose up to {limit} presets to show first, in the order you pick them. "
                          "The rest go in More.").format(limit=number(TOP_PRESET_LIMIT))
            self.text(c, 24, y+38, intro, -13, C.MUTED, "nw", width=width-48, translate=False)
            y += 92
            cell = (width-48-10)/2
            for index, item in enumerate(choices):
                key = preset_key(item)
                x, top_y = 24+(index % 2)*(cell+10), y+(index//2)*74
                color, glyph = self.preset_details(item)[:2]
                position = self.top_choice.index(key)+1 if key in self.top_choice else 0
                blocked = full and not position
                fill = self.app.soft(color) if position else C.SURFACE
                rounded(c, x, top_y, x+cell, top_y+64, 16, fill=fill, outline=color if position else fill, width=1.5)
                rounded(c, x+12, top_y+14, x+48, top_y+50, 11, fill=C.CARD, outline="")
                icon(c, glyph, x+30, top_y+32, C.FAINT if blocked else color, scale=.6, bg=C.CARD)
                self.text(c, x+58, top_y+32, item["label"], -13, C.FAINT if blocked else C.TEXT, weight="bold",
                          width=cell-58-44)
                cx, cy = x+cell-24, top_y+32
                if position:
                    aa_oval(c, cx-12, cy-12, cx+12, cy+12, fill=color, outline="")
                    self.text(c, cx, cy, number(position), -12, C.ON_BRAND, "center", "black", translate=False)
                else:
                    aa_oval(c, cx-11, cy-11, cx+11, cy+11, fill="", outline=C.TRACK if blocked else C.STRONG, width=1.5)
                self.sheet_hit((x, top_y, x+cell, top_y+64), lambda key=key: choose(key))
            y += ((len(choices)+1)//2)*74+2
            # What a selection does; once the four places are taken, how to free one.
            background, ink = (C.WARN_BG, C.WARN_TEXT) if self.top_refused else (C.SURFACE, C.MUTED)
            note = ("All {limit} places are taken. Remove a chosen preset to add another." if full else
                    "Select a preset to add it, or select it again to remove it.")
            rounded(c, 24, y, width-24, y+46, 14, fill=background, outline="")
            icon(c, "alert" if full else "check", 46, y+23, ink, scale=.5, bg=background)
            self.text(c, 64, y+23, tr(c, note).format(limit=number(TOP_PRESET_LIMIT)), -12, ink, weight="semibold",
                      width=width-100, translate=False)
            y += 46+20
            return self.sheet_buttons(c, y, width, "Cancel", "Save", lambda: self.save_top_presets(list(self.top_choice)))
        self.open_sheet(draw)

    def save_top_presets(self, keys):
        self.app.memory.save_top_presets(self.app.selected["id"], keys)
        failed = self.app.memory.save_error
        self.app.status.set("Top presets changed for this session, but could not be saved on this computer."
                            if failed else "Top presets saved.")
        self.close_sheet()
        self.render(keep_scroll=True)

    # Maintenance

    def draw_maintenance(self, c, y):
        warn = C.WARN_TEXT
        rounded(c, 0, y, WIDTH, y+46, 16, fill=C.WARN_BG, outline="")
        icon(c, "alert", 22, y+23, warn, scale=.6, bg=C.WARN_BG)
        self.text(c, 40, y+23, "Routines can interrupt what the AC is doing. Nothing here starts on its own.", -12, warn,
                  weight="semibold", width=WIDTH-56)
        y += 46+16
        # Air filter status from the AC's own reminder.
        reminder = any(alert.get("kind") == "filter" for alert in self.app.selected.get("alerts", []))
        color = C.WARN_TEXT if reminder else C.OK
        tint = blend(color, C.CARD, .12)
        rounded(c, 18, y+18, 114, y+114, 22, fill=tint, outline="")
        icon(c, "filter", 66, y+66, color, scale=1.9, bg=tint)
        self.text(c, 132, y+36, "Air filter", -17, weight="black")
        detail = ("The AC reports that its filter needs cleaning." if reminder else
                  "The unit hasn’t asked for a clean. When it does, a reminder shows on the dashboard.")
        self.text(c, 132, y+50, detail, -12, C.MUTED, "nw", width=WIDTH-150)
        label = tr(c, "Clean the air filter" if reminder else "No reminder")
        chip = measure(c, label, -11, "black")+34
        chip_fill = blend(color, C.CARD, .16)
        rounded(c, 132, y+88, 132+chip, y+112, 12, fill=chip_fill, outline="")
        icon(c, "alert" if reminder else "check", 146, y+100, color, scale=.42, bg=chip_fill)
        self.text(c, 156, y+100, label, -11, color, weight="black", translate=False)
        self.card(c, 0, y, WIDTH, y+132, 22)
        y += 132+16
        items = [dict(item, section="maintenance") for item in section_items(self.app.selected, "maintenance")]
        self.visible_items = items
        if not items:
            self.text(c, WIDTH/2, y+30, "No maintenance functions are exposed by your AC.", -13, C.MUTED, "center")
            return y+60
        section_label(c, 4, y+7, "Cleaning routines")
        y += 24
        if self.history_state is None:
            # After this draw: a preview answers at once and redraws.
            self.history_state = "queued"
            self.window.after_idle(self.load_routine_history)
        runs = self.app.memory.routine_runs(self.app.selected["id"])
        width = (WIDTH-10)/2
        palette = ("cool", "heat", "dry", "fan", "auto")
        for index, item in enumerate(items):
            bx, by = (index % 2)*(width+10), y+(index//2)*ROUTINE_STEP
            color = accent(palette[index % len(palette)])
            tint = self.app.soft(color)
            rounded(c, bx, by, bx+width, by+ROUTINE_STEP-10, 20, fill=C.CARD, outline="")
            rounded(c, bx+16, by+16, bx+72, by+72, 16, fill=tint, outline="")
            icon(c, glyph_for(item["label"]), bx+44, by+44, color, scale=1.1, bg=tint)
            self.text(c, bx+16, by+92, item["label"], -15, weight="black", width=width-32)
            if item["kind"] == "setting":
                detail = item.get("description") or tr(c, option_label(item["spec"], self.app.current(item["key"])))
            else:
                detail = "Cleaning / service routine"
            self.text(c, bx+16, by+108, detail, -12, C.MUTED, "nw", width=width-32)
            # How long since the routine last ran: hOn's history, runs started or seen here, or a
            # date the person set. Selecting the line sets the date.
            when = runs.get(item_routine(item))
            if when is None and self.history_state in {"queued", "loading"}:
                elapsed = tr(c, "Checking the last run…")
            else:
                elapsed = last_run_label(c, when)
            icon(c, "clock", bx+24, by+154, color if when else C.MUTED, scale=.5, bg=C.CARD)
            self.text(c, bx+36, by+154, elapsed, -11, C.TEXT if when else C.MUTED, weight="bold",
                      width=width-66, translate=False)
            icon(c, "next", bx+width-22, by+154, C.MUTED, scale=.45, bg=C.CARD)
            self.hit((bx, by+140, bx+width, by+168), lambda item=item, color=color: self.edit_last_run(item, color))
            state = self.started.get(item["label"])
            top = by+170
            if state:
                fill = blend(C.OK, C.CARD, .14)
                rounded(c, bx+16, top, bx+width-16, top+40, 12, fill=fill, outline="")
                shown = tr(c, state)
                left = bx+width/2-(measure(c, shown, -13, "black")+20)/2
                icon(c, "check", left+7, top+20, C.OK, scale=.5, bg=fill)
                self.text(c, left+20, top+20, shown, -13, C.OK, "w", "black", translate=False)
            else:
                label = "Turn on" if item["kind"] == "setting" else "Start"
                rounded(c, bx+16, top, bx+width-16, top+40, 12, fill=color, outline="")
                self.text(c, bx+width/2, top+20, label, -13, C.ON_BRAND, "center", "black")
                self.hit((bx+16, top, bx+width-16, top+40), lambda item=item: self.start_routine(item))
        return y+((len(items)+1)//2)*ROUTINE_STEP

    def edit_last_run(self, item, color):
        """Set when a routine last ran, for runs this app could not see (hOn does not keep them)."""
        from datetime import date
        from .routine_history import day_to_time, parse_day
        routine = item_routine(item)
        known = self.app.memory.routine_runs(self.app.selected["id"]).get(routine)
        field = tk.StringVar(value=known.astimezone().strftime("%d/%m/%Y") if known else "")
        self.date_error = False

        def pick(days_ago):
            field.set((date.today()-timedelta(days=days_ago)).strftime("%d/%m/%Y"))
            self.date_error = False
            self.sheet["draw"]()

        def save():
            day = parse_day(field.get(), date.today())
            if day is None:
                self.date_error = True
                self.sheet["draw"]()
                return
            self.app.memory.set_routine_run(self.app.selected["id"], routine, day_to_time(day))
            failed = self.app.memory.save_error
            self.app.status.set("The last run could not be saved on this computer." if failed else "Last run saved.")
            self.close_sheet()
            self.render(keep_scroll=True)

        def draw(c, width):
            y = 34
            tint = self.app.soft(color)
            rounded(c, 24, y, 92, y+68, 20, fill=tint, outline="")
            icon(c, "calendar", 58, y+34, color, scale=1.1, bg=tint)
            self.text(c, 108, y+12, tr(c, "Last run").upper(), -11, color, weight="black", translate=False)
            self.text(c, 108, y+40, item["label"], -22, weight="black", width=width-132)
            y += 68+18
            self.text(c, 24, y+10, "hOn does not keep past cleaning runs. Set when this one last ran.", -13, C.MUTED,
                      "w", width=width-48)
            y += 36
            # Quick picks, then the date itself (day/month/year).
            x = 24
            for label, days_ago in (("Today", 0), ("Yesterday", 1)):
                caption = tr(c, label)
                chip = measure(c, caption, -13, "bold")+32
                rounded(c, x, y, x+chip, y+40, 12, fill=C.SURFACE, outline="")
                self.text(c, x+chip/2, y+20, caption, -13, C.TEXT, "center", "bold", translate=False)
                self.sheet_hit((x, y, x+chip, y+40), lambda days_ago=days_ago: pick(days_ago))
                x += chip+8
            entry = getattr(self, "date_entry", None)
            if entry is None or not entry.winfo_exists():
                entry = tk.Entry(c, textvariable=field, relief="flat", bd=0, font=font(-15, "bold"), justify="center")
                entry.bind("<Return>", lambda event: save())
                self.date_entry = entry
                self.sheet["widgets"].append(entry)
            outline = C.DANGER_TEXT if self.date_error else C.STRONG
            rounded(c, x, y, width-24, y+40, 12, fill=C.SURFACE, outline=outline, width=1.2)
            entry.configure(bg=C.SURFACE, fg=C.TEXT, insertbackground=C.TEXT)
            c.create_window((x+width-24)/2, y+20, window=entry, width=width-24-x-24, height=28)
            y += 40+10
            hint = "Enter a past date as day/month/year, for example 06/12/2025." if self.date_error else                 "Day/month/year, for example 06/12/2025."
            self.text(c, 24, y+8, hint, -12, C.DANGER_TEXT if self.date_error else C.MUTED, "w", width=width-48)
            y += 34
            return self.sheet_buttons(c, y, width, "Cancel", "Save", save, 1.4)
        self.date_entry = None
        self.open_sheet(draw)
        self.date_entry.focus_set()

    def load_routine_history(self):
        """Read hOn's recent command history once; runs found are kept on this computer."""
        if self.history_state == "loading":
            return
        self.history_state = "loading"
        device_id = self.app.selected["id"]

        def done(runs):
            self.history_state = "loaded"
            self.app.memory.record_routine_runs(device_id, runs)
            if self.window.winfo_exists():
                self.render(keep_scroll=True)

        def failed(error):
            from .diagnostics import diagnostics
            diagnostics.record("routine_history_failed", error)
            self.history_state = "failed"
            if self.window.winfo_exists():
                self.render(keep_scroll=True)
        self.app.load_routine_history(done, failed)

    def start_routine(self, item):
        """Ask in a bottom sheet, in the app's own style, before starting a maintenance routine."""
        index = next((i for i, other in enumerate(self.visible_items) if other["label"] == item["label"]), 0)
        color = accent(("cool", "heat", "dry", "fan", "auto")[index % 5])
        turn_on = item["kind"] == "setting"

        def draw(c, width):
            y = 34
            tint = self.app.soft(color)
            rounded(c, 24, y, 92, y+68, 20, fill=tint, outline="")
            icon(c, glyph_for(item["label"]), 58, y+34, color, scale=1.25, bg=tint)
            self.text(c, 108, y+12, tr(c, "Maintenance routine").upper(), -11, color, weight="black", translate=False)
            self.text(c, 108, y+40, item["label"], -22, weight="black", width=width-132)
            y += 68+20
            rounded(c, 24, y, width-24, y+48, 14, fill=C.WARN_BG, outline="")
            icon(c, "alert", 46, y+24, C.WARN_TEXT, scale=.55, bg=C.WARN_BG)
            self.text(c, 64, y+24, "It may interrupt what the AC is doing.", -12, C.WARN_TEXT, weight="semibold",
                      width=width-100)
            y += 48+20
            return self.sheet_buttons(c, y, width, "Cancel", "Turn on" if turn_on else "Start",
                                      lambda: self.run_routine(item), 1.4)
        self.open_sheet(draw)

    def run_routine(self, item):
        self.close_sheet()
        if item["kind"] == "setting":
            value = next((option for option in item["spec"]["options"].values() if code(option) == "1"), "1")
            self.app.action("configure", {item["key"]: value})
        else:
            saved = self.app.memory.function_values(self.app.selected["id"], item["command"], item["form"])
            parameters = {spec["key"]: saved.get(spec["key"], spec.get("value")) for spec in item["form"].get("parameters", [])}
            self.app.action("execute", {"command": item["command"], "category": item["form"]["category"],
                                        "parameters": {key: value for key, value in parameters.items() if value is not None}})
        self.started[item["label"]] = "Preview only" if self.app.demo else "Started"
        self.render(keep_scroll=True)

    # Schedules

    def load_schedules(self):
        if self.loading:
            return
        self.loading, self.schedule_error = True, None

        def done(rows):
            self.loading, self.rows = False, rows
            if self.window.winfo_exists():
                self.render(keep_scroll=True)

        def failed(error):
            self.loading, self.schedule_error = False, error
            if self.window.winfo_exists():
                self.render(keep_scroll=True)
        self.app.load_schedules(done, failed)

    def row_segments(self, row):
        """Hour spans a schedule covers, as (day, start, end) for the week view."""
        start = row["start"][0]+row["start"][1]/60 if row["start"] else None
        end = row["end"][0]+row["end"][1]/60 if row["end"] else None
        if row["kind"] == "repeat":
            days = row["days"]
        elif row["kind"] == "once" and row["due"].date()-datetime.now().date() < timedelta(days=7):
            days = (row["due"].weekday(),)
        else:
            return []
        spans = []
        for day in days:
            if start is not None and end is not None:
                if end > start:
                    spans.append((day, start, end))
                else:
                    spans.extend([(day, start, 24), ((day+1) % 7, 0, end)])
            elif start is not None:
                spans.append((day, start, min(24, start+.5)))
            else:
                spans.append((day, max(0, end-.5), end))
        return spans

    def schedule_color(self, row):
        if not row["active"]:
            return C.STRONG
        if row.get("mode"):
            return accent(row["mode"])
        return C.FAINT

    def draw_schedules(self, c, y):
        self.visible_items = []
        if self.rows is None:
            if not self.loading and self.schedule_error is None:
                self.load_schedules()
            if self.rows is None:
                message = self.schedule_error or "Loading schedules from hOn…"
                self.text(c, WIDTH/2, y+40, message, -13, C.DANGER if self.schedule_error else C.MUTED, "center",
                          width=WIDTH-40)
                if self.schedule_error:
                    self.text(c, WIDTH/2, y+76, "Try again", -13, C.BRAND, "center", "black")
                    self.hit((WIDTH/2-60, y+60, WIDTH/2+60, y+92), self.retry_schedules)
                return y+100
        rows = self.rows
        today = datetime.now()
        # This week.
        top = y
        y += 16
        self.text(c, 16, y+10, "This week", -14, weight="bold")
        saved = tr(c, "Saved in hOn")
        self.text(c, WIDTH-16, y+10, saved, -12, C.MUTED, "e", "semibold", translate=False)
        icon(c, "cloud", WIDTH-16-measure(c, saved, -12, "semibold")-14, y+10, C.MUTED, scale=.6, bg=C.CARD)
        y += 30
        left, right = 58, WIDTH-16
        spans = [(row, span) for row in rows for span in self.row_segments(row)]
        for day in range(7):
            is_today = day == today.weekday()
            self.text(c, 16, y+8, DAY_NAMES[day], -12, C.TEXT if is_today else C.MUTED,
                      weight="black" if is_today else "semibold")
            rounded(c, left, y, right, y+16, 8, fill=C.STRONG if is_today else C.SURFACE, outline="")
            for row, (span_day, start, end) in spans:
                if span_day == day:
                    x1 = left+(right-left)*start/24
                    x2 = max(x1+8, left+(right-left)*end/24)
                    rounded(c, x1, y, x2, y+16, 8, fill=self.schedule_color(row), outline="")
            if is_today:
                now = left+(right-left)*(today.hour+today.minute/60)/24
                aa_line(c, now, y-4, now, y+20, fill=C.TEXT, width=2)
            y += 26
        for index, hour in enumerate(("00", "06", "12", "18", "24")):
            self.text(c, left+(right-left)*index/4, y+2, hour, -10, C.FAINT, "center", "semibold", translate=False)
        y += 18
        legend = []
        for row in rows:
            mode = (row.get("mode") or "").replace(" Night", "")
            if mode and row["active"] and mode not in [label for label, color in legend]:
                legend.append((mode, accent(mode)))
        legend.append(("Paused", C.STRONG))
        x = left
        for label, color in legend:
            rounded(c, x, y+2, x+10, y+12, 3, fill=color, outline="")
            x += 15
            item = self.text(c, x, y+7, label, -11, C.MUTED, weight="semibold")
            x = c.bbox(item)[2]+14
        aa_line(c, x, y+1, x, y+13, fill=C.TEXT, width=2)
        self.text(c, x+6, y+7, "Now", -11, C.MUTED, weight="semibold")
        y += 30
        self.card(c, 0, top, WIDTH, y)
        y += 16
        repeating = [row for row in rows if row["kind"] == "repeat"]
        if repeating:
            section_label(c, 4, y+7, "Repeating")
            y += 24
            for row in repeating:
                y = self.draw_repeating(c, y, row)+10
        others = [row for row in rows if row["kind"] != "repeat"]
        if others:
            y += 6
            section_label(c, 4, y+7, "One-time and other")
            y += 24
            top = y
            for index, row in enumerate(others):
                if index:
                    aa_line(c, 64, y, WIDTH, y, fill=C.TRACK)
                once = row["kind"] == "once"
                square = self.app.soft(C.BRAND) if once else C.SURFACE
                rounded(c, 16, y+14, 52, y+50, 12, fill=square, outline="")
                icon(c, ("power" if row["start"] else "clock") if once else "calendar", 34, y+32,
                     C.BRAND if once else C.MUTED, scale=.6, bg=square)
                if once:
                    action = "Turn on" if row["start"] else "Turn off"
                    when = translator(c).date(row["due"]) + " " + clock_text(row["start"] or row["end"])
                    title = tr(c, action) + " · " + when
                    sub = tr(c, row["mode"]) if row.get("mode") else tr(c, "Turns the AC on" if row["start"] else "Turns the AC off")
                else:
                    title, sub = tr(c, "A repeat this app does not edit"), tr(c, "Made in the hOn app")
                self.text(c, 66, y+23, title, -14, weight="bold", translate=False, width=WIDTH-170)
                self.text(c, 66, y+42, sub, -12, C.MUTED, weight="semibold", translate=False)
                if once:
                    self.text(c, WIDTH-16, y+32, "Delete", -12, C.DANGER, "e", "black")
                    self.hit((WIDTH-90, y, WIDTH, y+64), lambda row=row: self.delete_schedule(row))
                else:
                    self.text(c, WIDTH-16, y+32, "Manage in hOn", -12, C.MUTED, "e", "black")
                y += 64
            self.card(c, 0, top, WIDTH, y)
            y += 16
        if not rows:
            self.text(c, WIDTH/2, y+20, "No schedules yet. Create one, or choose a repeat on End at.", -13, C.MUTED,
                      "center", width=WIDTH-40)
            y += 50
        # New schedule.
        tone = C.BRAND
        rounded(c, 0, y, WIDTH, y+54, 16, fill=tone, outline="")
        label = tr(c, "New schedule")
        width = measure(c, label, -15, "black")+26
        icon(c, "plus", WIDTH/2-width/2+8, y+27, C.ON_BRAND, scale=.7, bg=tone)
        self.text(c, WIDTH/2-width/2+26, y+27, label, -15, C.ON_BRAND, weight="black", translate=False)
        self.hit((0, y, WIDTH, y+54), lambda: self.edit_schedule(None))
        return y+54

    def retry_schedules(self):
        self.schedule_error = None
        self.load_schedules()
        self.render(keep_scroll=True)

    def draw_repeating(self, c, y, row):
        active = row["active"]
        color = accent(row["mode"]) if row.get("mode") else C.MUTED
        top = y
        start, end = row["start"], row["end"]
        if start and end:
            title = f"{clock_text(start)} → {clock_text(end)}"
        elif start:
            title = tr(c, f"On at {clock_text(start)}")
        else:
            title = tr(c, f"Off at {clock_text(end)}")
        ink = C.TEXT if active else C.MUTED
        self.text(c, 16, y+30, title, -24, ink, weight="light", translate=False)
        switch(c, WIDTH-62, y+16, active, C.BRAND, width=46, height=28)
        self.hit((WIDTH-70, y+8, WIDTH, y+52), lambda: self.set_active(row, not active))
        y += 56
        for day in range(7):
            x = 16+day*29
            included = day in row["days"]
            fill = blend(color, C.CARD, .16) if included else C.CARD
            aa_oval(c, x, y, x+24, y+24, fill=fill, outline="")
            initial = tr(c, DAY_NAMES[day])[:1]
            self.text(c, x+12, y+12, initial, -11, color if included else C.FAINT, "center", "black", translate=False)
        if start:
            chip = tr(c, row["mode"]) if row.get("mode") else tr(c, "Turns the AC on")
            if "temperature" in row:
                chip += " " + translator(c).number(f"{row['temperature']:g}") + "°"
            glyph = mode_icon(row["mode"]) if row.get("mode") else "power"
        else:
            chip, glyph = tr(c, "Turns the AC off"), "power"
        width = measure(c, chip, -12, "bold")+40
        tint = blend(color, C.CARD, .14)
        rounded(c, WIDTH-16-width, y-1, WIDTH-16, y+25, 13, fill=tint, outline="")
        icon(c, glyph, WIDTH-16-width+15, y+12, color, scale=.45, bg=tint)
        self.text(c, WIDTH-16-width+27, y+12, chip, -12, color, weight="bold", translate=False)
        y += 38
        aa_line(c, 16, y, WIDTH-16, y, fill=C.TRACK)
        y += 10
        rounded(c, 16, y, 76, y+34, 10, fill=C.SURFACE, outline="")
        self.text(c, 46, y+17, "Edit", -12, C.TEXT, "center", "black")
        self.hit((16, y, 76, y+34), lambda: self.edit_schedule(row))
        self.text(c, 92, y+17, "Delete", -12, C.DANGER, weight="black")
        self.hit((84, y, 150, y+34), lambda: self.delete_schedule(row))
        note = ", ".join(tr(c, label) for label in day_labels(row["days"])) if active else tr(c, "Paused")
        self.text(c, WIDTH-16, y+17, note, -12, C.MUTED, "e", "semibold", translate=False)
        y += 34+16
        card = self.card(c, 0, top, WIDTH, y)
        if not active:
            restyle(c, card, fill=blend(C.CARD, C.BG, .6))
        return y

    def set_active(self, row, active):
        self.app.change_schedule("active", row["id"], self.schedules_changed, self.schedule_failed, active=active)

    def delete_schedule(self, row):
        if not messagebox.askyesno("Room AC Control", tr(self.window, "Delete this schedule from hOn?"), parent=self.window):
            return
        self.app.change_schedule("delete", row["id"], self.schedules_changed, self.schedule_failed)

    def schedules_changed(self, rows):
        self.rows = rows
        if self.window.winfo_exists():
            self.render(keep_scroll=True)

    def schedule_failed(self, error):
        self.app.status.set(error)
        self.rows = None
        self.schedule_error = error
        if self.window.winfo_exists():
            self.render(keep_scroll=True)

    def edit_schedule(self, row):
        """Open the schedule editor above this window; the list reloads when it closes."""
        self.app.open_schedules(self.window)
        view = self.app.schedules_view
        if view is None:
            return
        view.on_close = self.schedules_closed
        view.edit(row)

    def schedules_closed(self):
        self.rows = None
        if self.window.winfo_exists():
            self.load_schedules()

    # Search

    def draw_results(self, c, y, query):
        groups = []
        for section, title in SECTIONS:
            items = [dict(item, section=section) for item in section_items(self.app.selected, section)
                     if matches_search(item, query)]
            if items:
                groups.append((title, items))
        self.visible_items = [item for _, items in groups for item in items]
        count = len(self.visible_items)
        self.text(c, 4, y+9, f"{count} {'result' if count == 1 else 'results'} across all functions", -13, C.MUTED)
        y += 30
        for title, items in groups:
            section_label(c, 4, y+7, title)
            y += 24
            top = y
            for index, item in enumerate(items):
                if index:
                    aa_line(c, 64, y, WIDTH, y, fill=C.TRACK)
                rounded(c, 16, y+12, 52, y+48, 12, fill=C.SURFACE, outline="")
                icon(c, glyph_for(item["label"]), 34, y+30, C.MUTED, scale=.6, bg=C.SURFACE)
                self.text(c, 66, y+21, item["label"], -14, weight="bold")
                if item["kind"] == "setting":
                    sub = tr(c, option_label(item["spec"], self.app.current(item["key"])))
                    if is_toggle(item["spec"]) and item["key"] not in COMFORT:
                        action = lambda item=item: self.toggle_feature(item["key"])
                    else:
                        action = lambda item=item: self.edit_setting(item["spec"])
                else:
                    sub = tr(c, "Maintenance routine" if title == "Maintenance" else "Preset")
                    action = lambda item=item: self.open_preset(item)
                self.text(c, 66, y+40, sub, -12, C.MUTED, weight="semibold", translate=False)
                icon(c, "next", WIDTH-18, y+30, C.MUTED, scale=.6, bg=C.CARD)
                self.hit((0, y, WIDTH, y+60), action)
                y += 60
            self.card(c, 0, top, WIDTH, y)
            y += 16
        if not count:
            self.text(c, WIDTH/2, y+30, "No matching functions. Try another word or clear the search.", -13, C.MUTED,
                      "center", width=WIDTH-40)
            y += 60
        return y

    # Sheets

    def open_preset(self, item):
        """Review a preset, Night mode or maintenance routine, then start it explicitly."""
        selected = self.app.selected
        controls = selected.get("controls", {})
        color, glyph, description, features = self.preset_details(item)
        maintenance = item.get("section") == "maintenance" or \
            (item["kind"] == "function" and item["form"].get("group") == "maintenance")
        # Editable parameters: (spec, initial value).
        if item["kind"] == "night":
            values = {**PRESET_DEFAULTS.get(preset_key(item), {}),
                      **self.app.memory.mode_values(selected, dict(item["changes"]))}
            parameters = [(controls[key], values.get(key, self.app.current(key)))
                          for key in ("tempSel", "windSpeed", "windDirectionVertical", "muteStatus", "ecoMode")
                          if key in controls]
        else:
            saved = {**PRESET_DEFAULTS.get(preset_key(item), {}),
                     **self.app.memory.function_values(selected["id"], item["command"], item["form"])}
            parameters = [(spec, saved.get(spec["key"], spec.get("value"))) for spec in item["form"].get("parameters", [])
                          if spec["key"] != "machMode"]
        values = {spec["key"]: value for spec, value in parameters}
        holder = {}

        def pick(key, value):
            values[key] = value
            self.sheet["draw"]()

        def draw(c, width):
            from .dashboard import equal
            y = 30
            tint = self.app.soft(color)
            rounded(c, 24, y, 108, y+84, 22, fill=tint, outline="")
            icon(c, glyph, 66, y+42, color, scale=1.5, bg=tint)
            kind = "Maintenance routine" if maintenance else "Preset"
            self.text(c, 124, y+12, tr(c, kind).upper(), -11, color, weight="black", translate=False)
            self.text(c, 124, y+38, item["label"], -24, weight="black", width=width-148)
            self.text(c, 124, y+56, description, -13, C.MUTED, "nw", width=width-148)
            y += 84+20
            temperature = next(((spec, value) for spec, value in parameters if spec["key"] == "tempSel"), None)
            airflows = [(spec, value) for spec, value in parameters if spec["key"].startswith("windDirection")]
            enums = [(spec, value) for spec, value in parameters
                     if spec["key"] != "tempSel" and spec.get("kind") == "enum" and not is_toggle(spec)
                     and not spec["key"].startswith("windDirection")]
            toggles = [(spec, value) for spec, value in parameters if is_toggle(spec)]
            others = [(spec, value) for spec, value in parameters
                      if spec["key"] != "tempSel" and spec.get("kind") != "enum"]
            left = 24
            if temperature:
                spec, value = temperature
                rounded(c, 24, y, 156, y+150, 18, fill=C.SURFACE, outline="")
                self.text(c, 36, y+16, "Temperature", -11, C.MUTED, weight="bold")
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
                c.create_window(36, y+26, window=wheel, anchor="nw")
                left = 168
            ry = y
            for spec, value in enums:
                options = list(spec["options"].items())
                current = values.get(spec["key"], value)
                if len(options) <= 4:
                    box = 74
                    rounded(c, left, ry, width-24, ry+box, 18, fill=C.SURFACE, outline="")
                    self.text(c, left+12, ry+16, spec["label"], -11, C.MUTED, weight="bold")
                    cell = (width-24-left-24-4*(len(options)-1))/len(options)
                    for index, (label, option) in enumerate(options):
                        x = left+12+index*(cell+4)
                        on = equal(option, current)
                        fill = blend(color, C.SURFACE, .18) if on else C.SURFACE
                        rounded(c, x, ry+30, x+cell, ry+62, 9, fill=fill, outline="")
                        shown = tr(c, label)
                        while measure(c, shown, -12, "bold") > cell-4 and len(shown) > 3:
                            shown = shown[:-2]+"."
                        self.text(c, x+cell/2, ry+46, shown, -12, color if on else C.MUTED, "center", "bold", translate=False)
                        self.sheet_hit((x, ry+30, x+cell, ry+62), lambda key=spec["key"], option=option: pick(key, option))
                else:
                    box = 62
                    rounded(c, left, ry, width-24, ry+box, 18, fill=C.SURFACE, outline="")
                    self.text(c, left+12, ry+20, spec["label"], -11, C.MUTED, weight="bold")
                    self.text(c, left+12, ry+42, option_label(spec, current), -14, weight="bold")
                    icon(c, "next", width-40, ry+31, C.MUTED, scale=.6, bg=C.SURFACE)

                    def choose(spec=spec):
                        from .control_choices import airflow_choices
                        choices = airflow_choices(spec) if spec["key"].startswith("windDirection") else \
                            [{"label": label, "value": option} for label, option in spec["options"].items()]
                        self.choice_panel = ChoicePanel(self.window, spec["label"], choices, values.get(spec["key"]),
                                                        lambda value: pick(spec["key"], value))
                    self.sheet_hit((left, ry, width-24, ry+box), choose)
                ry += box+10
            for spec, value in others:
                rounded(c, left, ry, width-24, ry+62, 18, fill=C.SURFACE, outline="")
                self.text(c, left+12, ry+20, spec["label"], -11, C.MUTED, weight="bold")
                self.text(c, left+12, ry+42, option_label(spec, values.get(spec["key"], value)), -14, weight="bold")
                ry += 72
            if temperature or enums or others:
                y = max(y+(160 if temperature else 0), ry)
            for spec, value in airflows:
                section_label(c, 24, y+6, spec["label"])
                y += 22
                options = list(spec["options"].items())
                columns = min(6, len(options))
                cell = (width-48-8*(columns-1))/columns
                current = values.get(spec["key"], value)
                for index, (label, option) in enumerate(options):
                    x = 24+(index % columns)*(cell+8)
                    top = y+(index//columns)*96
                    on = equal(option, current)
                    fill = self.app.soft(color) if on else C.SURFACE
                    rounded(c, x, top, x+cell, top+88, 14, fill=fill, outline=color if on else fill, width=2)
                    louver(c, x+cell/2-25, top+6, louver_position(label), C.TEXT, color if on else C.FAINT, scale=.7)
                    shown = tr(c, label) if not label.startswith("Position ") else label[-1]
                    self.text(c, x+cell/2, top+72, shown, -12, color if on else C.TEXT, "center", "bold", translate=False)
                    self.sheet_hit((x, top, x+cell, top+88), lambda key=spec["key"], option=option: pick(key, option))
                y += ((len(options)+columns-1)//columns)*96+8
            if toggles:
                section_label(c, 24, y+6, "Features")
                y += 22
                cell = (width-48-16)/3
                for index, (spec, value) in enumerate(toggles):
                    x = 24+(index % 3)*(cell+8)
                    top = y+(index//3)*58
                    on = code(values.get(spec["key"], value)) == "1"
                    fill = blend(color, C.CARD, .10) if on else C.SURFACE
                    rounded(c, x, top, x+cell, top+50, 14, fill=fill, outline=blend(color, C.BG, .45) if on else fill, width=1.5)
                    symbol = FEATURES.get(spec["key"], (glyph_for(spec["label"]),))[0]
                    icon(c, symbol, x+20, top+25, color if on else C.MUTED, scale=.55, bg=fill)
                    name = tr(c, spec["label"])
                    while measure(c, name, -12, "black") > cell-46 and len(name) > 3:
                        name = name[:-2]+"…"
                    self.text(c, x+36, top+17, name, -12, weight="black", translate=False)
                    self.text(c, x+36, top+34, "On" if on else "Off", -11, color if on else C.MUTED, weight="black")
                    self.sheet_hit((x, top, x+cell, top+50), lambda key=spec["key"], on=on: pick(key, "0" if on else "1"))
                y += ((len(toggles)+2)//3)*58+6
            if item["kind"] == "night":
                fill = blend(color, C.CARD, .10)
                rounded(c, 24, y, width-24, y+44, 14, fill=fill, outline="")
                icon(c, "moon", 46, y+22, color, scale=.55, bg=fill)
                self.text(c, 64, y+22, "Sleep is on for this preset.", -12, color, weight="bold")
                y += 54
            warn = "This routine may interrupt the current operation." if maintenance else \
                "Starting this preset may turn the AC on and replace its current settings."
            rounded(c, 24, y, width-24, y+48, 14, fill=C.WARN_BG, outline="")
            icon(c, "alert", 46, y+24, C.WARN_TEXT, scale=.55, bg=C.WARN_BG)
            self.text(c, 64, y+24, warn, -12, C.WARN_TEXT, weight="semibold", width=width-100)
            y += 48+18
            primary = "Start maintenance routine" if maintenance else \
                "Start preset" if item["kind"] == "night" or item.get("command") == "startProgram" else "Run function"
            if maintenance:
                return self.sheet_buttons(c, y, width, "Back to cards", primary, lambda: self.run_preset(item, values), 1.4)
            return self.preset_buttons(c, y, width, primary, item, values, color)
        self.open_sheet(draw)
        self.selected_function = item
        self.search_entry.configure(state="disabled")

    # Kept for callers of the earlier card view.
    configure_function = open_preset

    def sheet_closed(self):
        self.selected_function = None
        self.search_entry.configure(state="normal")

    def sheet_done(self):
        self.render(keep_scroll=True)

    def preset_buttons(self, c, y, width, primary, item, values, color):
        """Back, Save (keep these values for next time) and Start."""
        gap = 8
        widths = (width-48-2*gap)*.28, (width-48-2*gap)*.28
        x = 24
        for label, action, fill, ink, outline in (
                ("Back", self.close_sheet, C.CARD, C.TEXT, C.STRONG),
                ("Save", lambda: self.save_preset(item, values), self.app.soft(color), color, color)):
            w = widths[0]
            rounded(c, x, y, x+w, y+50, 14, fill=fill, outline=outline, width=1.2)
            self.text(c, x+w/2, y+25, label, -14, ink, "center", "black")
            self.sheet_hit((x, y, x+w, y+50), action)
            x += w+gap
        rounded(c, x, y, width-24, y+50, 14, fill=color, outline="")
        self.text(c, (x+width-24)/2, y+25, primary, -14, C.ON_BRAND, "center", "black")
        self.sheet_hit((x, y, width-24, y+50), lambda: self.run_preset(item, values))
        return y+50+28

    def save_preset(self, item, values):
        """Keep a preset's values for next time without starting it."""
        from .program_memory import mode_key, normalized
        selected = self.app.selected
        chosen = {key: normalized(value) for key, value in values.items() if value is not None}
        if item["kind"] == "night":
            stored = {**self.app.memory.mode_values(selected, dict(item["changes"])), **chosen}
            stored.update({key: normalized(value) for key, value in item["changes"].items()})
            self.app.memory.save(selected["id"], mode_key(selected, item["changes"]), stored)
        else:
            self.app.memory.remember_function(selected["id"], item["command"], item["form"]["category"], chosen)
        failed = self.app.memory.save_error
        self.app.status.set("Preset settings could not be saved on this computer." if failed else "Preset settings saved.")
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

    # Input

    def click(self, event):
        if self.sheet:
            return
        x, y = self.content.canvasx(event.x), self.content.canvasy(event.y)
        for (x1, y1, x2, y2), action in list(self.hits):
            if x1 <= x <= x2 and y1 <= y <= y2:
                action()
                return

    def motion(self, event):
        x, y = self.content.canvasx(event.x), self.content.canvasy(event.y)
        inside = any(x1 <= x <= x2 and y1 <= y <= y2 for (x1, y1, x2, y2), _ in self.hits)
        self.content.configure(cursor="hand2" if inside else "")

    def wheel(self, event):
        widget = event.widget
        if isinstance(widget, TemperatureWheel) or self.sheet:
            return
        if widget.winfo_class() in {"Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Scale", "TScale", "Text"}:
            return
        while widget is not None and widget is not self.content:
            if widget is self.window:
                return
            widget = widget.master
        if widget is None or not self.scrollable:
            return "break"
        self.wheel_remainder -= event.delta / 120
        steps = int(self.wheel_remainder)
        if steps:
            self.content.yview_scroll(steps*48, "units")
            self.wheel_remainder -= steps
        return "break"

    # Status and footer

    def refresh_status(self):
        """Redraw values in place; keep the open sheet, scroll position and edits."""
        if self.window.winfo_exists():
            self.draw_top()
            self.render(keep_scroll=True)

    def update_footer(self):
        count = len(self.app.dirty)
        if count:
            self.apply_button.set_badge(count)
            self.apply_button.set_enabled(not self.app.busy)
            if not self.footer.winfo_manager():
                self.footer.pack(side="bottom", fill="x", pady=(12, 20), before=self.content)
                self.apply_button.pack(side="right")
                self.discard_button.pack(side="right", padx=(0, 4))
            self.apply_button.draw()
        elif self.footer.winfo_manager():
            self.footer.pack_forget()

    def discard(self):
        self.app.discard()
        self.render(keep_scroll=True)

    def apply(self):
        if not self.app.dirty:
            return
        self.close()
        self.app.action("apply")

    def close(self):
        self.close_sheet()
        self.app.dialog = None
        self.app.dialog_view = None
        if self.window.winfo_exists():
            self.window.destroy()
