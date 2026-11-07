"""A room dropdown card, theme-matched room chooser and the round power button."""

import tkinter as tk
from tkinter import font as tkfont

from .choice_widgets import ChoicePanel
from .i18n import refresh_on_language, tr
from .smooth import aa_oval, aa_text
from .theme import C, accent, blend, font, icon, refresh_on_theme


class DevicePicker(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, height=58, highlightthickness=0, takefocus=False)
        self.command = command
        self.devices = []
        self.index = 0
        self.enabled = False
        self.hover = False
        self.name_font = tkfont.Font(self, font=font(-26, "black"))
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Button-1>", lambda event: self.open())
        self.bind("<Return>", lambda event: self.open())
        self.bind("<space>", lambda event: self.open())
        self.bind("<Enter>", lambda event: self.highlight(True))
        self.bind("<Leave>", lambda event: self.highlight(False))
        self.bind("<FocusIn>", lambda event: self.highlight(True))
        self.bind("<FocusOut>", lambda event: self.highlight(False))
        refresh_on_language(self, self.draw)
        refresh_on_theme(self, self.draw)

    def set_devices(self, devices):
        self.devices = devices
        self.index = 0
        self.draw()

    def current(self, index=None):
        if index is not None:
            if not 0 <= index < len(self.devices):
                raise IndexError("Device index is out of range")
            self.index = index
            self.draw()
        return self.index

    def set_enabled(self, enabled):
        self.enabled = enabled
        selectable = enabled and len(self.devices) > 1
        self.configure(cursor="hand2" if selectable else "", takefocus=selectable)
        self.draw()

    def highlight(self, active):
        self.hover = active
        self.draw()

    def set_status(self, text, connected):
        """The connection line under the room name, such as "Connected · 12:04"."""
        self.status, self.connected = text, connected
        self.draw()

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        width = max(240, self.winfo_width())
        selectable = self.enabled and len(self.devices) > 1
        if not self.devices:
            return
        device = self.devices[self.index]
        name = device["name"]
        available = width - 40
        if self.name_font.measure(name) > available:
            while name and self.name_font.measure(name + "…") > available:
                name = name[:-1]
            name += "…"
        title = aa_text(
            self, 0, 19, text=name, anchor="w", fill=C.TEXT if self.enabled else C.MUTED, font=self.name_font
        )
        if selectable:
            right = self.bbox(title)[2]
            icon(self, "chevron", right + 17, 20, C.BRAND if self.hover else C.MUTED, scale=0.75)
        connected = getattr(self, "connected", device.get("connection") == "CONNECTED")
        aa_oval(self, 1, 42.5, 8, 49.5, fill=C.OK if connected else C.FAINT, outline="")
        status = getattr(self, "status", "") or (
            "Connected" if connected else "Offline" if device.get("connection") == "DISCONNECTED" else "Unknown"
        )
        rooms = len(self.devices)
        line = f"{device['model']} · {tr(self, status)}" + (" · " + tr(self, f"{rooms} rooms") if rooms > 1 else "")
        aa_text(self, 14, 46, text=line, anchor="w", fill=C.MUTED, font=font(-12, "semibold"))

    def open(self):
        if not self.enabled or len(self.devices) < 2:
            return
        options = [
            {
                "label": device["name"],
                "description": device["model"],
                "value": index,
                "glyph": "unit",
                "translate_label": False,
            }
            for index, device in enumerate(self.devices)
        ]

        def choose(index):
            self.current(index)
            self.command()

        self.choice_panel = ChoicePanel(self, "Your air conditioners", options, self.index, choose)


class PowerButton(tk.Canvas):
    """Filled with the mode accent, with a soft glow, when the AC reports On; plain when Off."""

    SIZE, BUTTON = 76, 56

    def __init__(self, parent, command):
        super().__init__(
            parent, width=self.SIZE, height=self.SIZE, highlightthickness=0, takefocus=True, cursor="hand2"
        )
        self.command = command
        self.on, self.enabled, self.hover = False, False, False
        self.mode = None
        self.glow = {}
        self.bind("<Button-1>", lambda event: self.invoke())
        self.bind("<Return>", lambda event: self.invoke())
        self.bind("<space>", lambda event: self.invoke())
        self.bind("<Enter>", lambda event: self.highlight(True))
        self.bind("<Leave>", lambda event: self.highlight(False))
        refresh_on_theme(self, self.draw)
        self.draw()

    def set_state(self, on, enabled, mode=None):
        """mode is the displayed mode label; its accent is read when drawing, so themes repaint it."""
        self.on, self.enabled = on, enabled
        self.mode = mode
        self.configure(cursor="hand2" if enabled else "")
        self.draw()

    def highlight(self, active):
        self.hover = active
        self.draw()

    def invoke(self):
        if self.enabled:
            self.command()

    def glow_image(self, tone):
        """The mockup's 0 6px 24px shadow in the accent colour."""
        key = (tone, C.BG)
        if key not in self.glow:
            from PIL import Image, ImageDraw, ImageFilter, ImageTk

            scale = 2
            size = self.SIZE * scale
            mask = Image.new("L", (size, size), 0)
            radius = self.BUTTON / 2 * scale
            centre = (size / 2, size / 2 + 3 * scale)
            ImageDraw.Draw(mask).ellipse(
                (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
                fill=round(255 * (0.48 if C.mode == "dark" else 0.42)),
            )
            mask = mask.filter(ImageFilter.GaussianBlur(8 * scale))
            image = Image.composite(Image.new("RGB", (size, size), tone), Image.new("RGB", (size, size), C.BG), mask)
            self.glow[key] = ImageTk.PhotoImage(
                image.resize((self.SIZE, self.SIZE), Image.Resampling.LANCZOS), master=self
            )
        return self.glow[key]

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        hover = self.hover and self.enabled
        middle = self.SIZE / 2
        radius = self.BUTTON / 2
        box = (middle - radius, middle - radius - 3, middle + radius, middle + radius - 3)
        if self.on:
            tone = accent(self.mode) if self.mode else C.BRAND
            self.create_image(0, 0, image=self.glow_image(tone), anchor="nw")
            fill = blend(tone, C.BG, 0.85) if hover else tone
            outline, glyph = "", C.ON_BRAND
        else:
            fill, outline, glyph = (C.HOVER if hover else C.CARD), (C.BRAND if hover else ""), C.MUTED
        aa_oval(self, *box, fill=fill, outline=outline, width=1.5)
        icon(self, "power", middle, middle - 3, glyph if self.enabled else C.FAINT, bg=fill)
