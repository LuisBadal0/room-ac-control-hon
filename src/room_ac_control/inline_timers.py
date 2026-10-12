"""One-time AC schedule controls embedded below the temperature slider."""
from datetime import datetime, timedelta
import tkinter as tk

from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, GREEN, rounded, icon

ACTIVE = "#25392d"


def next_time(hour, minute, now=None):
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Choose a valid 24-hour time.")
    now = now or datetime.now()
    result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return result if result > now else result + timedelta(days=1)


class NumberWheel(tk.Canvas):
    """Three visible numbers; wheel/arrow keys select the central number."""
    def __init__(self, parent, limit, value, changed):
        super().__init__(parent, bg=CARD, width=45, height=65, highlightthickness=0, takefocus=True)
        self.limit, self.value, self.changed = limit, value, changed
        self.enabled, self.tone, self.surface = True, TEXT, CARD
        self.bind("<MouseWheel>", lambda e: self.step(-1 if e.delta > 0 else 1) if e.delta else None)
        self.bind("<Up>", lambda e: self.step(-1))
        self.bind("<Down>", lambda e: self.step(1))
        self.bind("<Button-1>", self.click)
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        self.draw()

    def step(self, amount):
        if self.enabled:
            self.value = (self.value + amount) % self.limit
            self.draw()
            self.changed()
        return "break"

    def click(self, event):
        self.focus_set()
        if event.y < 22:
            self.step(-1)
        elif event.y > 43:
            self.step(1)

    def draw(self):
        self.delete("all")
        self.configure(bg=self.surface, cursor="hand2" if self.enabled else "arrow")
        if self.focus_get() is self:
            rounded(self, 1, 1, 44, 64, 7, fill="", outline=ACCENT)
        for offset, y, size, color in ((-1, 10, 9, MUTED), (0, 32, 20, self.tone), (1, 54, 9, MUTED)):
            self.create_text(22, y, text=f"{(self.value + offset) % self.limit:02d}",
                             fill=color if self.enabled else MUTED,
                             font=("Segoe UI", size, "bold" if not offset else "normal"))


class TimerCard(tk.Canvas):
    def __init__(self, parent, action, changed):
        super().__init__(parent, width=248, height=112, bg=BG, highlightthickness=0, takefocus=True)
        self.action, self.changed = action, changed
        self.active, self.supported, self.busy, self.draft = False, False, False, False
        self.hover, self.due = False, None
        self.hour = NumberWheel(self, 24, 8 if action == "on" else 22, self.edited)
        self.minute = NumberWheel(self, 60, 0, self.edited)
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Motion>", self.motion)
        self.bind("<Leave>", lambda e: self.highlight(False))
        self.bind("<Button-1>", self.click)
        self.bind("<Return>", lambda e: self.run(stop=self.active and not self.draft))
        self.bind("<space>", lambda e: self.run(stop=self.active and not self.draft))
        self.draw()

    def edited(self):
        self.draft = True
        self.draw()

    def set_status(self, supported, due, busy):
        self.supported, self.busy = supported, busy
        self.due = due
        self.active = due is not None and due > datetime.now()
        if due and not self.draft:
            self.hour.value, self.minute.value = due.hour, due.minute
        self.draw()

    def highlight(self, value):
        if self.hover != value:
            self.hover = value
            self.draw()

    def motion(self, event):
        self.highlight(event.x >= max(self.winfo_width(), 248)-86 and event.y >= 41)

    def run(self, stop=False):
        if self.supported and not self.busy:
            self.changed(self.action, None if stop else next_time(self.hour.value, self.minute.value))
        return "break"

    def click(self, event):
        if event.x >= max(self.winfo_width(), 248)-86 and 41 <= event.y <= 76:
            self.run(stop=self.active and not self.draft)

    def draw(self):
        self.delete("all")
        width = max(self.winfo_width(), 248)
        surface = ACTIVE if self.active else CARD
        rounded(self, 1, 1, width-1, 111, 12, fill=surface, outline=GREEN if self.active else "")
        icon(self, "clock", 20, 19, GREEN if self.active else ACCENT)
        self.create_text(40, 19, text="Start at" if self.action == "on" else "End at", anchor="w",
                         fill=TEXT, font=("Segoe UI", 10, "bold"))
        self.create_text(width-13, 19, text="Once", anchor="e", fill=MUTED, font=("Segoe UI", 8))
        for x, wheel in ((12, self.hour), (69, self.minute)):
            wheel.surface, wheel.tone, wheel.enabled = surface, GREEN if self.active else TEXT, not self.busy
            wheel.draw()
            self.create_window(x, 30, window=wheel, anchor="nw")
        self.create_text(63, 63, text=":", fill=GREEN if self.active else TEXT, font=("Segoe UI", 19))
        enabled = self.supported and not self.busy
        button = "Stop" if self.active and not self.draft else "Set" if self.supported else "Unavailable"
        rounded(self, width-84, 44, width-12, 76, 8,
                fill=HOVER if self.hover and enabled else "#35513d" if self.active else BG,
                outline=GREEN if self.active else "")
        self.create_text(width-48, 60, text=button, fill=TEXT if enabled else MUTED,
                         font=("Segoe UI", 9, "bold"))
        hint = ("Preview · " + self.due.strftime("%a %d %b")) if self.active else "Select a time" if self.supported else "hOn timer connection needed"
        self.create_text(13, 99, text=hint, anchor="w", fill=GREEN if self.active else MUTED, font=("Segoe UI", 8))
        # An edited active timer retains an independent Stop button.
        if self.active and self.draft:
            self.create_text(width-34, 98, text="Stop", fill=GREEN, font=("Segoe UI", 9, "bold"), tags="stop")
            self.tag_bind("stop", "<Button-1>", lambda e: self.run(stop=True))


class InlineTimers(tk.Frame):
    def __init__(self, app):
        super().__init__(app.canvas, bg=BG, width=510, height=116)
        self.app = app
        self.device = None
        self.cards = {}
        self.columnconfigure(0, weight=1, uniform="timers")
        self.columnconfigure(1, weight=1, uniform="timers")
        for index, action in enumerate(("on", "off")):
            self.cards[action] = TimerCard(self, action, app.change_timer)
            self.cards[action].grid(row=0, column=index, sticky="ew", padx=(0, 10) if not index else 0)

    def refresh(self, snapshot, busy):
        device = snapshot["id"]
        if device != self.device:
            for action, card in self.cards.items():
                card.draft = False
                card.hour.value, card.minute.value = (8 if action == "on" else 22), 0
            self.device = device
        status = self.app.preview_timers.get(device, {}) if self.app.demo else {}
        for action, card in self.cards.items():
            card.set_status(self.app.demo, status.get(action), busy)
