"""The Schedules window: every timer saved in hOn, with repeating schedules editable."""

import tkinter as tk
from tkinter import ttk

from .choice_widgets import SelectField
from .control_choices import mode_icon
from .controller import mode_choices, mode_label
from .i18n import TranslatedVariable, localized, localized_title, refresh_on_language, tr, translator
from .inline_timers import NumberWheel
from .schedules import DAY_NAMES, EVERY_DAY, WEEKDAYS, WEEKEND, clock_text, day_labels
from .smooth import aa_oval, aa_text
from .temperature_wheel import TemperatureWheel
from .theme import C, font, icon, paint, refresh_on_theme, rounded
from .worker import degrees

SIZE = (600, 720)


def days_text(widget, days):
    return ", ".join(tr(widget, label) for label in day_labels(days))


class DayChips(tk.Canvas):
    """Seven day toggles, Monday first as in hOn; at least one stays selected."""

    CHIP = 52

    def __init__(self, parent, days, changed=None, background="BG"):
        super().__init__(
            parent, width=7 * self.CHIP + 6 * 6, height=40, highlightthickness=0, takefocus=True, cursor="hand2"
        )
        self.days, self.changed, self.background = set(days), changed, background
        self.focus_day = min(self.days) if self.days else 0
        self.bind("<Button-1>", self.click)
        self.bind("<Left>", lambda event: self.move(-1))
        self.bind("<Right>", lambda event: self.move(1))
        self.bind("<space>", lambda event: self.toggle(self.focus_day))
        self.bind("<FocusIn>", lambda event: self.draw())
        self.bind("<FocusOut>", lambda event: self.draw())
        refresh_on_language(self, self.draw)
        refresh_on_theme(self, self.draw)
        self.draw()

    def set(self, days):
        self.days = set(days)
        self.draw()
        if self.changed:
            self.changed()

    def move(self, step):
        self.focus_day = (self.focus_day + step) % 7
        self.draw()
        return "break"

    def toggle(self, day):
        if day in self.days and len(self.days) == 1:
            return "break"  # A schedule needs at least one day.
        self.days ^= {day}
        self.focus_day = day
        self.set(self.days)
        return "break"

    def click(self, event):
        self.focus_set()
        day = int(event.x // (self.CHIP + 6))
        if 0 <= day <= 6 and event.x - day * (self.CHIP + 6) <= self.CHIP:
            self.toggle(day)

    def draw(self):
        self.delete("all")
        self.configure(bg=getattr(C, self.background))
        focused = self.focus_get() is self
        for day, name in enumerate(DAY_NAMES):
            x = day * (self.CHIP + 6)
            selected = day in self.days
            outline = C.BRAND if focused and day == self.focus_day else (C.BRAND if selected else C.EDGE)
            rounded(
                self,
                x + 1,
                2,
                x + self.CHIP - 1,
                38,
                12,
                fill=C.BRAND if selected else C.CARD,
                outline=outline,
                width=2 if focused and day == self.focus_day else 1,
                tags=(f"day-{day}",),
            )
            aa_text(
                self,
                x + self.CHIP / 2,
                20,
                text=tr(self, name),
                fill=C.ON_BRAND if selected else C.TEXT,
                font=font(9, "bold"),
                tags=(f"day-{day}",),
            )


class DayPicker:
    """A small dialog that chooses repeat days for a Start at or End at card."""

    def __init__(self, parent, days, chosen):
        self.chosen = chosen
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        localized_title(self.window, "Choose days")
        paint(self.window, bg="BG")
        self.window.transient(parent.winfo_toplevel())
        self.window.resizable(False, False)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        from .window_header import WindowHeader

        self.header = WindowHeader(self.window, "Choose days", self.close, maximize=False)
        body = paint(tk.Frame(self.window, padx=22, pady=16), bg="BG")
        body.pack(fill="both", expand=True)
        localized(
            paint(tk.Label(body, text="Choose days", font=font(18, "black"), anchor="w"), bg="BG", fg="TEXT")
        ).pack(fill="x")
        localized(
            paint(
                tk.Label(body, text="The schedule repeats on these days.", font=font(10), anchor="w"),
                bg="BG",
                fg="MUTED",
            )
        ).pack(fill="x", pady=(2, 16))
        self.chips = DayChips(body, days or WEEKDAYS)
        self.chips.pack(anchor="w")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(18, 0))
        localized(ttk.Button(buttons, text="Done", style="Accent.TButton", command=self.done)).pack(side="right")
        localized(ttk.Button(buttons, text="Cancel", command=self.close)).pack(side="right", padx=(0, 8))
        self.window.update_idletasks()
        owner = parent.winfo_toplevel()
        x = max(0, owner.winfo_rootx() + (owner.winfo_width() - self.window.winfo_reqwidth()) // 2)
        y = max(0, owner.winfo_rooty() + (owner.winfo_height() - self.window.winfo_reqheight()) // 2)
        self.window.geometry(f"+{x}+{y}")
        self.chips.focus_set()

    def done(self):
        days = tuple(sorted(self.chips.days))
        self.close()
        self.chosen(days)

    def close(self):
        if self.window.winfo_exists():
            self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()


class ScheduleRow(tk.Canvas):
    HEIGHT = 96

    def __init__(self, view, row):
        super().__init__(view.inner, height=self.HEIGHT, highlightthickness=0)
        self.view, self.row = view, row
        self.bind("<Configure>", lambda event: self.draw())
        refresh_on_language(self, self.draw)
        refresh_on_theme(self, self.draw)
        # Handlers are named on_* so they never shadow Canvas methods such as delete().
        for tag, action in (("toggle", self.on_toggle), ("edit", self.on_edit), ("delete", self.on_delete)):
            self.tag_bind(tag, "<Button-1>", lambda event, action=action: action())
            self.tag_bind(tag, "<Enter>", lambda event: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda event: self.configure(cursor=""))

    def on_toggle(self):
        if not self.view.busy:
            self.view.set_active(self.row, not self.row["active"])

    def on_edit(self):
        if not self.view.busy:
            self.view.edit(self.row)

    def on_delete(self):
        if not self.view.busy:
            self.view.delete(self.row)

    def title(self):
        start, end = self.row["start"], self.row["end"]
        if start and end:
            return f"{clock_text(start)}  →  {clock_text(end)}"
        if start:
            return tr(self, f"On at {clock_text(start)}")
        return tr(self, f"Off at {clock_text(end)}")

    def when(self):
        row = self.row
        if row["kind"] == "repeat":
            text = days_text(self, row["days"])
        elif row["kind"] == "once":
            text = tr(self, "Once") + " · " + translator(self).date(row["due"])
        else:
            text = tr(self, "A repeat this app does not edit")
        return text + (" · " + tr(self, "Paused") if not row["active"] else "")

    def settings(self):
        row = self.row
        if not row["start"]:
            return tr(self, "Turns the AC off")
        parts = [tr(self, row["mode"])] if row.get("mode") else []
        if "temperature" in row:
            parts.append(translator(self).number(degrees(row["temperature"])))
        return " · ".join(parts) or tr(self, "Turns the AC on")

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        width = max(self.winfo_width(), 420)
        row, active = self.row, self.row["active"]
        surface = C.CARD if active else C.SURFACE
        ink = C.TEXT if active else C.MUTED
        rounded(self, 1, 1, width - 1, self.HEIGHT - 1, 12, fill=surface, outline=C.EDGE)
        circle = C.SOFT if active else C.RAISED
        aa_oval(self, 16, 16, 52, 52, fill=circle, outline="")
        icon(self, "clock", 34, 34, C.ON_SOFT if active else C.MUTED, scale=0.7, bg=circle)
        aa_text(self, 66, 24, text=self.title(), anchor="w", fill=ink, font=font(14, "black"))
        aa_text(self, 66, 49, text=self.when(), anchor="w", fill=C.MUTED, font=font(9), tags=("when",))
        aa_text(self, 66, 72, text=self.settings(), anchor="w", fill=ink, font=font(9, "bold"))
        right = width - 16
        if row["kind"] == "other":
            aa_text(self, right, 48, text=tr(self, "Manage in hOn"), anchor="e", fill=C.MUTED, font=font(9))
            return
        delete = aa_text(
            self, right, 72, text=tr(self, "Delete"), anchor="e", fill=C.DANGER, font=font(9, "bold"), tags=("delete",)
        )
        if row["kind"] == "repeat":
            left = self.bbox(delete)[0]
            aa_text(
                self,
                left - 18,
                72,
                text=tr(self, "Edit"),
                anchor="e",
                fill=C.BRAND,
                font=font(9, "bold"),
                tags=("edit",),
            )
            on = row["active"]
            rounded(self, right - 44, 14, right, 38, 12, fill=C.BRAND if on else C.FIELD, outline="", tags=("toggle",))
            aa_oval(
                self,
                right - 22 if on else right - 42,
                16,
                right - 2 if on else right - 22,
                36,
                fill=C.THUMB,
                outline="",
                tags=("toggle",),
            )


class SchedulesView:
    def __init__(self, app, parent=None):
        self.app = app
        self.rows = []
        self.busy = False
        self.editing = None
        self.in_editor = False
        self.on_close = None  # All functions reloads its Schedules tab when the editor closes.
        # Opened from All functions, it sits above that window and returns to it.
        parent = parent or app.root
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        app.schedules_view = self
        localized_title(self.window, "Room AC Control · Schedules")
        self.window.geometry("{}x{}".format(*SIZE))
        self.window.resizable(False, False)
        paint(self.window, bg="BG")
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        from .window_header import WindowHeader

        self.header = WindowHeader(
            self.window,
            "Room AC Control · Schedules",
            self.close,
            maximize=False,
            size=SIZE,
            owner=parent.winfo_toplevel(),
        )
        self.body = ttk.Frame(self.window, padding=(24, 4, 24, 20))
        self.body.pack(fill="both", expand=True)
        localized(ttk.Label(self.body, text="Schedules", font=font(21, "black"))).pack(anchor="w")
        selected = app.selected
        ttk.Label(self.body, text=f"{selected['name']} · {selected['model']}", style="Muted.TLabel").pack(
            anchor="w", pady=(2, 0)
        )
        localized(ttk.Label(self.body, text="Saved in hOn, so they work with your PC off.", style="Muted.TLabel")).pack(
            anchor="w", pady=(0, 10)
        )
        self.note = tk.StringVar()
        self.note_display = TranslatedVariable(self.window, self.note)
        note = tk.Label(
            self.body,
            textvariable=self.note_display,
            font=font(9),
            anchor="w",
            justify="left",
            padx=12,
            pady=8,
            wraplength=520,
            bd=0,
        )
        paint(note, bg="SOFT", fg="ON_SOFT")
        note.pack(fill="x", pady=(0, 12))
        area = ttk.Frame(self.body)
        area.pack(fill="both", expand=True)
        self.scroll = paint(tk.Canvas(area, highlightthickness=0), bg="BG")
        self.bar = ttk.Scrollbar(area, orient="vertical", command=self.scroll.yview)
        self.scroll.pack(side="left", fill="both", expand=True)
        self.scroll.configure(yscrollcommand=self.bar.set)
        self.inner = ttk.Frame(self.scroll)
        self.inner_id = self.scroll.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self.update_scroll_region)
        self.scroll.bind(
            "<Configure>",
            lambda event: (self.scroll.itemconfigure(self.inner_id, width=event.width), self.update_scroll_region()),
        )
        self.window.bind("<MouseWheel>", self.wheel)
        self.footer = ttk.Frame(self.body)
        self.footer.pack(fill="x", pady=(14, 0))
        self.new_button = ttk.Button(self.footer, style="Accent.TButton", command=self.primary)
        refresh_on_language(self.new_button, self.update_primary)
        self.update_primary()
        self.new_button.pack(side="left", expand=True, fill="x", padx=(0, 10))
        localized(ttk.Button(self.footer, text="Close", command=self.close)).pack(side="right")
        self.refresh_button = localized(
            ttk.Button(self.footer, text="↻ Refresh", style="Ghost.TButton", command=self.load)
        )
        self.refresh_button.pack(side="right", padx=(0, 6))
        self.load()

    def primary(self):
        """The footer's main button: New schedule in the list, Save schedule in the editor."""
        if self.in_editor:
            self.save()
        else:
            self.edit(None)

    def update_primary(self):
        self.new_button.configure(text=tr(self.new_button, "Save schedule" if self.in_editor else "New schedule"))

    # List

    def update_scroll_region(self, event=None):
        height = max(1, self.scroll.winfo_height())
        content = self.inner.winfo_reqheight()
        self.scroll.configure(scrollregion=(0, 0, self.scroll.winfo_width(), max(height, content)))
        if content > height:
            if not self.bar.winfo_manager():
                self.bar.pack(side="right", fill="y", before=self.scroll)
        else:
            self.scroll.yview_moveto(0)
            self.bar.pack_forget()

    def wheel(self, event):
        if self.inner.winfo_reqheight() > self.scroll.winfo_height():
            self.scroll.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def set_busy(self, value, message=None):
        self.busy = value
        state = "disabled" if value else "normal"
        for button in (self.new_button, self.refresh_button):
            if button is not None and button.winfo_exists():
                button.configure(state=state)
        if message:
            self.note.set(message)

    def load(self):
        if self.busy:
            return
        self.editing = None
        self.set_busy(True, "Loading schedules from hOn…")
        self.app.load_schedules(self.loaded, self.failed)

    def loaded(self, rows, message=None):
        if not self.window.winfo_exists():
            return
        self.rows = rows
        self.in_editor = False
        self.update_primary()
        self.set_busy(
            False,
            message
            or (
                "Repeating schedules can be edited, paused or deleted. One-time timers can be deleted."
                if rows
                else "Saved schedules appear here."
            ),
        )
        self.render()

    def failed(self, error):
        if self.window.winfo_exists():
            self.set_busy(False, error)

    def render(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.inner.columnconfigure(0, weight=1)
        self.new_button.configure(state="disabled" if self.busy else "normal")
        for index, row in enumerate(self.rows):
            ScheduleRow(self, row).grid(row=index, column=0, sticky="ew", pady=(0, 10))
        if not self.rows:
            self.empty = localized(
                ttk.Label(
                    self.inner,
                    text="No schedules yet. Create one, or choose a repeat on Start at or End at.",
                    style="Muted.TLabel",
                    wraplength=480,
                    justify="center",
                )
            )
            self.empty.grid(row=0, column=0, pady=60)
        self.scroll.yview_moveto(0)

    def set_active(self, row, active):
        self.set_busy(True, "Resuming the schedule in hOn…" if active else "Pausing the schedule in hOn…")
        self.app.change_schedule(
            "active",
            row["id"],
            lambda rows: self.loaded(
                rows, "Schedule resumed." if active else "Schedule paused. It stays saved in hOn."
            ),
            self.failed,
            active=active,
        )

    def delete(self, row):
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Room AC Control", tr(self.window, "Delete this schedule from hOn?"), parent=self.window
        ):
            return
        self.set_busy(True, "Deleting the schedule in hOn…")
        self.app.change_schedule("delete", row["id"], lambda rows: self.loaded(rows, "Schedule deleted."), self.failed)

    # Editor

    def wheel_pair(self, parent, value):
        frame = paint(tk.Frame(parent), bg="BG")
        wheels = []
        for limit, start in ((24, value[0]), (60, value[1])):
            wheel = NumberWheel(frame, limit, start, lambda: None)

            def recolor(wheel=wheel):
                wheel.surface, wheel.pill = C.BG, C.SURFACE
                wheel.draw()

            recolor()
            refresh_on_theme(wheel, recolor)
            wheels.append(wheel)
        wheels[0].pack(side="left")
        colon = paint(tk.Label(frame, text=":", font=font(16, "black")), bg="BG", fg="TEXT")
        colon.pack(side="left", padx=4)
        wheels[1].pack(side="left")
        return frame, wheels

    def edit(self, row):
        if self.busy:
            return
        self.editing = row
        self.in_editor = True
        self.update_primary()
        for child in self.inner.winfo_children():
            child.destroy()
        selected = self.app.selected
        detail = ttk.Frame(self.inner, padding=(4, 0))
        detail.grid(row=0, column=0, sticky="ew")
        localized(ttk.Button(detail, text="‹ Back to schedules", command=lambda: self.loaded(self.rows))).pack(
            anchor="w", pady=(0, 12)
        )
        localized(ttk.Label(detail, text="Edit schedule" if row else "New schedule", style="Heading.TLabel")).pack(
            anchor="w", pady=(0, 10)
        )
        self.times = {}
        defaults = {"on": (row["start"] if row else (7, 0)), "off": (row["end"] if row else (22, 0))}
        enabled = {"on": bool(row["start"]) if row else True, "off": bool(row["end"]) if row else False}
        for action, label in (("on", "Turn on at"), ("off", "Turn off at")):
            line = ttk.Frame(detail)
            line.pack(fill="x", pady=2)
            line.columnconfigure(0, minsize=160)
            variable = tk.BooleanVar(value=enabled[action])
            localized(ttk.Checkbutton(line, text=label, variable=variable)).grid(row=0, column=0, sticky="w")
            frame, wheels = self.wheel_pair(line, defaults[action] or (7, 0))
            frame.grid(row=0, column=1, sticky="w")
            self.times[action] = (variable, wheels)
        localized(ttk.Label(detail, text="Repeat on", font=font(10, "bold"))).pack(anchor="w", pady=(14, 6))
        self.day_chips = DayChips(detail, row["days"] if row else WEEKDAYS)
        self.day_chips.pack(anchor="w")
        shortcuts = ttk.Frame(detail)
        shortcuts.pack(anchor="w", pady=(6, 0))
        for label, days in (("Every day", EVERY_DAY), ("Weekdays", WEEKDAYS), ("Weekend", WEEKEND)):
            localized(
                ttk.Button(
                    shortcuts, text=label, style="Ghost.TButton", command=lambda days=days: self.day_chips.set(days)
                )
            ).pack(side="left", padx=(0, 4))
        localized(ttk.Label(detail, text="When it turns on", font=font(10, "bold"))).pack(anchor="w", pady=(14, 2))
        localized(
            ttk.Label(
                detail,
                text="Fan, airflow and other settings follow what you last used in that mode.",
                style="Muted.TLabel",
                wraplength=520,
            )
        ).pack(anchor="w", pady=(0, 6))
        options = mode_choices(selected)
        self.modes = {option["label"]: option["value"] for option in options}
        current = row.get("mode") if row else mode_label(selected)
        self.mode = tk.StringVar(value=current if current in self.modes else next(iter(self.modes), "Choose…"))
        settings = ttk.Frame(detail)
        settings.pack(fill="x")
        if self.modes:
            SelectField(
                settings,
                self.mode,
                {label: label for label in self.modes},
                "Mode",
                choices=[{"label": label, "value": label, "glyph": mode_icon(label)} for label in self.modes],
            ).pack(side="left", anchor="n")
        self.temperature = None
        spec = selected.get("controls", {}).get("tempSel")
        if spec and spec.get("kind") == "range":
            value = row.get("temperature") if row else None
            self.temperature = TemperatureWheel(settings, spec, value if value is not None else selected.get("target"))
            self.temperature.pack(side="right")
        self.note.set("Changes are saved to hOn when you select Save schedule.")
        self.scroll.yview_moveto(0)

    def request(self):
        """Read the editor: start, end, days and the settings for the start."""
        values = {}
        for action, (variable, wheels) in self.times.items():
            values[action] = (wheels[0].value, wheels[1].value) if variable.get() else None
        requested = {}
        if values["on"]:
            requested = dict(self.modes.get(self.mode.get(), {}))
            if self.temperature is not None and self.temperature.get() is not None:
                requested["tempSel"] = self.temperature.get()
            requested = self.app.memory.mode_values(self.app.selected, requested)
        return values["on"], values["off"], tuple(sorted(self.day_chips.days)), requested

    def save(self):
        if self.busy:
            return
        start, end, days, requested = self.request()
        if start is None and end is None:
            self.note.set("Choose a start time, an end time or both.")
            return
        if start is not None and start == end:
            self.note.set("The start and end times must differ.")
            return
        ident = self.editing["id"] if self.editing else None
        self.set_busy(True, "Saving schedule to hOn…")
        self.app.save_schedule(
            ident,
            start,
            end,
            days,
            requested,
            lambda rows: self.loaded(rows, "Schedule saved in hOn. It works with your PC off."),
            self.failed,
            parent=self.window,
            cancelled=lambda: self.set_busy(False, "Not saved. Adjust the time or days."),
        )

    def close(self):
        self.app.schedules_view = None
        if self.window.winfo_exists():
            self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
        if self.on_close:
            self.on_close()
