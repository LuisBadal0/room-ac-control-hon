"""Ambient building blocks: rounded buttons, switches, a dimmed overlay and a status toast."""

import math
import tkinter as tk

from .i18n import refresh_on_language, tr
from .smooth import aa_arc, aa_line, aa_oval, aa_rect, aa_text
from .theme import C, blend, font, icon, measure, refresh_on_theme, rounded


def raise_widget(widget):
    """Stack a widget above its siblings; Canvas.lift() would raise canvas items instead."""
    widget.tk.call("raise", widget._w)


def section_label(canvas, x, y, text, anchor="w"):
    """An upper-case section heading such as COMFORT."""
    return aa_text(canvas, x, y, text=tr(canvas, text).upper(), anchor=anchor, fill=C.MUTED, font=font(-11, "black"))


def switch(canvas, x, y, on, tone=None, width=40, height=24, tags=()):
    """A pill switch whose knob sits right when on; (x, y) is its top left."""
    tone = tone or C.BRAND
    rounded(canvas, x, y, x + width, y + height, height / 2, fill=tone if on else C.STRONG, outline="", tags=tags)
    knob = height - 6
    left = x + width - 3 - knob if on else x + 3
    aa_oval(canvas, left, y + 3, left + knob, y + 3 + knob, fill=C.BG if on else C.MUTED, outline="", tags=tags)


def fan_bars(canvas, x, bottom, level, tone, base, heights=(8, 11, 14), width=4, gap=3, tags=()):
    """Signal-style bars: level 0 lights all faintly (Auto), 1–3 light that many."""
    for index, height in enumerate(heights):
        left = x + index * (width + gap)
        lit = level == 0 or index < level
        color = blend(tone, base, 0.6) if level == 0 else (tone if lit else C.STRONG)
        aa_rect(canvas, left, bottom - height, left + width, bottom, fill=color, outline="", tags=tags)


def louver(canvas, x, y, position, color, air, scale=1.0, tags=()):
    """A side view of the indoor unit and its louver; position 1–5, or 0 for Swing.

    (x, y) is the top left of a 72×64 drawing at scale 1."""
    s = scale
    rounded(canvas, x + 4 * s, y + 4 * s, x + 34 * s, y + 26 * s, 8 * s, fill=C.STRONG, outline="", tags=tags)
    pivot = (x + 30 * s, y + 26 * s)

    def end(angle, length=22):
        a = math.radians(angle)
        return pivot[0] + length * s * math.cos(a), pivot[1] + length * s * math.sin(a), math.cos(a), math.sin(a)

    if position:
        ex, ey, c, sn = end(6 + (position - 1) * 13)
        aa_line(canvas, *pivot, ex, ey, fill=color, width=3 * s, capstyle="round", tags=tags)
        ox, oy = -sn * 5 * s, c * 5 * s
        aa_line(
            canvas,
            ex + 4 * c * s,
            ey + 4 * sn * s,
            ex + 16 * c * s,
            ey + 16 * sn * s,
            fill=air,
            width=2.2 * s,
            capstyle="round",
            tags=tags,
        )
        aa_line(
            canvas,
            ex + 2 * c * s + ox,
            ey + 2 * sn * s + oy,
            ex + 11 * c * s + ox,
            ey + 11 * sn * s + oy,
            fill=air,
            width=2.2 * s,
            capstyle="round",
            tags=tags,
        )
    else:
        for angle in (8, 58):
            ex, ey, c, sn = end(angle)
            aa_line(canvas, *pivot, ex, ey, fill=color, width=3 * s, capstyle="round", tags=tags)
        aa_arc(
            canvas,
            x + 28 * s,
            y + 20 * s,
            x + 64 * s,
            y + 60 * s,
            start=-90,
            extent=110,
            style="arc",
            outline=air,
            width=2.2 * s,
            tags=tags,
        )
        for px, py, dx, dy in (
            (x + 60 * s, y + 33 * s, -3.5, 3),
            (x + 60 * s, y + 33 * s, 2.5, 3.8),
            (x + 46 * s, y + 60 * s, 4.5, 0.2),
            (x + 46 * s, y + 60 * s, 1.8, -4),
        ):
            aa_line(canvas, px, py, px + dx * s, py + dy * s, fill=air, width=2.2 * s, capstyle="round", tags=tags)


