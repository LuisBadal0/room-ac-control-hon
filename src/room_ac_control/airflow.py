"""A soft moving curtain of air, rendered without video playback dependencies."""
import math
import time

from .theme import C


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


# Light airflow must darken the sand page, dark airflow must brighten charcoal.
COLORS = {
    "light": {"cool": (31, 112, 168), "heat": (207, 89, 0), "neutral": (110, 110, 110)},
    "dark": {"cool": (115, 201, 237), "heat": (242, 167, 106), "neutral": (198, 208, 195)},
}


def tint(tone, opacity):
    background = tuple(int(C.BG[i:i+2], 16) for i in (1, 3, 5))
    rgb = COLORS[C.mode][tone]
    return "#" + "".join(f"{round(a+(b-a)*opacity):02x}" for a, b in zip(background, rgb))


class AirflowAnimation:
    """Own one cancellable Tk timer and a small set of reusable canvas strokes."""
    def __init__(self, canvas):
        self.canvas = canvas
        self.job = None
        self.closed = False
        self.tone = None
        self.geometry = (0, 0, 1, 1, 1)
        self.strokes = []
        self.start = time.monotonic()
        self.canvas.bind("<Destroy>", self._destroyed, add="+")

    def set_state(self, device, x, outlet, width, length, scale=1):
        if self.closed:
            return
        self.tone = airflow_tone(device)
        self.geometry = (x, outlet, width, length, scale)
        # A dashboard redraw removes these items; recreate once, never per frame.
        self.canvas.delete("airflow")
        self.strokes = []
        if self.tone:
            for strand in range(19):
                for depth in range(8):
                    glow = self.canvas.create_line(0, 0, 1, 1, fill=C.BG, width=4*scale, smooth=True, tags="airflow")
                    core = self.canvas.create_line(0, 0, 1, 1, fill=C.BG, width=1.2*scale, smooth=True, tags="airflow")
                    self.strokes.append((strand, depth, glow, core))
            self.canvas.tag_lower("airflow")
            self.paint(time.monotonic()-self.start)
        if self.job is None:
            self.job = self.canvas.after(40, self.tick)

    def paint(self, elapsed):
        if not self.tone:
            return
        x, y, width, length, scale = self.geometry
        for strand, depth, glow, core in self.strokes:
            fraction = (strand-9)/18
            coords = []
            for step in range(3):
                progress = (depth+step/2)/8
                wave = math.sin(progress*5-elapsed*2.5+strand*.27)
                drift = -length*.23*progress + wave*length*.035*progress
                coords.extend(((x+fraction*width*(1+.10*progress)+drift)*scale,
                               (y+length*progress)*scale))
            progress = (depth+.5)/8
            pulse = .68+.32*math.sin(progress*12-elapsed*4+strand*.31)
            edge = 1-abs(fraction)*.7
            opacity = .33*(1-progress)**1.3*pulse*edge
            self.canvas.coords(glow, *coords)
            self.canvas.coords(core, *coords)
            self.canvas.itemconfigure(glow, fill=tint(self.tone, opacity*.38))
            self.canvas.itemconfigure(core, fill=tint(self.tone, opacity))

    def tick(self):
        self.job = None
        if self.closed:
            return
        visible = self.canvas.winfo_ismapped() and self.canvas.winfo_toplevel().state() == "normal"
        if visible and self.tone:
            self.paint(time.monotonic()-self.start)
        self.job = self.canvas.after(40 if visible and self.tone else 250, self.tick)

    def _destroyed(self, event):
        if event.widget is self.canvas:
            self.close()

    def close(self):
        self.closed = True
        if self.job is not None:
            self.canvas.after_cancel(self.job)
            self.job = None
