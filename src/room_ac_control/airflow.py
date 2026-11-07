"""Animated airflow below the unit: dashed lines that drift down in the mode's accent."""

import math
import time

from .theme import C, accent, blend


def airflow_tone(device):
    """Use reported operation only; pending menu selections are not AC status."""
    if not device or device.get("power") != "On":
        return None
    mode = str(device.get("mode", "")).casefold()
    if mode in {"cool", "cool night"}:
        return "cool"
    if mode in {"heat", "heat night"}:
        return "heat"
    return "neutral"


class AirflowAnimation:
    """Own one cancellable Tk timer and a fixed set of reusable dash strokes."""

    LINES, DASH, GAP, SPEED = 11, 5, 9, 12.7  # count, px, px, px per second

    def __init__(self, canvas):
        self.canvas = canvas
        self.job = None
        self.closed = False
        self.tone = None
        self.color = None
        self.paths = []
        self.strokes = []
        self.scale = 1
        self.start = time.monotonic()
        self.canvas.bind("<Destroy>", self._destroyed, add="+")

    def set_state(self, device, x, outlet, width, length, scale=1):
        if self.closed:
            return
        self.tone = airflow_tone(device)
        # A redraw removes these items; recreate once, never per frame.
        self.canvas.delete("airflow")
        self.strokes, self.paths, self.scale = [], [], scale
        if self.tone:
            self.color = blend(accent(device.get("mode")), C.BG, 0.75)
            for line in range(self.LINES):
                x0 = x - width / 2 + line * width / (self.LINES - 1)
                drift = (x0 - x) * 0.16
                points = []
                for step in range(13):
                    t = step / 12
                    px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * (x0 + drift * 0.3) + t * t * (x0 + drift)
                    py = (1 - t) ** 2 * outlet + 2 * (1 - t) * t * (outlet + length * 0.47) + t * t * (outlet + length)
                    points.append((px * scale, py * scale))
                lengths = [0]
                for a, b in zip(points, points[1:]):
                    lengths.append(lengths[-1] + math.dist(a, b))
                self.paths.append((points, lengths))
                for _dash in range(4):
                    self.strokes.append(
                        self.canvas.create_line(
                            0,
                            0,
                            1,
                            1,
                            fill=self.color,
                            width=2.2 * scale,
                            capstyle="round",
                            tags="airflow",
                            state="hidden",
                        )
                    )
            self.paint(time.monotonic() - self.start)
        if self.job is None:
            self.job = self.canvas.after(40, self.tick)

    def paint(self, elapsed):
        if not self.tone:
            return
        period = (self.DASH + self.GAP) * self.scale
        offset = (elapsed * self.SPEED * self.scale) % period
        for index, (points, lengths) in enumerate(self.paths):
            total = lengths[-1]
            for dash in range(4):
                item = self.strokes[index * 4 + dash]
                start = offset + (dash - 1) * period
                end = start + self.DASH * self.scale
                start, end = max(0, start), min(total, end)
                if end - start < 0.5:
                    self.canvas.itemconfigure(item, state="hidden")
                    continue
                self.canvas.coords(item, *self.segment(points, lengths, start, end))
                self.canvas.itemconfigure(item, state="normal")

    @staticmethod
    def segment(points, lengths, start, end):
        def at(distance):
            for i in range(1, len(lengths)):
                if lengths[i] >= distance:
                    span = lengths[i] - lengths[i - 1] or 1
                    t = (distance - lengths[i - 1]) / span
                    (ax, ay), (bx, by) = points[i - 1], points[i]
                    return ax + (bx - ax) * t, ay + (by - ay) * t
            return points[-1]

        coords = [*at(start)]
        coords.extend(c for i in range(1, len(lengths)) if start < lengths[i] < end for c in points[i])
        coords.extend(at(end))
        return coords

    def tick(self):
        self.job = None
        if self.closed:
            return
        visible = self.canvas.winfo_ismapped() and self.canvas.winfo_toplevel().state() == "normal"
        if visible and self.tone:
            self.paint(time.monotonic() - self.start)
        self.job = self.canvas.after(40 if visible and self.tone else 250, self.tick)

    def _destroyed(self, event):
        if event.widget is self.canvas:
            self.close()

    def close(self):
        self.closed = True
        if self.job is not None:
            self.canvas.after_cancel(self.job)
            self.job = None
