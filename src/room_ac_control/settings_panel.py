"""The dashboard's Settings dropdown: appearance, language, updates and sign-out.

It opens inside the main window, under the Settings button, over a dimmed page."""
import math
import time
import tkinter as tk

from . import __version__
from .i18n import LANGUAGES, tr, refresh_on_language
from .theme import C, font, icon, measure, rounded, blend, refresh_on_theme
from .updates_view import update_message, primary_label, primary_enabled, run_primary
from .widgets import Overlay, raise_widget, section_label, switch
from .smooth import texts as canvas_texts
from .smooth import aa_arc, aa_line, aa_oval, aa_rect, aa_text

WIDTH = 330
LOOKS = (("system", "Follow Windows"), ("light", "Light mode"), ("dark", "Dark mode"))
# Each preview shows the page colour on its left and right half, and a dial ring.
PREVIEWS = {"system": ("#EEF1F5", "#0E1116", "#7A8594"), "light": ("#EEF1F5", "#EEF1F5", "#D5DBE3"),
            "dark": ("#0E1116", "#0E1116", "#252C36")}


class SettingsPanel:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        app.settings_panel = self
        self.overlay = Overlay(self.root, self.close)
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=600, highlightthickness=0, takefocus=True)
        self.regions = []
        self.spin_job = None
        self.place()
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Escape>", lambda event: self.close())
        self.canvas.bind("<Left>", lambda event: self.step_look(-1))
        self.canvas.bind("<Right>", lambda event: self.step_look(1))
        self.canvas.bind("<Up>", lambda event: self.step_language(-1))
        self.canvas.bind("<Down>", lambda event: self.step_language(1))
        refresh_on_theme(self.canvas, self.draw)
        refresh_on_language(self.canvas, self.draw)
        self.unlisten = app.updater.listen(self.updated)
        self.draw()
        self.canvas.focus_set()

    def place(self):
        width = self.root.winfo_width()
        x = width-20-WIDTH if width > WIDTH+40 else 190
        self.canvas.place(x=x, y=44)
        raise_widget(self.canvas)

    # Drawing

    def draw(self):
        c = self.canvas
        if not c.winfo_exists():
            return
        c.delete("all")
        self.regions = []
        c.configure(bg=C.BG)
        inner = WIDTH-36
        tone = self.app.dial_accent()
        y = 18
        text = lambda x, y, value, size, color=None, anchor="w", weight="normal": aa_text(c, 
            x, y, text=value, anchor=anchor, fill=color or C.TEXT, font=font(size, weight))
        # Header.
        text(18, y+15, tr(c, "Settings"), -18, weight="black")
        rounded(c, WIDTH-48, y, WIDTH-18, y+30, 8, fill=C.SURFACE, outline="")
        aa_line(c, WIDTH-38, y+10, WIDTH-28, y+20, fill=C.MUTED, width=2.2, capstyle="round")
        aa_line(c, WIDTH-28, y+10, WIDTH-38, y+20, fill=C.MUTED, width=2.2, capstyle="round")
        self.regions.append(((WIDTH-48, y, WIDTH-18, y+30), self.close))
        y += 44
        # Appearance.
        section_label(c, 18, y+6, "Appearance")
        y += 20
        tile = (inner-16)/3
        for index, (value, label) in enumerate(LOOKS):
            x1 = 18+index*(tile+8)
            x2 = x1+tile
            active = value == self.app.theme_preference
            left, right, ring = PREVIEWS[value]
            middle = (x1+x2)/2
            rounded(c, x1, y, x2, y+64, 12, fill=left, outline="")
            if right != left:
                rounded(c, middle, y, x2, y+64, 12, fill=right, outline="")
                aa_rect(c, middle, y, middle+14, y+64, fill=right, outline="")
            rounded(c, x1, y, x2, y+64, 12, fill="", outline=tone if active else C.TRACK, width=2)
            aa_arc(c, middle-14, y+9, middle+14, y+37, start=-45, extent=270, style="arc", outline=ring, width=5)
            aa_arc(c, middle-14, y+9, middle+14, y+37, start=225, extent=-120, style="arc", outline=tone, width=5)
            rounded(c, x1+12, y+50, x2-12, y+56, 3, fill=ring, outline="")
            text(middle, y+77, tr(c, label), -11, tone if active else C.MUTED, "center", "bold")
            self.regions.append(((x1, y, x2, y+86), lambda value=value: self.pick_look(value)))
        y += 86+14
        aa_line(c, 18, y, WIDTH-18, y, fill=C.TRACK)
        y += 14
        # Language.
        section_label(c, 18, y+6, "Language")
        y += 20
        rows = [("system", tr(c, "System language"), "SYS")] + [
            (value, label, "PT" if value == "pt-PT" else "EN") for value, label in LANGUAGES.items()]
        for value, label, code in rows:
            active = value == self.app.i18n.preference
            fill = blend(tone, C.CARD, .14) if active else C.CARD
            rounded(c, 18, y, WIDTH-18, y+42, 12, fill=fill, outline=tone if active else fill, width=1.5)
            rounded(c, 30, y+10, 60, y+32, 6, fill=C.SURFACE, outline="")
            text(45, y+21, code, -10, C.MUTED, "center", "black")
            text(72, y+21, label, -13, weight="bold")
            aa_oval(c, WIDTH-48, y+12, WIDTH-30, y+30, outline=tone if active else C.FAINT, width=2)
            if active:
                aa_oval(c, WIDTH-43, y+17, WIDTH-35, y+25, fill=tone, outline="")
            self.regions.append(((18, y, WIDTH-18, y+42), lambda value=value: self.pick_language(value)))
            y += 46
        y += 10
        aa_line(c, 18, y, WIDTH-18, y, fill=C.TRACK)
        y += 14
        # Updates.
        section_label(c, 18, y+6, "Updates")
        y += 22
        # The status can wrap to several lines (Portuguese often does): the rows below move down.
        bottom = self.draw_update(c, y, text, tone)
        y = max(y+50, bottom+14)
        supported = self.app.updater.supported
        text(18, y+18, tr(c, "Check automatically"), -13, C.TEXT if supported else C.FAINT, weight="semibold")
        switch(c, WIDTH-58, y+6, self.app.updater.enabled and supported, tone)
        if supported:
            self.regions.append(((18, y, WIDTH-18, y+36), self.toggle_automatic))
        y += 36+14
        aa_line(c, 18, y, WIDTH-18, y, fill=C.TRACK)
        y += 10
        # Sign out.
        available = bool(self.app.selected) and not self.app.busy and not self.app.demo
        ink = C.DANGER if available else C.FAINT
        icon(c, "signout", 30, y+17, ink, scale=.62, bg=C.CARD)
        label = tr(c, "Sign out")
        text(46, y+17, label, -13, ink, weight="black")
        if available:
            self.regions.append(((18, y, 56+measure(c, label, -13, "black"), y+34), self.logout))
        y += 34+18
        # The card itself, behind everything drawn above.
        card = rounded(c, 1, 1, WIDTH-1, y, 22, fill=C.CARD, outline=C.TRACK)
        c.tag_lower(card)
        c.configure(height=y+1)

    def update_status(self):
        """Icon, sub-line and colour for the update row, like the mockup's three states."""
        updater = self.app.updater
        state = updater.state
        if state == "checking":
            return "refresh", tr(self.canvas, "Checking for updates…"), C.MUTED, True
        if state == "current":
            return "check", tr(self.canvas, "You have the latest version."), C.OK, False
        if state == "idle" and getattr(updater, "checked", None):
            clock = updater.checked.strftime("%H:%M")
            return "update", tr(self.canvas, "Last checked today at {time}").format(time=clock), C.MUTED, False
        headline, detail = update_message(updater)
        failed = state == "failed"
        return ("alert" if failed else "update"), tr(self.canvas, headline), (C.DANGER if failed else C.MUTED), False

    def draw_update(self, c, y, text, tone):
        glyph, line, color, spinning = self.update_status()
        done = glyph == "check"
        fill = blend(C.OK, C.CARD, .14) if done else blend(tone, C.CARD, .14)
        rounded(c, 18, y, 56, y+38, 11, fill=fill, outline="")
        ink = C.OK if done else (C.DANGER if glyph == "alert" else tone)
        turn = (time.monotonic()*360) % 360 if spinning else 0
        icon(c, glyph, 37, y+19, ink, scale=.68, bg=fill, rotate=turn)
        if spinning and self.spin_job is None:
            self.spin_job = self.canvas.after(60, self.spin)
        label = tr(c, primary_label(self.app.updater))
        enabled = primary_enabled(self.app.updater)
        accent_button = primary_label(self.app.updater) == "Update"
        x2 = WIDTH-18
        x1 = x2-measure(c, label, -12, "black")-26
        fill = (tone if accent_button else C.SURFACE) if enabled else C.SURFACE
        rounded(c, x1, y+1, x2, y+37, 10, fill=fill, outline="" if accent_button else C.TRACK)
        text((x1+x2)/2, y+19, label, -12, (C.ON_BRAND if accent_button else C.TEXT) if enabled else C.FAINT,
             "center", "black")
        if enabled:
            self.regions.append(((x1, y, x2, y+38), self.primary))
        # The version line opens update details (What's new) and diagnostics.
        version = text(66, y+9, tr(c, "Version {version}").format(version=__version__), -13, weight="black")
        right = c.bbox(version)[2]
        self.regions.append(((66, y, right, y+18), lambda: self.app.open_updates()))
        status = aa_text(c, 66, y+18, text=line, anchor="nw", fill=color, font=font(-11, "semibold"), width=x1-76)
        return max(y+38, c.bbox(status)[3])

    def spin(self):
        self.spin_job = None
        if self.canvas.winfo_exists() and self.app.updater.state == "checking":
            self.draw()

    # Actions

    def recapture(self):
        """Re-dim the page after it changed colour or language underneath the panel."""
        self.overlay.refresh((self.canvas,))
        self.place()

    def pick_look(self, value):
        if value != self.app.theme_preference:
            self.app.set_theme(value)
            self.recapture()
        self.draw()

    def pick_language(self, value):
        if value != self.app.i18n.preference:
            self.app.set_language(value)
            self.recapture()
        self.draw()

    def step_look(self, direction):
        values = [value for value, label in LOOKS]
        index = values.index(self.app.theme_preference) if self.app.theme_preference in values else 0
        self.pick_look(values[max(0, min(len(values)-1, index+direction))])
        return "break"

    def step_language(self, direction):
        values = ["system", *LANGUAGES]
        index = values.index(self.app.i18n.preference) if self.app.i18n.preference in values else 0
        self.pick_language(values[max(0, min(len(values)-1, index+direction))])
        return "break"

    def primary(self):
        """Check now, or Update once a signed release is found."""
        run_primary(self.app, self.root)

    def texts(self):
        return [text for item, text in canvas_texts(self.canvas)]

    def toggle_automatic(self):
        self.app.set_auto_update(not self.app.updater.enabled)
        self.draw()

    def updated(self):
        if self.canvas.winfo_exists():
            self.draw()

    def click(self, event):
        for (x1, y1, x2, y2), action in list(self.regions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                action()
                return

    def motion(self, event):
        inside = any(x1 <= event.x <= x2 and y1 <= event.y <= y2 for (x1, y1, x2, y2), _ in self.regions)
        self.canvas.configure(cursor="hand2" if inside else "")

    def logout(self):
        self.close()
        self.app.logout()

    def close(self):
        self.unlisten()
        if self.spin_job is not None and self.canvas.winfo_exists():
            self.canvas.after_cancel(self.spin_job)
        self.spin_job = None
        self.app.settings_panel = None
        self.app.settings_button.set_pressed(False)
        if self.canvas.winfo_exists():
            self.canvas.destroy()
        self.overlay.destroy()
