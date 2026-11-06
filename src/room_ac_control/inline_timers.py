"""The End at row on the dashboard and the timer cards it is built from; a repeat makes a schedule."""
from .i18n import tr, refresh_on_language, translator
from datetime import datetime, timedelta
import tkinter as tk

from .theme import C, font, rounded, icon, measure, refresh_on_theme, blend


def next_time(hour, minute, now=None):
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Choose a valid 24-hour time.")
    now = now or datetime.now()
    result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return result if result > now else result + timedelta(days=1)


class NumberWheel(tk.Canvas):
    """Drag the numbers vertically, or use a click, wheel or arrow key."""
    ROW_HEIGHT = 26
    DRAG_THRESHOLD = 4
    CLICK_TOP, CLICK_BOTTOM = 16, 52

    def __init__(self, parent, limit, value, changed):
        super().__init__(parent, bg=C.CARD, width=48, height=68, highlightthickness=0, takefocus=True)
        self.limit, self.value, self.changed = limit, value, changed
        self.enabled, self.tone, self.surface, self.pill = True, C.TEXT, C.CARD, C.SURFACE
        self.drag_state, self.drag_offset = None, 0
        self.bind("<MouseWheel>", lambda e: self.step(-1 if e.delta > 0 else 1) if e.delta else None)
        self.bind("<Up>", lambda e: self.step(-1))
        self.bind("<Down>", lambda e: self.step(1))
        self.bind("<Button-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        refresh_on_language(self,self.draw)
        refresh_on_theme(self,self.draw)
        self.draw()

    def step(self, amount):
        self.cancel_drag()
        if self.enabled:
            self.value = self.normalize_value(self.value + amount)
            self.draw()
            self.changed()
        return "break"

    def normalize_value(self, value):
        return value % self.limit

    def cancel_drag(self):
        self.drag_state, self.drag_offset = None, 0

    def press(self, event):
        self.cancel_drag()
        if not self.enabled:
            return "break"
        self.focus_set()
        self.drag_state = {"origin": event.y_root, "value": self.value,
                           "click_y": event.y, "moved": False}
        return "break"

    def drag(self, event):
        if self.drag_state is None or not self.enabled:
            return "break"
        delta = event.y_root - self.drag_state["origin"]
        if abs(delta) < self.DRAG_THRESHOLD and not self.drag_state["moved"]:
            return "break"
        self.drag_state["moved"] = True
        steps = int(-delta / self.ROW_HEIGHT)
        self.drag_offset = delta + steps * self.ROW_HEIGHT
        value = self.normalize_value(self.drag_state["value"] + steps)
        if value != self.value:
            self.value = value
            self.changed()
        self.draw()
        return "break"

    def release(self, event):
        if self.drag_state is None:
            return "break"
        self.drag(event)  # A fast release may arrive without a final motion event.
        state = self.drag_state
        self.cancel_drag()
        if not self.enabled or state is None:
            self.draw()
            return "break"
        if state["moved"]:
            delta = event.y_root - state["origin"]
            rows = -delta / self.ROW_HEIGHT
            steps = int(rows + (0.5 if rows >= 0 else -0.5))
            value = self.normalize_value(state["value"] + steps)
            if value != self.value:
                self.value = value
                self.changed()
        elif state["click_y"] < self.CLICK_TOP:
            self.step(-1)
        elif state["click_y"] > self.CLICK_BOTTOM:
            self.step(1)
        self.draw()
        return "break"

    def draw(self):
        if not self.enabled:
            self.cancel_drag()
        self.delete("all")
        self.configure(bg=self.surface, cursor="sb_v_double_arrow" if self.enabled else "arrow")
        focused = self.focus_get() is self
        rounded(self, 1, 16, 47, 52, 6, fill=self.pill, outline=C.BRAND if focused else "", width=1.5)
        for offset in range(-2, 3):
            y = 34 + offset * self.ROW_HEIGHT + self.drag_offset
            emphasis = max(0, 1 - abs(y - 34) / self.ROW_HEIGHT)
            color = self.tone if emphasis >= 0.5 and self.enabled else self.faint
            self.create_text(24, y, text=tr(self, f"{(self.value + offset) % self.limit:02d}"), fill=color,
                             font=font(round(9 + 8 * emphasis), "black" if emphasis >= 0.5 else "normal"))

    @property
    def faint(self):
        return C.ON_SOFT if self.surface == C.SOFT else C.FAINT


class TimerCard(tk.Canvas):
    HEIGHT = 138

    def __init__(self, parent, action, changed, scheduled=None, choose_repeat=None):
        super().__init__(parent, width=248, height=self.HEIGHT, highlightthickness=0, takefocus=True)
        self.action, self.changed = action, changed
        # () is a one-time timer; days (0 = Monday) save a repeating schedule instead.
        self.scheduled, self.choose_repeat, self.repeat = scheduled, choose_repeat, ()
        self.chip_box = (0, 0, 0, 0)
        self.active, self.supported, self.busy, self.draft = False, False, False, False
        self.hover, self.due = False, None
        self.hint, self.preview = "", False
        self.hour = NumberWheel(self, 24, 8 if action == "on" else 22, self.edited)
        self.minute = NumberWheel(self, 60, 0, self.edited)
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Motion>", self.motion)
        self.bind("<Leave>", lambda e: self.highlight(False))
        self.bind("<Button-1>", self.click)
        self.bind("<Return>", lambda e: self.run(stop=self.active and not self.draft))
        self.bind("<space>", lambda e: self.run(stop=self.active and not self.draft))
        refresh_on_language(self,self.draw)
        refresh_on_theme(self,self.draw)
        self.draw()

    def edited(self):
        self.draft = True
        self.draw()

    def set_repeat(self, days):
        self.repeat = tuple(sorted(days))
        self.edited()

    def repeat_label(self):
        if not self.repeat:
            return tr(self, "Once")
        from .schedules import day_labels
        labels = day_labels(self.repeat)
        if len(labels) > 3:
            return tr(self, f"{len(labels)} days")
        return ", ".join(tr(self, label) for label in labels)

    def in_chip(self, x, y):
        x1, y1, x2, y2 = self.chip_box
        return x1 <= x <= x2 and y1 - 4 <= y <= y2 + 4

    def set_status(self, supported, due, busy, hint="", preview=False):
        self.supported, self.busy = supported, busy
        self.hint, self.preview = hint, preview
        self.due = due
        self.active = due is not None and due > datetime.now()
        if due and not self.draft and self.hour.drag_state is None and self.minute.drag_state is None:
            self.hour.value, self.minute.value = due.hour, due.minute
        self.draw()

    def highlight(self, value):
        if self.hover != value:
            self.hover = value
            self.draw()

    def in_button(self, x, y):
        return x >= self.card_width()-86 and 50 <= y <= 94

    def motion(self, event):
        self.highlight(self.in_button(event.x, event.y))
        chip = self.choose_repeat is not None and self.supported and not self.busy and self.in_chip(event.x, event.y)
        self.configure(cursor="hand2" if chip else "")

    def run(self, stop=False):
        if self.supported and not self.busy:
            if self.repeat and not stop and self.scheduled:
                self.scheduled(self.action, (self.hour.value, self.minute.value), self.repeat)
            else:
                self.changed(self.action, None if stop else next_time(self.hour.value, self.minute.value))
        return "break"

    def click(self, event):
        if self.choose_repeat and self.supported and not self.busy and self.in_chip(event.x, event.y):
            self.choose_repeat(self)
        elif self.in_button(event.x, event.y):
            self.run(stop=self.active and not self.draft)

    def card_width(self):
        width = self.winfo_width()
        return width if width > 1 else int(self.cget("width"))

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        width = self.card_width()
        active = self.active
        surface = C.SOFT if active else C.CARD
        ink = C.ON_SOFT if active else C.TEXT
        rounded(self, 1, 1, width-1, self.HEIGHT-1, 12, fill=surface, outline=C.BRAND if active else C.EDGE)
        icon(self, "clock", 24, 23, C.ON_SOFT if active else C.MUTED, scale=.78, bg=surface)
        self.create_text(40, 23, text=tr(self, "Start at" if self.action == "on" else "End at"), anchor="w",
                         fill=ink, font=font(10, "bold"))
        repeat = self.repeat_label() + ("  ▾" if self.choose_repeat else "")
        chip = measure(self, repeat, 8, "bold")
        self.chip_box = (width-26-chip, 12, width-12, 34)
        chip_fill = C.BRAND if self.repeat else (C.CARD if active else C.SURFACE)
        rounded(self, *self.chip_box, 10, fill=chip_fill, outline="", tags=("repeat",))
        self.create_text(width-19, 23, text=repeat, anchor="e", fill=C.ON_BRAND if self.repeat else C.TEXT,
                         font=font(8, "bold"), tags=("repeat",))
        for x, wheel in ((14, self.hour), (76, self.minute)):
            wheel.surface, wheel.pill = surface, (C.CARD if active else C.SURFACE)
            wheel.tone, wheel.enabled = C.TEXT, not self.busy
            wheel.draw()
            self.create_window(x, 38, window=wheel, anchor="nw")
        self.create_text(69, 70, text=":", fill=ink, font=font(16, "black"))
        enabled = self.supported and not self.busy
        button = "Stop" if active and not self.draft and not self.repeat else "Set" if self.supported else "Unavailable"
        hover = self.hover and enabled
        rounded(self, width-86, 54, width-14, 90, 12,
                fill=(C.CARD if active else C.SURFACE) if hover else surface,
                outline=(ink if enabled else C.EDGE), width=1.5)
        self.create_text(width-50, 72, text=tr(self, button), fill=ink if enabled else C.MUTED,
                         font=font(9, "bold"))
        if active:
            hint = ("Preview · " if self.preview else "Saved · ") + translator(self).date(self.due)
            icon(self, "check", 21, 118, C.ON_SOFT, scale=.6, bg=surface)
            self.create_text(30, 118, text=tr(self, hint), anchor="w", fill=C.ON_SOFT, font=font(9, "bold"))
        else:
            hint = ("Saves a repeating schedule" if self.repeat else "Select a time") if self.supported else self.hint or "Timers unavailable · Refresh"
            self.create_text(14, 118, text=tr(self, hint), anchor="w", fill=C.MUTED, font=font(9), width=width-28)
        # An edited active timer retains an independent Stop button.
        if active and self.draft:
            self.create_text(width-16, 118, text=tr(self, "Stop"), anchor="e", fill=C.ON_SOFT, font=font(9, "bold"), tags="stop")
            self.tag_bind("stop", "<Button-1>", lambda e: self.run(stop=True))


class SlotWheel(NumberWheel):
    """The End at row's 46×72 wheel: the chosen number in a band, neighbours above and below."""
    ROW_HEIGHT = 24
    CLICK_TOP, CLICK_BOTTOM = 24, 48

    def __init__(self, parent, limit, value, changed):
        super().__init__(parent, limit, value, changed)
        self.configure(width=46, height=72)
        self.draw()

    def draw(self):
        if not self.enabled:
            self.cancel_drag()
        self.delete("all")
        self.configure(bg=self.surface, cursor="sb_v_double_arrow" if self.enabled else "arrow")
        focused = self.focus_get() is self
        rounded(self, 0, 24, 46, 48, 8, fill=self.pill, outline=C.BRAND if focused else "", width=1.5)
        for offset in range(-2, 3):
            y = 36 + offset*self.ROW_HEIGHT + self.drag_offset
            distance = abs(y-36)/self.ROW_HEIGHT
            if distance < .5:
                size, weight, color = -20, "black", self.tone if self.enabled else C.MUTED
            elif distance < 1.5:
                size, weight, color = -13, "semibold", C.MUTED
            else:
                size, weight, color = -11, "semibold", C.FAINT
            self.create_text(23, y, text=f"{(self.value + offset) % self.limit:02d}", fill=color, font=font(size, weight))


class EndAtCard(TimerCard):
    """The dashboard's End at row: a turn-off time on two drag wheels, a repeat chip and Set."""
    HEIGHT = 84
    BUTTON = 64

    def __init__(self, parent, changed, scheduled=None, choose_repeat=None, tone=None):
        super().__init__(parent, "off", changed, scheduled, choose_repeat)
        self.tone = tone or (lambda: C.BRAND)
        for wheel in (self.hour, self.minute):
            wheel.destroy()
        self.hour = SlotWheel(self, 24, 22, self.edited)
        self.minute = SlotWheel(self, 60, 0, self.edited)
        self.configure(width=500)
        self.draw()

    def in_button(self, x, y):
        width = self.card_width()
        return width-10-self.BUTTON <= x <= width-10 and 22 <= y <= 62

    def hint_text(self):
        if self.active:
            if self.preview:
                return tr(self, "Preview · ") + translator(self).date(self.due)
            day = self.due.date()
            today = datetime.now().date()
            time = f"{self.due.hour:02d}:{self.due.minute:02d}"
            if day == today:
                return tr(self, "Turns off today at {time}").format(time=time)
            if day == today+timedelta(days=1):
                return tr(self, "Turns off tomorrow at {time}").format(time=time)
            return tr(self, "Saved · ") + translator(self).date(self.due)
        if not self.supported:
            return tr(self, self.hint or "Timers unavailable · Refresh")
        return tr(self, "Saves a repeating schedule" if self.repeat else "Drag or scroll the time")

    def draw(self):
        if not hasattr(self, "tone"):
            return  # TimerCard draws once before the wheels are swapped in.
        self.delete("all")
        self.configure(bg=C.BG)
        width = self.card_width()
        active, tone = self.active, self.tone()
        surface = blend(tone, C.CARD, .14 if C.mode == "dark" else .10) if active else C.CARD
        rounded(self, 1, 1, width-1, self.HEIGHT-1, 18, fill=surface,
                outline=blend(tone, C.BG, .5) if active else surface, width=1)
        rounded(self, 12, 26, 44, 58, 10, fill=tone if active else C.SURFACE, outline="")
        icon(self, "clock", 28, 42, C.ON_BRAND if active else C.MUTED, scale=.62, bg=tone if active else C.SURFACE)
        # Right to left: Set/Stop, the repeat chip, then the minute and hour wheels.
        button_left = width-10-self.BUTTON
        repeat = self.repeat_label()
        chip = measure(self, repeat, -12, "bold")+30
        self.chip_box = (button_left-8-chip, 27, button_left-8, 57)
        chip_fill = tone if self.repeat else C.SURFACE
        chip_ink = C.ON_BRAND if self.repeat else C.MUTED
        rounded(self, *self.chip_box, 15, fill=chip_fill, outline="", tags=("repeat",))
        self.create_text(self.chip_box[0]+10, 42, text=repeat, anchor="w", fill=chip_ink, font=font(-12, "bold"), tags=("repeat",))
        icon(self, "chevron", self.chip_box[2]-13, 43, chip_ink, scale=.42, bg=chip_fill, tags=("repeat",))
        minute_x = self.chip_box[0]-8-46
        hour_x = minute_x-8-8-46
        for x, wheel in ((hour_x, self.hour), (minute_x, self.minute)):
            wheel.surface, wheel.pill = surface, C.SURFACE
            wheel.tone, wheel.enabled = tone if active else C.TEXT, not self.busy
            wheel.draw()
            self.create_window(x, 6, window=wheel, anchor="nw")
        self.create_text(minute_x-8, 41, text=":", fill=C.MUTED, font=font(-18, "black"))
        text_width = max(40, hour_x-60)
        self.create_text(52, 33, text=tr(self, "End at"), anchor="w", fill=C.TEXT, font=font(-13, "bold"), width=text_width)
        self.create_text(52, 51, text=self.hint_text(), anchor="w", fill=tone if active else C.MUTED,
                         font=font(-11, "semibold"), width=text_width)
        enabled = self.supported and not self.busy
        stop = active and not self.draft and not self.repeat
        label = tr(self, "Stop" if stop else "Set" if self.supported else "Unavailable")
        hover = self.hover and enabled
        if not enabled:
            fill, ink, outline = C.SURFACE, C.FAINT, C.SURFACE
        elif stop:
            fill, ink, outline = (blend(tone, surface, .15) if hover else surface), tone, tone
        else:
            fill, ink, outline = (blend(C.TEXT, C.BG, .85) if hover else C.TEXT), C.BG, C.TEXT
        rounded(self, button_left, 22, width-10, 62, 12, fill=fill, outline=outline, width=1.5)
        self.create_text(button_left+self.BUTTON/2, 42, text=label, fill=ink, font=font(-13, "black"))
        # An edited active timer retains an independent Stop action.
        if active and self.draft:
            self.create_text(52, 70, text=tr(self, "Stop"), anchor="w", fill=tone, font=font(-11, "bold"), tags="stop")
            self.tag_bind("stop", "<Button-1>", lambda e: self.run(stop=True))


class InlineTimers(tk.Frame):
    """The End at row on the dashboard. Start times are set in Schedules."""
    def __init__(self, app):
        super().__init__(app.canvas, bg=C.BG, width=500, height=EndAtCard.HEIGHT)
        refresh_on_theme(self, lambda: self.configure(bg=C.BG))
        self.app = app
        self.device = None
        self.columnconfigure(0, weight=1)
        self.cards = {"off": EndAtCard(self, app.change_timer, app.save_repeating_timer, app.timer_repeat_menu,
                                       tone=app.dial_accent)}
        self.cards["off"].grid(row=0, column=0, sticky="ew")

    def refresh(self, snapshot, busy):
        device = snapshot["id"]
        if device != self.device:
            for action, card in self.cards.items():
                card.draft, card.repeat = False, ()
                card.hour.cancel_drag()
                card.minute.cancel_drag()
                card.hour.value, card.minute.value = (8 if action == "on" else 22), 0
            self.device = device
        status = self.app.preview_timers.get(device, {}) if self.app.demo else snapshot.get("timers", {}).get("values", {})
        for action, card in self.cards.items():
            item = status.get(action, {}) if not self.app.demo else {}
            supported = self.app.demo or (snapshot.get("timers", {}).get("available", False) and item.get("supported", False))
            hint = "Manage timers in Schedules" if item.get("count", 0) > 1 else snapshot.get("timers", {}).get("error", "Timers unavailable · Refresh")
            card.set_status(supported, status.get(action) if self.app.demo else item.get("due"), busy, hint, self.app.demo)
