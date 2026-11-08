"""The Schedules tab: a week view of every hOn timer, with pause, resume, edit and delete."""

from datetime import datetime, timedelta
from tkinter import messagebox

from ..control_choices import mode_icon
from ..i18n import tr, translator
from ..schedules import DAY_NAMES, clock_text, day_labels
from ..smooth import aa_line, aa_oval, restyle
from ..theme import C, accent, blend, icon, measure, rounded
from ..widgets import section_label, switch
from .model import (
    WIDTH,
)


class SchedulesTabMixin:
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
        start = row["start"][0] + row["start"][1] / 60 if row["start"] else None
        end = row["end"][0] + row["end"][1] / 60 if row["end"] else None
        if row["kind"] == "repeat":
            days = row["days"]
        elif row["kind"] == "once" and row["due"].date() - datetime.now().date() < timedelta(days=7):
            days = (row["due"].weekday(),)
        else:
            return []
        spans = []
        for day in days:
            if start is not None and end is not None:
                if end > start:
                    spans.append((day, start, end))
                else:
                    spans.extend([(day, start, 24), ((day + 1) % 7, 0, end)])
            elif start is not None:
                spans.append((day, start, min(24, start + 0.5)))
            else:
                spans.append((day, max(0, end - 0.5), end))
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
                self.text(
                    c,
                    WIDTH / 2,
                    y + 40,
                    message,
                    -13,
                    C.DANGER if self.schedule_error else C.MUTED,
                    "center",
                    width=WIDTH - 40,
                )
                if self.schedule_error:
                    self.text(c, WIDTH / 2, y + 76, "Try again", -13, C.BRAND, "center", "black")
                    self.hit((WIDTH / 2 - 60, y + 60, WIDTH / 2 + 60, y + 92), self.retry_schedules)
                return y + 100
        rows = self.rows
        today = datetime.now()
        # This week.
        top = y
        y += 16
        self.text(c, 16, y + 10, "This week", -14, weight="bold")
        saved = tr(c, "Saved in hOn")
        self.text(c, WIDTH - 16, y + 10, saved, -12, C.MUTED, "e", "semibold", translate=False)
        icon(c, "cloud", WIDTH - 16 - measure(c, saved, -12, "semibold") - 14, y + 10, C.MUTED, scale=0.6, bg=C.CARD)
        y += 30
        left, right = 58, WIDTH - 16
        spans = [(row, span) for row in rows for span in self.row_segments(row)]
        for day in range(7):
            is_today = day == today.weekday()
            self.text(
                c,
                16,
                y + 8,
                DAY_NAMES[day],
                -12,
                C.TEXT if is_today else C.MUTED,
                weight="black" if is_today else "semibold",
            )
            rounded(c, left, y, right, y + 16, 8, fill=C.STRONG if is_today else C.SURFACE, outline="")
            for row, (span_day, start, end) in spans:
                if span_day == day:
                    x1 = left + (right - left) * start / 24
                    x2 = max(x1 + 8, left + (right - left) * end / 24)
                    rounded(c, x1, y, x2, y + 16, 8, fill=self.schedule_color(row), outline="")
            if is_today:
                now = left + (right - left) * (today.hour + today.minute / 60) / 24
                aa_line(c, now, y - 4, now, y + 20, fill=C.TEXT, width=2)
            y += 26
        for index, hour in enumerate(("00", "06", "12", "18", "24")):
            self.text(
                c, left + (right - left) * index / 4, y + 2, hour, -10, C.FAINT, "center", "semibold", translate=False
            )
        y += 18
        legend = []
        for row in rows:
            mode = (row.get("mode") or "").replace(" Night", "")
            if mode and row["active"] and mode not in [label for label, color in legend]:
                legend.append((mode, accent(mode)))
        legend.append(("Paused", C.STRONG))
        x = left
        for label, color in legend:
            rounded(c, x, y + 2, x + 10, y + 12, 3, fill=color, outline="")
            x += 15
            item = self.text(c, x, y + 7, label, -11, C.MUTED, weight="semibold")
            x = c.bbox(item)[2] + 14
        aa_line(c, x, y + 1, x, y + 13, fill=C.TEXT, width=2)
        self.text(c, x + 6, y + 7, "Now", -11, C.MUTED, weight="semibold")
        y += 30
        self.card(c, 0, top, WIDTH, y)
        y += 16
        repeating = [row for row in rows if row["kind"] == "repeat"]
        if repeating:
            section_label(c, 4, y + 7, "Repeating")
            y += 24
            for row in repeating:
                y = self.draw_repeating(c, y, row) + 10
        others = [row for row in rows if row["kind"] != "repeat"]
        if others:
            y += 6
            section_label(c, 4, y + 7, "One-time and other")
            y += 24
            top = y
            for index, row in enumerate(others):
                if index:
                    aa_line(c, 64, y, WIDTH, y, fill=C.TRACK)
                once = row["kind"] == "once"
                square = self.app.soft(C.BRAND) if once else C.SURFACE
                rounded(c, 16, y + 14, 52, y + 50, 12, fill=square, outline="")
                icon(
                    c,
                    ("power" if row["start"] else "clock") if once else "calendar",
                    34,
                    y + 32,
                    C.BRAND if once else C.MUTED,
                    scale=0.6,
                    bg=square,
                )
                if once:
                    action = "Turn on" if row["start"] else "Turn off"
                    when = translator(c).date(row["due"]) + " " + clock_text(row["start"] or row["end"])
                    title = tr(c, action) + " · " + when
                    sub = (
                        tr(c, row["mode"])
                        if row.get("mode")
                        else tr(c, "Turns the AC on" if row["start"] else "Turns the AC off")
                    )
                else:
                    title, sub = tr(c, "A repeat this app does not edit"), tr(c, "Made in the hOn app")
                self.text(c, 66, y + 23, title, -14, weight="bold", translate=False, width=WIDTH - 170)
                self.text(c, 66, y + 42, sub, -12, C.MUTED, weight="semibold", translate=False)
                if once:
                    self.text(c, WIDTH - 16, y + 32, "Delete", -12, C.DANGER, "e", "black")
                    self.hit((WIDTH - 90, y, WIDTH, y + 64), lambda row=row: self.delete_schedule(row))
                else:
                    self.text(c, WIDTH - 16, y + 32, "Manage in hOn", -12, C.MUTED, "e", "black")
                y += 64
            self.card(c, 0, top, WIDTH, y)
            y += 16
        if not rows:
            self.text(
                c,
                WIDTH / 2,
                y + 20,
                "No schedules yet. Create one, or choose a repeat on End at.",
                -13,
                C.MUTED,
                "center",
                width=WIDTH - 40,
            )
            y += 50
        # New schedule.
        tone = C.BRAND
        rounded(c, 0, y, WIDTH, y + 54, 16, fill=tone, outline="")
        label = tr(c, "New schedule")
        width = measure(c, label, -15, "black") + 26
        icon(c, "plus", WIDTH / 2 - width / 2 + 8, y + 27, C.ON_BRAND, scale=0.7, bg=tone)
        self.text(c, WIDTH / 2 - width / 2 + 26, y + 27, label, -15, C.ON_BRAND, weight="black", translate=False)
        self.hit((0, y, WIDTH, y + 54), lambda: self.edit_schedule(None))
        return y + 54

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
        self.text(c, 16, y + 30, title, -24, ink, weight="light", translate=False)
        switch(c, WIDTH - 62, y + 16, active, C.BRAND, width=46, height=28)
        self.hit((WIDTH - 70, y + 8, WIDTH, y + 52), lambda: self.set_active(row, not active))
        y += 56
        for day in range(7):
            x = 16 + day * 29
            included = day in row["days"]
            fill = blend(color, C.CARD, 0.16) if included else C.CARD
            aa_oval(c, x, y, x + 24, y + 24, fill=fill, outline="")
            initial = tr(c, DAY_NAMES[day])[:1]
            self.text(
                c, x + 12, y + 12, initial, -11, color if included else C.FAINT, "center", "black", translate=False
            )
        if start:
            chip = tr(c, row["mode"]) if row.get("mode") else tr(c, "Turns the AC on")
            if "temperature" in row:
                chip += " " + translator(c).number(f"{row['temperature']:g}") + "°"
            glyph = mode_icon(row["mode"]) if row.get("mode") else "power"
        else:
            chip, glyph = tr(c, "Turns the AC off"), "power"
        width = measure(c, chip, -12, "bold") + 40
        tint = blend(color, C.CARD, 0.14)
        rounded(c, WIDTH - 16 - width, y - 1, WIDTH - 16, y + 25, 13, fill=tint, outline="")
        icon(c, glyph, WIDTH - 16 - width + 15, y + 12, color, scale=0.45, bg=tint)
        self.text(c, WIDTH - 16 - width + 27, y + 12, chip, -12, color, weight="bold", translate=False)
        y += 38
        aa_line(c, 16, y, WIDTH - 16, y, fill=C.TRACK)
        y += 10
        rounded(c, 16, y, 76, y + 34, 10, fill=C.SURFACE, outline="")
        self.text(c, 46, y + 17, "Edit", -12, C.TEXT, "center", "black")
        self.hit((16, y, 76, y + 34), lambda: self.edit_schedule(row))
        self.text(c, 92, y + 17, "Delete", -12, C.DANGER, weight="black")
        self.hit((84, y, 150, y + 34), lambda: self.delete_schedule(row))
        note = ", ".join(tr(c, label) for label in day_labels(row["days"])) if active else tr(c, "Paused")
        self.text(c, WIDTH - 16, y + 17, note, -12, C.MUTED, "e", "semibold", translate=False)
        y += 34 + 16
        card = self.card(c, 0, top, WIDTH, y)
        if not active:
            restyle(c, card, fill=blend(C.CARD, C.BG, 0.6))
        return y

    def set_active(self, row, active):
        self.app.change_schedule("active", row["id"], self.schedules_changed, self.schedule_failed, active=active)

    def delete_schedule(self, row):
        if not messagebox.askyesno(
            "Room AC Control", tr(self.window, "Delete this schedule from hOn?"), parent=self.window
        ):
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