class PillButton(tk.Canvas):
    """A rounded button drawn to the Ambient design, with keyboard and hover support.

    kind: "surface" (card fill), "accent" (filled with tone()), "outline", "ghost", "danger" or "solid"
    (filled with the text colour)."""

    def __init__(
        self,
        parent,
        text="",
        command=None,
        glyph=None,
        kind="surface",
        height=48,
        width=None,
        radius=14,
        size=-13,
        tone=None,
        translate=True,
        bg=None,
        hover_when=None,
    ):
        super().__init__(parent, height=height, highlightthickness=0, takefocus=True, cursor="hand2")
        self.text, self.command, self.glyph, self.kind = text, command, glyph, kind
        self.fixed_width, self.radius, self.size = width, radius, size
        self.tone = tone or (lambda: C.BRAND)
        self.translate, self.surface = translate, bg
        self.enabled, self.hover, self.badge = True, False, None
        # Optional gate: the dashboard highlights buttons only while the AC is on.
        self.hover_when = hover_when
        self.bind("<Button-1>", lambda event: self.invoke())
        self.bind("<Return>", lambda event: self.invoke())
        self.bind("<space>", lambda event: self.invoke())
        self.bind("<Enter>", lambda event: self.highlight(True))
        self.bind("<Leave>", lambda event: self.highlight(False))
        self.bind("<FocusIn>", lambda event: self.draw())
        self.bind("<FocusOut>", lambda event: self.draw())
        self.bind("<Configure>", lambda event: self.draw())
        refresh_on_theme(self, self.draw)
        refresh_on_language(self, self.draw)
        self.draw()

    def label(self):
        return tr(self, self.text) if self.translate else self.text

    def set_text(self, text):
        self.text = text
        self.draw()

    def set_badge(self, value):
        self.badge = value
        self.draw()

    def set_enabled(self, value):
        self.enabled = bool(value)
        self.configure(cursor="hand2" if self.enabled else "", takefocus=self.enabled)
        self.draw()

    def highlight(self, value):
        self.hover = bool(value) and (self.hover_when is None or bool(self.hover_when()))
        self.draw()

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def natural_width(self):
        label = self.label()
        width = (measure(self, label, self.size, "bold") if label else 0) + 32
        if self.glyph:
            width += 24 if label else 0
        if self.badge is not None:
            width += 30
        return max(width, int(self.cget("height")))

    def draw(self):
        self.delete("all")
        background = self.surface() if callable(self.surface) else (self.surface or C.BG)
        self.configure(bg=background)
        width = self.fixed_width or self.natural_width()
        if int(self.cget("width")) != width:
            self.configure(width=width)
        height = int(self.cget("height"))
        tone = self.tone()
        focused = self.focus_get() is self
        if not self.enabled:
            fill, ink, outline = (C.SURFACE if self.kind not in {"ghost", "danger"} else background), C.FAINT, ""
        elif self.kind == "accent":
            fill, ink, outline = (blend(tone, C.BG, 0.85) if self.hover else tone), C.ON_BRAND, ""
        elif self.kind == "solid":
            fill, ink, outline = (blend(C.TEXT, C.BG, 0.85) if self.hover else C.TEXT), C.BG, ""
        elif self.kind == "outline":
            fill, ink, outline = (blend(tone, background, 0.12) if self.hover else background), tone, tone
        elif self.kind in {"ghost", "danger"}:
            fill = C.HOVER if self.hover else background
            ink, outline = (C.DANGER if self.kind == "danger" else C.MUTED), ""
        else:
            fill, ink, outline = (C.HOVER if self.hover else C.CARD), C.TEXT, ""
        if focused and self.enabled:
            outline = C.BRAND if self.kind != "accent" else C.TEXT
        rounded(self, 1, 1, width - 1, height - 1, self.radius, fill=fill, outline=outline, width=1.5)
        label = self.label()
        content = (
            (measure(self, label, self.size, "bold") if label else 0)
            + (24 if self.glyph and label else 0)
            + (30 if self.badge is not None else 0)
        )
        x = width / 2 - content / 2 if label else width / 2
        if self.glyph:
            icon(self, self.glyph, x + 8 if label else x, height / 2, ink, scale=0.62, bg=fill)
            x += 24
        if label:
            aa_text(self, x, height / 2, text=label, anchor="w", fill=ink, font=font(self.size, "bold"))
            x += measure(self, label, self.size, "bold")
        if self.badge is not None:
            badge = blend(C.BG, fill, 0.2) if self.kind == "accent" else C.SURFACE
            rounded(self, x + 8, height / 2 - 11, x + 30, height / 2 + 11, 11, fill=badge, outline="")
            aa_text(self, x + 19, height / 2, text=str(self.badge), fill=ink, font=font(-12, "black"))


