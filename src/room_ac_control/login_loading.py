"""A reusable, cancellable sign-in animation drawn with native canvas shapes."""
import time

from .theme import CARD, TEXT, MUTED, GREEN


def blend(color, background, strength):
    channels = []
    for index in (1, 3, 5):
        base = int(background[index:index+2], 16)
        target = int(color[index:index+2], 16)
        channels.append(f"{round(base+(target-base)*strength):02x}")
    return "#" + "".join(channels)


class LoginLoadingAnimation:
    TAG = "login-loading"

    def __init__(self, canvas):
        self.canvas = canvas
        self.job = None
        self.active, self.closed = False, False
        self.segments = []
        self.center = 0
        self.canvas.bind("<Destroy>", self.destroyed, add="+")

    def start(self, automatic=False):
        if self.closed:
            return
        if self.active:
            return  # One pending timer even if a sign-in request is repeated.
        self.active = True
        self.started = time.monotonic()
        self.center = self.canvas.winfo_width()/2
        x = self.center
        self.canvas.create_oval(x-34, 96, x+34, 164, outline="#30372e", width=4, tags=self.TAG)
        for index in range(12):
            self.segments.append(self.canvas.create_arc(x-34, 96, x+34, 164,
                start=index*18, extent=16, style="arc", width=4,
                outline=blend(GREEN, CARD, 1-index/13), tags=self.TAG))
        self.canvas.create_rectangle(x-13, 122, x+13, 137, outline=GREEN, width=1.5, tags=self.TAG)
        self.canvas.create_line(x-10, 133, x+10, 133, fill=GREEN, width=1.5, tags=self.TAG)
        self.canvas.create_text(x, 205, text="Welcome back" if automatic else "Signing in",
            fill=TEXT, font=("Segoe UI", 20, "bold"), tags=self.TAG)
        self.canvas.create_text(x, 244,
            text="Signing in with your saved account." if automatic else "Connecting to hOn and loading your AC.",
            fill=MUTED, font=("Segoe UI", 10), width=380, tags=self.TAG)
        self.paint()
        self.job = self.canvas.after(40, self.tick)

    def resize(self):
        if self.active:
            center = self.canvas.winfo_width()/2
            self.canvas.move(self.TAG, center-self.center, 0)
            self.center = center

    def paint(self):
        phase = -(time.monotonic()-self.started)*240
        for index, segment in enumerate(self.segments):
            self.canvas.itemconfigure(segment, start=(phase+index*18) % 360)

    def tick(self):
        self.job = None
        if not self.active or self.closed:
            return
        visible = self.canvas.winfo_ismapped() and self.canvas.winfo_toplevel().state() in {"normal", "zoomed"}
        if visible:
            self.paint()
        self.job = self.canvas.after(40 if visible else 250, self.tick)

    def stop(self):
        self.active = False
        if self.job is not None:
            self.canvas.after_cancel(self.job)
            self.job = None
        if not self.closed:
            self.canvas.delete(self.TAG)
        self.segments = []

    def close(self):
        self.stop()
        self.closed = True

    def destroyed(self, event):
        if event.widget is self.canvas:
            self.closed = True
            self.stop()
