"""The Room history sheet: the room temperature over the last day or week.

Readings are kept on this computer by `room_history`, one every ten minutes while the
app is open. The chart shows the room temperature, the outside temperature when known,
and shades the times the AC was on.
"""

from datetime import datetime, timedelta

from ..i18n import tr, translator
from ..room_history import EVERY, summary
from ..smooth import aa_line, aa_oval
from ..theme import C, blend, rounded

PERIODS = (("24 hours", 24), ("7 days", 24 * 7))
CHART_HEIGHT = 190
# A pause longer than this (the app was closed) breaks the line.
GAP = 3 * EVERY


def segments(rows, key):
    """Runs of consecutive readings with a value, split where readings stop for a while."""
    runs, current, last = [], [], None
    for row in rows:
        value = row.get(key)
        if value is None or (last is not None and row["time"] - last > GAP):
            if len(current) > 1:
                runs.append(current)
            current = []
        if value is not None:
            current.append((row["time"], value))
        last = row["time"]
    if len(current) > 1:
        runs.append(current)
    return runs


def scale(rows):
    """Rounded lower and upper bounds for the chart, at least four degrees apart."""
    values = [row[key] for row in rows for key in ("room", "outside") if row.get(key) is not None]
    low, high = int(min(values) // 1), int(-(-max(values) // 1))
    while high - low < 4:
        low, high = low - 1, high + 1
    return low, high


def ticks(start, end, hours):
    """Times to label under the chart: every six hours for a day, each midnight for a week."""
    every = 6 if hours <= 24 else 24
    moment = datetime.fromtimestamp(start).replace(minute=0, second=0, microsecond=0)
    while moment.timestamp() < start or moment.hour % every:
        moment += timedelta(hours=1)
    result = []
    while moment.timestamp() <= end:
        result.append(moment.timestamp())
        moment += timedelta(hours=every)
    return result


class HistorySheetMixin:
    """Adds the Room history sheet to a SheetHost."""

    history_hours = 24

    def open_history_sheet(self):
        device = self.app.selected
        if not device:
            return
        number = translator(self.window).number

        def degrees(value, places=1):
            return number(f"{float(value):.{places}f}") + "°"

        def choose(hours):
            self.history_hours = hours
            self.sheet["draw"]()

        def draw(c, width):
            tone = self.tone()
            hours = self.history_hours
            rows = self.app.memory.readings(device["id"], hours)
            y = 30
            self.text(c, 24, y + 12, "Room temperature", -22, weight="black")
            self.text(
                c,
                24,
                y + 38,
                "One reading every ten minutes while the app is open.",
                -13,
                C.MUTED,
                width=width - 48,
            )
            y += 70
            # Period switch: 24 hours or 7 days.
            cell = (width - 48 - 8) / 2
            for index, (label, value) in enumerate(PERIODS):
                x = 24 + index * (cell + 8)
                on = value == hours
                fill = self.app.soft(tone) if on else C.SURFACE
                rounded(c, x, y, x + cell, y + 38, 12, fill=fill, outline=tone if on else fill, width=1.5)
                self.text(c, x + cell / 2, y + 19, label, -13, tone if on else C.TEXT, "center", "bold")
                self.sheet_hit((x, y, x + cell, y + 38), lambda value=value: choose(value))
            y += 52
            stats = summary(rows)
            if stats is None or len(rows) < 2:
                rounded(c, 24, y, width - 24, y + 120, 18, fill=C.SURFACE, outline="")
                self.text(c, width / 2, y + 44, "No readings yet", -15, C.TEXT, "center", "bold")
                self.text(
                    c,
                    width / 2,
                    y + 74,
                    "Keep the app open (it can stay in the notification area) and the chart fills in.",
                    -12,
                    C.MUTED,
                    "center",
                    width=width - 96,
                )
                y += 134
            else:
                tiles = (("Lowest", stats["low"]), ("Average", stats["average"]), ("Highest", stats["high"]))
                tile = (width - 48 - 20) / 3
                for index, (label, value) in enumerate(tiles):
                    x = 24 + index * (tile + 10)
                    rounded(c, x, y, x + tile, y + 60, 16, fill=C.SURFACE, outline="")
                    self.text(c, x + 14, y + 19, label, -11, C.MUTED, weight="semibold")
                    self.text(c, x + 14, y + 40, degrees(value), -17, weight="bold", translate=False)
                y += 74
                y = self.draw_history_chart(c, width, y, rows, hours, tone, degrees)
            rounded(c, 24, y, width - 24, y + 50, 14, fill=C.CARD, outline=C.STRONG, width=1.2)
            self.text(c, width / 2, y + 25, "Close", -14, C.TEXT, "center", "bold")
            self.sheet_hit((24, y, width - 24, y + 50), self.close_sheet)
            return y + 50 + 28

        self.open_sheet(draw)

    def draw_history_chart(self, c, width, y, rows, hours, tone, degrees):
        """The chart and its legend; returns the y below them."""
        left, right = 60, width - 28
        top, bottom = y + 8, y + 8 + CHART_HEIGHT
        end = max(rows[-1]["time"], datetime.now().timestamp())
        start = end - hours * 3600
        low, high = scale(rows)
        x_of = lambda moment: left + (moment - start) / (end - start) * (right - left)
        y_of = lambda value: bottom - (value - low) / (high - low) * (bottom - top)
        rounded(c, 24, y, width - 24, bottom + 34, 18, fill=C.SURFACE, outline="")
        # The AC's running time, shaded behind the lines.
        band = blend(tone, C.SURFACE, 0.14)
        for previous, row in zip(rows, rows[1:]):
            if previous["on"] and row["time"] - previous["time"] <= GAP:
                c.create_rectangle(x_of(previous["time"]), top, x_of(row["time"]), bottom, fill=band, outline="")
        # Horizontal guides at whole degrees, labelled on the left.
        step = 1 if high - low <= 6 else 2 if high - low <= 12 else 5
        value = low - low % step + (step if low % step else 0)
        while value <= high:
            line_y = y_of(value)
            c.create_line(left, line_y, right, line_y, fill=C.TRACK)
            self.text(c, left - 8, line_y, degrees(value, 0), -10, C.MUTED, "e", translate=False)
            value += step
        language = translator(self.window)
        for moment in ticks(start, end, hours):
            stamp = datetime.fromtimestamp(moment)
            label = stamp.strftime("%H:%M") if hours <= 24 else language.date(stamp).rsplit(" ", 1)[0]
            self.text(c, x_of(moment), bottom + 16, label, -10, C.MUTED, "center", translate=False)
        for key, color, width_ in (("outside", C.FAINT, 1.6), ("room", tone, 2.4)):
            for run in segments(rows, key):
                points = [coordinate for moment, value in run for coordinate in (x_of(moment), y_of(value))]
                aa_line(c, *points, fill=color, width=width_, capstyle="round", joinstyle="round")
        latest = next((row for row in reversed(rows) if row.get("room") is not None), None)
        if latest:
            x, dot_y = x_of(latest["time"]), y_of(latest["room"])
            aa_oval(c, x - 4, dot_y - 4, x + 4, dot_y + 4, fill=tone, outline="")
        y = bottom + 46
        # Legend.
        x = 28
        for label, color, width_ in (("Room", tone, 3), ("Outside", C.FAINT, 2)):
            if label == "Outside" and not segments(rows, "outside"):
                continue
            c.create_line(x, y, x + 18, y, fill=color, width=width_)
            self.text(c, x + 26, y, label, -12, C.MUTED, weight="semibold")
            x += 40 + len(tr(c, label)) * 7
        if any(row["on"] for row in rows):
            rounded(c, x, y - 7, x + 18, y + 7, 4, fill=band, outline="")
            self.text(c, x + 26, y, "AC on", -12, C.MUTED, weight="semibold")
        return y + 24