class Overlay:
    """Dim a window and float a panel above it, like a web popover or bottom sheet.

    The dimmed backdrop is a darkened picture of the window, so the page stays visible."""

    def __init__(self, window, close):
        self.window, self.on_close = window, close
        self.backdrop = tk.Canvas(window, highlightthickness=0, bd=0)
        self.image = None
        self.paint()
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        raise_widget(self.backdrop)
        self.backdrop.bind("<Button-1>", lambda event: self.on_close())

    def paint(self):
        """Capture the window, then darken it; fall back to a flat tint when it cannot be captured."""
        self.backdrop.delete("all")
        dim = "#05070A" if C.mode == "dark" else "#12161C"
        strength = 0.55 if C.mode == "dark" else 0.22
        self.backdrop.configure(bg=blend(dim, C.BG, strength))
        try:
            from PIL import Image, ImageGrab, ImageTk

            self.window.update_idletasks()
            x, y = self.window.winfo_rootx(), self.window.winfo_rooty()
            width, height = self.window.winfo_width(), self.window.winfo_height()
            if self.window.state() != "normal" or width < 10 or height < 10:
                return
            shot = ImageGrab.grab((x, y, x + width, y + height), all_screens=True).convert("RGB")
            tint = Image.new("RGB", shot.size, tuple(int(dim[i : i + 2], 16) for i in (1, 3, 5)))
            self.image = ImageTk.PhotoImage(Image.blend(shot, tint, strength), master=self.window)
            self.backdrop.create_image(0, 0, image=self.image, anchor="nw")
        except Exception:
            self.image = None

    def refresh(self, panels=()):
        """Recapture after a theme change: hide the overlay, let the page repaint, then dim it again."""
        for widget in (self.backdrop, *panels):
            widget.place_forget()
        self.window.update()
        self.paint()
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        raise_widget(self.backdrop)

    def destroy(self):
        if self.backdrop.winfo_exists():
            self.backdrop.destroy()


class Toast:
    """A short-lived status message above the dashboard's action row."""

    def __init__(self, window):
        self.window, self.job = window, None
        self.label = tk.Label(window, font=font(-12, "semibold"), padx=14, pady=8, bd=0, wraplength=440, justify="left")
        refresh_on_theme(self.label, self.paint)
        self.paint()

    def paint(self):
        self.label.configure(bg=C.TEXT, fg=C.BG)

    def show(self, text, y, seconds=6):
        self.label.configure(text=text)
        self.label.place(relx=0.5, y=y, anchor="s")
        self.label.lift()
        if self.job is not None:
            self.window.after_cancel(self.job)
        self.job = self.window.after(int(seconds * 1000), self.hide)

    def hide(self):
        self.job = None
        if self.label.winfo_exists():
            self.label.place_forget()


