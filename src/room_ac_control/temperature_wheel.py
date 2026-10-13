"""A bounded temperature selector using the timer wheels' drag interaction."""
from decimal import Decimal, InvalidOperation

from .inline_timers import NumberWheel
from .theme import CARD, HOVER, TEXT, MUTED, ACCENT, rounded
from .i18n import translator


class TemperatureWheel(NumberWheel):
    ROW_HEIGHT = 30
    CLICK_TOP, CLICK_BOTTOM = 39, 69

    def __init__(self, parent, spec, value):
        self.minimum = Decimal(str(spec["min"]))
        maximum = Decimal(str(spec["max"]))
        self.increment = Decimal(str(spec["step"]))
        if not all(number.is_finite() for number in (self.minimum, maximum, self.increment)) or self.increment <= 0 or maximum < self.minimum:
            raise ValueError("Invalid temperature range")
        limit = int((maximum-self.minimum) // self.increment) + 1
        self.chosen, self.hover, self.wheel_remainder = False, False, 0
        index = 0
        try:
            position = (Decimal(str(value))-self.minimum)/self.increment
            if position.is_finite() and position == int(position) and 0 <= position < limit:
                index, self.chosen = int(position), True
        except (InvalidOperation, ValueError, OverflowError):
            pass
        super().__init__(parent, limit, index, self.mark_changed)
        self.configure(width=236, height=108)
        self.bind("<Enter>", lambda event: self.highlight(True))
        self.bind("<Leave>", lambda event: self.highlight(False))
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<Up>", lambda event: self.step(1))
        self.bind("<Down>", lambda event: self.step(-1))
        self.bind("<Home>", lambda event: self.step(-self.value))
        self.bind("<End>", lambda event: self.step(self.limit-1-self.value))
        self.draw()

    def normalize_value(self, value):
        return max(0, min(self.limit-1, value))

    def number(self, index):
        return format((self.minimum+self.increment*index).normalize(), "f")

    def get(self):
        return self.number(self.value) if self.chosen else None

    def mark_changed(self):
        self.chosen = True
        self.draw()

    def highlight(self, active):
        self.hover = active
        self.draw()

    def wheel(self, event):
        if self.enabled:
            self.wheel_remainder += event.delta/120
            steps = int(self.wheel_remainder)
            if steps:
                self.wheel_remainder -= steps
                self.step(steps)
        return "break"

    def release(self, event):
        gesture = self.drag_state
        super().release(event)
        if gesture and gesture["moved"] and self.enabled and not self.chosen:
            self.mark_changed()
        return "break"

    def draw(self):
        if not self.enabled:
            self.cancel_drag()
        self.delete("all")
        focused = self.focus_get() is self
        self.configure(bg=CARD, cursor="sb_v_double_arrow" if self.enabled else "arrow")
        rounded(self, 1, 1, 235, 107, 12, fill=HOVER if self.hover or focused else CARD,
                outline=ACCENT if self.hover or focused else "#394035")
        for offset in range(-2, 3):
            index = self.value+offset
            if not 0 <= index < self.limit:
                continue
            y = 54+offset*self.ROW_HEIGHT+self.drag_offset
            emphasis = max(0, 1-abs(y-54)/self.ROW_HEIGHT)
            text = "—" if offset == 0 and not self.chosen else translator(self).number(self.number(index))+"°C"
            self.create_text(118, y, text=text,
                             fill=TEXT if emphasis >= .5 and self.enabled else MUTED,
                             font=("Segoe UI", round(11+15*emphasis), "bold" if emphasis >= .5 else "normal"))
