"""The All functions window: header, search, tabs, scrolling, footer and sheets.

Choices made here are staged on the dashboard, so Apply (here or there) sends them together."""

import tkinter as tk

from ..i18n import localized_title, refresh_on_language, tr
from ..smooth import aa_line, aa_text
from ..temperature_wheel import TemperatureWheel
from ..theme import C, blend, font, icon, measure, paint, refresh_on_theme, rounded, unit_photo
from ..widgets import PillButton, section_label
from .everyday_tab import EverydayTabMixin
from .maintenance_tab import MaintenanceTabMixin
from .model import (
    COMFORT,
    SECTION_GLYPHS,
    SECTIONS,
    SIZE,
    TABS,
    WIDTH,
    glyph_for,
    is_toggle,
    matches_search,
    option_label,
    section_items,
)
from .schedules_tab import SchedulesTabMixin
from .settings_tab import SettingsTabMixin
from .sheets import (
    SheetHost,
)


class FunctionsView(SettingsTabMixin, EverydayTabMixin, MaintenanceTabMixin, SchedulesTabMixin, SheetHost):
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
        from ..window_header import WindowHeader

        self.header = WindowHeader(
            self.window, "Room AC Control", self.close, maximize=False, size=SIZE, owner=app.root
        )
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
        self.search_entry = tk.Entry(
            self.search_bar, textvariable=self.search, relief="flat", bd=0, font=font(-14, "semibold")
        )
        self.search_bar.bind("<Configure>", lambda event: self.draw_search())
        self.search_bar.bind("<Button-1>", lambda event: self.search_entry.focus_set())
        self.search_entry.bind("<FocusIn>", lambda event: self.draw_search())
        self.search_entry.bind("<FocusOut>", lambda event: self.draw_search())
        self.search_entry.bind("<Escape>", self.reset_search)
        self.window.bind("<Control-f>", self.focus_search)
        self.window.bind("<Escape>", lambda event: self.close_sheet() if self.sheet else None)
        self.tabs = tk.Canvas(self.body, height=48, highlightthickness=0, cursor="hand2")
        self.tabs.pack(fill="x", pady=(0, 16))
        self.tabs.bind(
            "<Button-1>", lambda event: self.navigate(int(event.x // (max(self.tabs.winfo_width(), WIDTH) / len(TABS))))
        )
        self.footer = paint(tk.Frame(self.body), bg="BG")
        self.apply_button = PillButton(
            self.footer, "Apply", self.apply, kind="accent", size=-14, tone=app.settings_accent
        )
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
        icon(c, "back", 22, 24, C.TEXT, scale=0.8, bg=C.CARD)
        aa_text(c, 56, 13, text=tr(c, "All functions"), anchor="w", fill=C.TEXT, font=font(-24, "black"))
        selected = self.app.selected
        aa_text(
            c,
            56,
            37,
            text=f"{selected['name']} · {selected['model']}",
            anchor="w",
            fill=C.MUTED,
            font=font(-12, "semibold"),
        )
        c.create_image(width, 24, image=self.photo, anchor="e")

    def draw_search(self):
        c = self.search_bar
        if not c.winfo_exists():
            return
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), WIDTH)
        focused = self.window.focus_get() is self.search_entry
        rounded(c, 1, 1, width - 1, 47, 14, fill=C.CARD, outline=C.BRAND if focused else C.TRACK, width=1.2)
        icon(c, "search", 24, 24, C.MUTED, scale=0.75, bg=C.CARD)
        hint = "Ctrl F"
        chip = measure(c, hint, -11, "black") + 14
        rounded(c, width - 14 - chip, 14, width - 14, 34, 6, fill=C.SURFACE, outline="")
        aa_text(c, width - 14 - chip / 2, 24, text=hint, fill=C.MUTED, font=font(-11, "black"))
        self.search_entry.configure(
            bg=C.CARD,
            fg=C.TEXT,
            insertbackground=C.TEXT,
            disabledbackground=C.CARD,
            selectbackground=C.SOFT,
            selectforeground=C.ON_SOFT,
        )
        c.create_window(44, 24, window=self.search_entry, anchor="w", width=width - 44 - chip - 30, height=28)
        if not self.search.get() and not focused:
            aa_text(
                c,
                46,
                24,
                text=tr(c, "Search settings, presets and schedules"),
                anchor="w",
                fill=C.MUTED,
                font=font(-14, "semibold"),
                tags="placeholder",
            )
            c.tag_bind("placeholder", "<Button-1>", lambda event: self.search_entry.focus_set())

    def draw_tabs(self):
        c = self.tabs
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), WIDTH)
        rounded(c, 0, 0, width, 48, 16, fill=C.CARD, outline="")
        segment = (width - 8 - 4 * (len(TABS) - 1)) / len(TABS)
        query = self.search.get().strip()
        tone = self.tone()
        for index, (key, label) in enumerate(TABS):
            x = 4 + index * (segment + 4)
            on = key == self.section and not query
            fill = blend(tone, C.CARD, 0.14) if on else C.CARD
            rounded(c, x, 4, x + segment, 44, 12, fill=fill, outline="")
            caption = tr(c, label)
            size = -12 if measure(c, caption, -12, "bold") + 22 <= segment - 8 else -11
            left = x + segment / 2 - (measure(c, caption, size, "bold") + 20) / 2
            ink = tone if on else C.MUTED
            icon(c, SECTION_GLYPHS[key], left + 7, 24, ink, scale=0.55, bg=fill)
            aa_text(c, left + 20, 24, text=caption, anchor="w", fill=ink, font=font(size, "bold"))

    def navigate(self, index):
        index = max(0, min(len(TABS) - 1, index))
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
            draw = {
                "settings": self.draw_settings,
                "everyday": self.draw_everyday,
                "maintenance": self.draw_maintenance,
                "schedules": self.draw_schedules,
            }[self.section]
            height = draw(c, 0)
        visible = max(1, c.winfo_height())
        c.configure(scrollregion=(0, 0, WIDTH, max(visible, height + 16)))
        self.scrollable = height + 16 > visible
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
        aa_line(c, 16, y, WIDTH - 16, y, fill=C.TRACK)

    # Search

    def draw_results(self, c, y, query):
        groups = []
        for section, title in SECTIONS:
            items = [
                dict(item, section=section)
                for item in section_items(self.app.selected, section)
                if matches_search(item, query)
            ]
            if items:
                groups.append((title, items))
        self.visible_items = [item for _, items in groups for item in items]
        count = len(self.visible_items)
        self.text(c, 4, y + 9, f"{count} {'result' if count == 1 else 'results'} across all functions", -13, C.MUTED)
        y += 30
        for title, items in groups:
            section_label(c, 4, y + 7, title)
            y += 24
            top = y
            for index, item in enumerate(items):
                if index:
                    aa_line(c, 64, y, WIDTH, y, fill=C.TRACK)
                rounded(c, 16, y + 12, 52, y + 48, 12, fill=C.SURFACE, outline="")
                icon(c, glyph_for(item["label"]), 34, y + 30, C.MUTED, scale=0.6, bg=C.SURFACE)
                self.text(c, 66, y + 21, item["label"], -14, weight="bold")
                if item["kind"] == "setting":
                    sub = tr(c, option_label(item["spec"], self.app.current(item["key"])))
                    if is_toggle(item["spec"]) and item["key"] not in COMFORT:
                        action = lambda item=item: self.toggle_feature(item["key"])
                    else:
                        action = lambda item=item: self.edit_setting(item["spec"])
                else:
                    sub = tr(c, "Maintenance routine" if title == "Maintenance" else "Preset")
                    action = lambda item=item: self.open_preset(item)
                self.text(c, 66, y + 40, sub, -12, C.MUTED, weight="semibold", translate=False)
                icon(c, "next", WIDTH - 18, y + 30, C.MUTED, scale=0.6, bg=C.CARD)
                self.hit((0, y, WIDTH, y + 60), action)
                y += 60
            self.card(c, 0, top, WIDTH, y)
            y += 16
        if not count:
            self.text(
                c,
                WIDTH / 2,
                y + 30,
                "No matching functions. Try another word or clear the search.",
                -13,
                C.MUTED,
                "center",
                width=WIDTH - 40,
            )
            y += 60
        return y

    def sheet_closed(self):
        self.selected_function = None
        self.search_entry.configure(state="normal")

    def sheet_done(self):
        self.render(keep_scroll=True)

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
            self.content.yview_scroll(steps * 48, "units")
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