class UpdateNotice:
    """The update bar above the dashboard's bottom row.

    "Version X is available" with an Update button when a signed update is found. After
    Update is clicked it stays, with a progress bar, through the download and checks until
    the app restarts, so it is clear the app is being updated."""

    BUSY = {"downloading", "verifying", "ready"}

    def __init__(self, app):
        self.app, self.dismissed = app, None
        self.frame = tk.Frame(app.root, bd=0, highlightthickness=0)
        self.label = tk.Label(self.frame, bd=0, anchor="w", font=font(-13, "bold"))
        self.label.pack(side="left", padx=(16, 8), pady=10, fill="x", expand=True)
        self.close = tk.Label(self.frame, text="×", bd=0, cursor="hand2", font=font(-18, "bold"))
        self.close.bind("<Button-1>", lambda event: self.dismiss())
        self.button = PillButton(
            self.frame,
            "Update",
            self.update,
            kind="accent",
            height=36,
            radius=10,
            size=-13,
            tone=app.settings_accent,
            bg=lambda: C.CARD,
        )
        self.buttons_shown = False
        self.show_buttons(True)
        self.bar = tk.Canvas(self.frame, height=4, bd=0, highlightthickness=0)
        refresh_on_theme(self.frame, self.refresh)
        refresh_on_language(self.frame, self.refresh)

    def show_buttons(self, shown):
        if shown == self.buttons_shown:
            return
        if shown:
            self.close.pack(side="right", padx=(0, 12))
            self.button.pack(side="right", padx=(0, 6), pady=8)
        else:
            self.button.pack_forget()
            self.close.pack_forget()
        self.buttons_shown = shown

    def release(self):
        updater = self.app.updater
        if updater.release and updater.state in {"available", "failed"}:
            return updater.release.get("version")
        return None

    def message(self):
        """What the bar says, and how far the update has got (None: no progress bar)."""
        updater = self.app.updater
        version = (updater.release or {}).get("version", "")
        if updater.state == "downloading":
            value = int(updater.progress * 100)
            return tr(self.frame, "Downloading version {version}… {value}%").format(version=version, value=value), max(
                0.02, updater.progress
            )
        if updater.state == "verifying":
            return tr(self.frame, "Checking the new version…"), 1.0
        if updater.state == "ready":
            return tr(self.frame, "Restarting to finish the update…"), 1.0
        return tr(self.frame, "Version {version} is available.").format(version=version), None

    def refresh(self):
        updater = self.app.updater
        busy = bool(updater.release) and updater.state in self.BUSY
        version = self.release()
        if not busy and (not version or version == self.dismissed):
            self.frame.place_forget()
            return
        text, done = self.message()
        self.frame.configure(bg=C.CARD, highlightbackground=C.TRACK, highlightthickness=1)
        self.label.configure(bg=C.CARD, fg=C.TEXT, text=text)
        self.close.configure(bg=C.CARD, fg=C.MUTED)
        self.show_buttons(not busy)
        if self.buttons_shown:
            self.button.draw()
        # Room under the text for the progress line while an update runs.
        self.label.pack_configure(pady=(14, 22) if done is not None else 10)
        if done is None:
            self.bar.place_forget()
        else:
            self.bar.configure(bg=C.CARD)
            self.bar.place(x=16, rely=1, y=-12, relwidth=1, width=-32, height=4, anchor="sw")
            self.bar.delete("all")
            width = 500 - 32
            rounded(self.bar, 0, 0, width, 4, 2, fill=C.SURFACE, outline="")
            rounded(self.bar, 0, 0, max(4, width * done), 4, 2, fill=self.app.settings_accent(), outline="")
        self.frame.place(relx=0.5, rely=1, y=-84, anchor="s", width=500)
        raise_widget(self.frame)

    def update(self):
        from .updates_view import run_primary

        run_primary(self.app, self.app.root)
        self.refresh()

    def dismiss(self):
        self.dismissed = self.release()
        self.frame.place_forget()
