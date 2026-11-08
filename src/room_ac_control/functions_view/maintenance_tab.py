"""The Maintenance tab: filter status and cleaning routines with their last run."""

import tkinter as tk
from datetime import timedelta

from ..controller import code
from ..i18n import tr
from ..routine_history import item_routine
from ..theme import C, accent, blend, font, icon, measure, rounded
from ..widgets import section_label
from .model import (
    ROUTINE_STEP,
    WIDTH,
    glyph_for,
    last_run_label,
    option_label,
    section_items,
)


class MaintenanceTabMixin:
    # Maintenance

    def draw_maintenance(self, c, y):
        warn = C.WARN_TEXT
        rounded(c, 0, y, WIDTH, y + 46, 16, fill=C.WARN_BG, outline="")
        icon(c, "alert", 22, y + 23, warn, scale=0.6, bg=C.WARN_BG)
        self.text(
            c,
            40,
            y + 23,
            "Routines can interrupt what the AC is doing. Nothing here starts on its own.",
            -12,
            warn,
            weight="semibold",
            width=WIDTH - 56,
        )
        y += 46 + 16
        # Air filter status from the AC's own reminder.
        reminder = any(alert.get("kind") == "filter" for alert in self.app.selected.get("alerts", []))
        color = C.WARN_TEXT if reminder else C.OK
        tint = blend(color, C.CARD, 0.12)
        rounded(c, 18, y + 18, 114, y + 114, 22, fill=tint, outline="")
        icon(c, "filter", 66, y + 66, color, scale=1.9, bg=tint)
        self.text(c, 132, y + 36, "Air filter", -17, weight="black")
        detail = (
            "The AC reports that its filter needs cleaning."
            if reminder
            else "The unit hasn’t asked for a clean. When it does, a reminder shows on the dashboard."
        )
        self.text(c, 132, y + 50, detail, -12, C.MUTED, "nw", width=WIDTH - 150)
        label = tr(c, "Clean the air filter" if reminder else "No reminder")
        chip = measure(c, label, -11, "black") + 34
        chip_fill = blend(color, C.CARD, 0.16)
        rounded(c, 132, y + 88, 132 + chip, y + 112, 12, fill=chip_fill, outline="")
        icon(c, "alert" if reminder else "check", 146, y + 100, color, scale=0.42, bg=chip_fill)
        self.text(c, 156, y + 100, label, -11, color, weight="black", translate=False)
        self.card(c, 0, y, WIDTH, y + 132, 22)
        y += 132 + 16
        items = [dict(item, section="maintenance") for item in section_items(self.app.selected, "maintenance")]
        self.visible_items = items
        if not items:
            self.text(c, WIDTH / 2, y + 30, "No maintenance functions are exposed by your AC.", -13, C.MUTED, "center")
            return y + 60
        section_label(c, 4, y + 7, "Cleaning routines")
        y += 24
        if self.history_state is None:
            # After this draw: a preview answers at once and redraws.
            self.history_state = "queued"
            self.window.after_idle(self.load_routine_history)
        runs = self.app.memory.routine_runs(self.app.selected["id"])
        width = (WIDTH - 10) / 2
        palette = ("cool", "heat", "dry", "fan", "auto")
        for index, item in enumerate(items):
            bx, by = (index % 2) * (width + 10), y + (index // 2) * ROUTINE_STEP
            color = accent(palette[index % len(palette)])
            tint = self.app.soft(color)
            rounded(c, bx, by, bx + width, by + ROUTINE_STEP - 10, 20, fill=C.CARD, outline="")
            rounded(c, bx + 16, by + 16, bx + 72, by + 72, 16, fill=tint, outline="")
            icon(c, glyph_for(item["label"]), bx + 44, by + 44, color, scale=1.1, bg=tint)
            self.text(c, bx + 16, by + 92, item["label"], -15, weight="black", width=width - 32)
            if item["kind"] == "setting":
                detail = item.get("description") or tr(c, option_label(item["spec"], self.app.current(item["key"])))
            else:
                detail = "Cleaning / service routine"
            self.text(c, bx + 16, by + 108, detail, -12, C.MUTED, "nw", width=width - 32)
            # How long since the routine last ran: hOn's history, runs started or seen here, or a
            # date the person set. Selecting the line sets the date.
            when = runs.get(item_routine(item))
            if when is None and self.history_state in {"queued", "loading"}:
                elapsed = tr(c, "Checking the last run…")
            else:
                elapsed = last_run_label(c, when)
            icon(c, "clock", bx + 24, by + 154, color if when else C.MUTED, scale=0.5, bg=C.CARD)
            self.text(
                c,
                bx + 36,
                by + 154,
                elapsed,
                -11,
                C.TEXT if when else C.MUTED,
                weight="bold",
                width=width - 66,
                translate=False,
            )
            icon(c, "next", bx + width - 22, by + 154, C.MUTED, scale=0.45, bg=C.CARD)
            self.hit(
                (bx, by + 140, bx + width, by + 168), lambda item=item, color=color: self.edit_last_run(item, color)
            )
            state = self.started.get(item["label"])
            top = by + 170
            if state:
                fill = blend(C.OK, C.CARD, 0.14)
                rounded(c, bx + 16, top, bx + width - 16, top + 40, 12, fill=fill, outline="")
                shown = tr(c, state)
                left = bx + width / 2 - (measure(c, shown, -13, "black") + 20) / 2
                icon(c, "check", left + 7, top + 20, C.OK, scale=0.5, bg=fill)
                self.text(c, left + 20, top + 20, shown, -13, C.OK, "w", "black", translate=False)
            else:
                label = "Turn on" if item["kind"] == "setting" else "Start"
                rounded(c, bx + 16, top, bx + width - 16, top + 40, 12, fill=color, outline="")
                self.text(c, bx + width / 2, top + 20, label, -13, C.ON_BRAND, "center", "black")
                self.hit((bx + 16, top, bx + width - 16, top + 40), lambda item=item: self.start_routine(item))
        return y + ((len(items) + 1) // 2) * ROUTINE_STEP

    def edit_last_run(self, item, color):
        """Set when a routine last ran, for runs this app could not see (hOn does not keep them)."""
        from datetime import date

        from ..routine_history import day_to_time, parse_day

        routine = item_routine(item)
        known = self.app.memory.routine_runs(self.app.selected["id"]).get(routine)
        field = tk.StringVar(value=known.astimezone().strftime("%d/%m/%Y") if known else "")
        self.date_error = False

        def pick(days_ago):
            field.set((date.today() - timedelta(days=days_ago)).strftime("%d/%m/%Y"))
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
            rounded(c, 24, y, 92, y + 68, 20, fill=tint, outline="")
            icon(c, "calendar", 58, y + 34, color, scale=1.1, bg=tint)
            self.text(c, 108, y + 12, tr(c, "Last run").upper(), -11, color, weight="black", translate=False)
            self.text(c, 108, y + 40, item["label"], -22, weight="black", width=width - 132)
            y += 68 + 18
            self.text(
                c,
                24,
                y + 10,
                "hOn does not keep past cleaning runs. Set when this one last ran.",
                -13,
                C.MUTED,
                "w",
                width=width - 48,
            )
            y += 36
            # Quick picks, then the date itself (day/month/year).
            x = 24
            for label, days_ago in (("Today", 0), ("Yesterday", 1)):
                caption = tr(c, label)
                chip = measure(c, caption, -13, "bold") + 32
                rounded(c, x, y, x + chip, y + 40, 12, fill=C.SURFACE, outline="")
                self.text(c, x + chip / 2, y + 20, caption, -13, C.TEXT, "center", "bold", translate=False)
                self.sheet_hit((x, y, x + chip, y + 40), lambda days_ago=days_ago: pick(days_ago))
                x += chip + 8
            entry = getattr(self, "date_entry", None)
            if entry is None or not entry.winfo_exists():
                entry = tk.Entry(c, textvariable=field, relief="flat", bd=0, font=font(-15, "bold"), justify="center")
                entry.bind("<Return>", lambda event: save())
                self.date_entry = entry
                self.sheet["widgets"].append(entry)
            outline = C.DANGER_TEXT if self.date_error else C.STRONG
            rounded(c, x, y, width - 24, y + 40, 12, fill=C.SURFACE, outline=outline, width=1.2)
            entry.configure(bg=C.SURFACE, fg=C.TEXT, insertbackground=C.TEXT)
            c.create_window((x + width - 24) / 2, y + 20, window=entry, width=width - 24 - x - 24, height=28)
            y += 40 + 10
            hint = (
                "Enter a past date as day/month/year, for example 06/12/2025."
                if self.date_error
                else "Day/month/year, for example 06/12/2025."
            )
            self.text(c, 24, y + 8, hint, -12, C.DANGER_TEXT if self.date_error else C.MUTED, "w", width=width - 48)
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
            from ..diagnostics import diagnostics

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
            rounded(c, 24, y, 92, y + 68, 20, fill=tint, outline="")
            icon(c, glyph_for(item["label"]), 58, y + 34, color, scale=1.25, bg=tint)
            self.text(c, 108, y + 12, tr(c, "Maintenance routine").upper(), -11, color, weight="black", translate=False)
            self.text(c, 108, y + 40, item["label"], -22, weight="black", width=width - 132)
            y += 68 + 20
            rounded(c, 24, y, width - 24, y + 48, 14, fill=C.WARN_BG, outline="")
            icon(c, "alert", 46, y + 24, C.WARN_TEXT, scale=0.55, bg=C.WARN_BG)
            self.text(
                c,
                64,
                y + 24,
                "It may interrupt what the AC is doing.",
                -12,
                C.WARN_TEXT,
                weight="semibold",
                width=width - 100,
            )
            y += 48 + 20
            return self.sheet_buttons(
                c, y, width, "Cancel", "Turn on" if turn_on else "Start", lambda: self.run_routine(item), 1.4
            )

        self.open_sheet(draw)

    def run_routine(self, item):
        self.close_sheet()
        if item["kind"] == "setting":
            value = next((option for option in item["spec"]["options"].values() if code(option) == "1"), "1")
            self.app.action("configure", {item["key"]: value})
        else:
            saved = self.app.memory.function_values(self.app.selected["id"], item["command"], item["form"])
            parameters = {
                spec["key"]: saved.get(spec["key"], spec.get("value")) for spec in item["form"].get("parameters", [])
            }
            self.app.action(
                "execute",
                {
                    "command": item["command"],
                    "category": item["form"]["category"],
                    "parameters": {key: value for key, value in parameters.items() if value is not None},
                },
            )
        self.started[item["label"]] = "Preview only" if self.app.demo else "Started"
        self.render(keep_scroll=True)
