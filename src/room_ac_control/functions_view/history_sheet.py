"""The History sheet: the room temperature over the last day or week, and energy use.

Temperature readings are kept on this computer by `room_history`, one every ten minutes
while the app is open. The chart shows the room temperature, the outside temperature
when known, and shades the times the AC was on. Energy use comes from hOn's statistics
service (`energy`), as in hOn's Energy consumption panel.
"""

from datetime import datetime, timedelta

from ..i18n import tr, translator
from ..room_history import EVERY, summary
from ..smooth import aa_line, aa_oval
from ..theme import C, blend, measure, rounded

PERIODS = (("24 hours", 24), ("7 days", 24 * 7))
TABS = (("Temperature", "temperature"), ("Energy", "energy"))
ENERGY_PERIODS = (("This week", "week"), ("This month", "month"), ("This year", "year"))
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
    """Adds the History sheet to a SheetHost."""

    history_hours = 24
    history_tab = "temperature"
    energy_period = "week"

    def open_history_sheet(self, tab=None):
        device = self.app.selected
        if not device:
            return
        if tab:
            self.history_tab = tab
        number = translator(self.window).number

        def degrees(value, places=1):
            return number(f"{float(value):.{places}f}") + "°"

        def choose(hours):
            self.history_hours = hours
            self.sheet["draw"]()

        def switch(tab):
            self.history_tab = tab
            if tab == "energy":
                self.load_energy(device)
            self.sheet["draw"]()

        def draw(c, width):
            tone = self.tone()
            y = 30
            self.text(c, 24, y + 12, "History", -22, weight="black")
            # Temperature or Energy, as underlined tabs on the right of the title.
            x = width - 24
            for label, value in reversed(TABS):
                on = value == self.history_tab
                label_width = measure(c, tr(c, label), -14, "bold")
                self.text(c, x, y + 12, label, -14, tone if on else C.MUTED, "e", "bold")
                if on:
                    c.create_line(x - label_width, y + 30, x, y + 30, fill=tone, width=3, capstyle="round")
                self.sheet_hit((x - label_width - 8, y - 6, x + 8, y + 36), lambda value=value: switch(value))
                x -= label_width + 24
            y += 50
            if self.history_tab == "energy":
                y = self.draw_energy(c, width, y, device, tone)
            else:
                y = self.draw_temperature(c, width, y, device, tone, degrees, choose)
            rounded(c, 24, y, width - 24, y + 50, 14, fill=C.CARD, outline=C.STRONG, width=1.2)
            self.text(c, width / 2, y + 25, "Close", -14, C.TEXT, "center", "bold")
            self.sheet_hit((24, y, width - 24, y + 50), self.close_sheet)
            return y + 50 + 28

        if self.history_tab == "energy":
            self.load_energy(device)
        self.open_sheet(draw)

    def draw_temperature(self, c, width, y, device, tone, degrees, choose):
        hours = self.history_hours
        rows = self.app.memory.readings(device["id"], hours)
        self.text(c, 24, y + 4, "Room temperature, one reading every ten minutes while the app is open.", -13, C.MUTED)
        y += 30
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
            return self.empty_card(
                c,
                width,
                y,
                "No readings yet",
                "Keep the app open (it can stay in the notification area) and the chart fills in.",
            )
        tiles = (("Lowest", stats["low"]), ("Average", stats["average"]), ("Highest", stats["high"]))
        self.tiles(c, width, y, [(label, degrees(value)) for label, value in tiles])
        y += 74
        return self.draw_history_chart(c, width, y, rows, hours, tone, degrees)

    def tiles(self, c, width, y, tiles, selected=None, tone=None, hits=None):
        """A row of small value tiles; a selected one takes the accent."""
        tile = (width - 48 - 10 * (len(tiles) - 1)) / len(tiles)
        for index, (label, value) in enumerate(tiles):
            x = 24 + index * (tile + 10)
            on = selected == index
            fill = self.app.soft(tone) if on else C.SURFACE
            rounded(c, x, y, x + tile, y + 60, 16, fill=fill, outline=tone if on else fill, width=1.5)
            self.text(c, x + 14, y + 19, label, -11, tone if on else C.MUTED, weight="semibold")
            self.text(c, x + 14, y + 40, value, -17, weight="bold", translate=False)
            if hits:
                self.sheet_hit((x, y, x + tile, y + 60), hits[index])

    def empty_card(self, c, width, y, title, detail, action=None):
        height = 150 if action else 120
        rounded(c, 24, y, width - 24, y + height, 18, fill=C.SURFACE, outline="")
        self.text(c, width / 2, y + 40, title, -15, C.TEXT, "center", "bold")
        self.text(c, width / 2, y + 72, detail, -12, C.MUTED, "center", width=width - 96)
        if action:
            label, run = action
            rounded(c, width / 2 - 70, y + 100, width / 2 + 70, y + 136, 12, fill=C.CARD, outline=C.STRONG)
            self.text(c, width / 2, y + 118, label, -13, C.TEXT, "center", "bold")
            self.sheet_hit((width / 2 - 70, y + 100, width / 2 + 70, y + 136), run)
        return y + height + 14

    # Energy

    def load_energy(self, device):
        """Ask the worker for hOn's energy statistics; the preview has its own fictional values."""
        states = self.__dict__.setdefault("energy_states", {})
        state = states.get(device["id"])
        if state and state["status"] in {"loading", "ready"}:
            return
        if self.app.demo:
            from ..demo import energy

            states[device["id"]] = {"status": "ready", "values": energy(device)}
            return
        states[device["id"]] = {"status": "loading"}

        def finished(status, values=None):
            states[device["id"]] = {"status": status, "values": values}
            if self.sheet and self.history_tab == "energy":
                self.sheet["draw"]()

        self.app.worker.submit(
            self.app.worker.controller.energy(device["id"]),
            lambda values: finished("ready", values),
            "energy",
            on_error=lambda error: finished("failed"),
        )

    def draw_energy(self, c, width, y, device, tone):
        state = self.__dict__.get("energy_states", {}).get(device["id"], {"status": "loading"})
        self.text(c, 24, y + 4, "Energy use the AC reports to hOn.", -13, C.MUTED)
        y += 30
        if state["status"] == "loading":
            return self.empty_card(c, width, y, "Loading energy use…", "Asking hOn for this AC's statistics.")
        if state["status"] == "failed":

            def retry():
                self.energy_states.pop(device["id"], None)
                self.load_energy(device)
                self.sheet["draw"]()

            return self.empty_card(
                c,
                width,
                y,
                "Energy use could not be loaded",
                "Check your internet connection and try again.",
                ("Try again", retry),
            )
        values = state["values"]
        if not values["measured"]:
            return self.empty_card(
                c,
                width,
                y,
                "No energy data from hOn",
                "hOn has no energy readings for this AC. Many models do not measure their consumption, "
                "and the hOn app shows the same.",
            )
        number = translator(self.window).number

        def amount(value):
            return "—" if value is None else number(f"{value:.1f}") + " kWh"

        def pick(period):
            self.energy_period = period
            self.sheet["draw"]()

        periods = [value for _, value in ENERGY_PERIODS]
        self.tiles(
            c,
            width,
            y,
            [(label, amount(values["total"][value])) for label, value in ENERGY_PERIODS],
            selected=periods.index(self.energy_period),
            tone=tone,
            hits=[lambda value=value: pick(value) for value in periods],
        )
        y += 74
        return self.draw_energy_bars(c, width, y, values["history"][self.energy_period], tone)

    def draw_energy_bars(self, c, width, y, bars, tone):
        """One bar per entry of the chosen period's history; returns the y below them."""
        top, bottom = y + 30, y + CHART_HEIGHT
        rounded(c, 24, y, width - 24, bottom + 34, 18, fill=C.SURFACE, outline="")
        if not bars:
            self.text(c, width / 2, (top + bottom) / 2, "No history for this period yet.", -12, C.MUTED, "center")
            return bottom + 48
        language = translator(self.window)
        highest = max(bar["kwh"] for bar in bars) or 1
        left, right = 40, width - 40
        slot = (right - left) / len(bars)
        bar_width = max(3, min(28, slot * 0.6))
        every = max(1, round(len(bars) / 8))
        c.create_line(left, bottom, right, bottom, fill=C.TRACK)
        for index, bar in enumerate(bars):
            middle = left + slot * (index + 0.5)
            height = (bottom - top) * bar["kwh"] / highest
            if height > 0:
                rounded(
                    c,
                    middle - bar_width / 2,
                    bottom - max(height, 4),
                    middle + bar_width / 2,
                    bottom,
                    min(6, bar_width / 2),
                    fill=tone,
                    outline="",
                )
            if index % every == 0 and bar["date"] is not None:
                day, date, month = language.date(bar["date"]).split(" ")
                label = month if self.energy_period == "year" else day if len(bars) <= 7 else date
                self.text(c, middle, bottom + 16, label, -10, C.MUTED, "center", translate=False)
        peak = max(bars, key=lambda bar: bar["kwh"])
        self.text(
            c,
            width - 40,
            y + 16,
            tr(c, "Highest") + " " + language.number(f"{peak['kwh']:.1f}") + " kWh",
            -11,
            C.MUTED,
            "e",
            "semibold",
            translate=False,
        )
        return bottom + 48

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
