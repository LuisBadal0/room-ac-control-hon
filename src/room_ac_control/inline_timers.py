"""One-time AC schedule controls embedded below the temperature slider."""
from .i18n import tr, refresh_on_language, translator
from datetime import datetime, timedelta
import tkinter as tk

from .theme import C, font, rounded, icon, measure, refresh_on_theme


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

    def __init__(self, parent, action, changed):
        super().__init__(parent, width=248, height=self.HEIGHT, highlightthickness=0, takefocus=True)
        self.action, self.changed = action, changed
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

    def run(self, stop=False):
        if self.supported and not self.busy:
            self.changed(self.action, None if stop else next_time(self.hour.value, self.minute.value))
        return "break"

    def click(self, event):
        if self.in_button(event.x, event.y):
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
        once = tr(self, "Once")
        chip = measure(self, once, 8, "bold")
        rounded(self, width-26-chip, 12, width-12, 34, 10, fill=C.CARD if active else C.SURFACE, outline="")
        self.create_text(width-19, 23, text=once, anchor="e", fill=C.TEXT, font=font(8, "bold"))
        for x, wheel in ((14, self.hour), (76, self.minute)):
            wheel.surface, wheel.pill = surface, (C.CARD if active else C.SURFACE)
            wheel.tone, wheel.enabled = C.TEXT, not self.busy
            wheel.draw()
            self.create_window(x, 38, window=wheel, anchor="nw")
        self.create_text(69, 70, text=":", fill=ink, font=font(16, "black"))
        enabled = self.supported and not self.busy
        button = "Stop" if active and not self.draft else "Set" if self.supported else "Unavailable"
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
            hint = "Select a time" if self.supported else self.hint or "Timers unavailable · Refresh"
            self.create_text(14, 118, text=tr(self, hint), anchor="w", fill=C.MUTED, font=font(9), width=width-28)
        # An edited active timer retains an independent Stop button.
        if active and self.draft:
            self.create_text(width-16, 118, text=tr(self, "Stop"), anchor="e", fill=C.ON_SOFT, font=font(9, "bold"), tags="stop")
            self.tag_bind("stop", "<Button-1>", lambda e: self.run(stop=True))


class InlineTimers(tk.Frame):
    def __init__(self, app):
        super().__init__(app.canvas, bg=C.BG, width=520, height=TimerCard.HEIGHT)
        refresh_on_theme(self, lambda: self.configure(bg=C.BG))
        self.app = app
        self.device = None
        self.cards = {}
        self.columnconfigure(0, weight=1, uniform="timers")
        self.columnconfigure(1, weight=1, uniform="timers")
        for index, action in enumerate(("on", "off")):
            self.cards[action] = TimerCard(self, action, app.change_timer)
            self.cards[action].grid(row=0, column=index, sticky="ew", padx=(0, 6) if not index else (6, 0))

    def refresh(self, snapshot, busy):
        device = snapshot["id"]
        if device != self.device:
            for action, card in self.cards.items():
                card.draft = False
                card.hour.cancel_drag()
                card.minute.cancel_drag()
                card.hour.value, card.minute.value = (8 if action == "on" else 22), 0
            self.device = device
        status = self.app.preview_timers.get(device, {}) if self.app.demo else snapshot.get("timers", {}).get("values", {})
        for action, card in self.cards.items():
            item = status.get(action, {}) if not self.app.demo else {}
            supported = self.app.demo or (snapshot.get("timers", {}).get("available", False) and item.get("supported", False))
            hint = "Manage timers in hOn" if item.get("count", 0) > 1 else snapshot.get("timers", {}).get("error", "Timers unavailable · Refresh")
            card.set_status(supported, status.get(action) if self.app.demo else item.get("due"), busy, hint, self.app.demo)
