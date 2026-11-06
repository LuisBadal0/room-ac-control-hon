"""The dashboard's Settings panel: appearance, language, updates and sign-out."""
import tkinter as tk
from tkinter import ttk

from . import __version__
from .i18n import LANGUAGES, tr, localized, localized_title, refresh_on_language
from .theme import C, font, icon, paint, rounded, refresh_on_theme
from .updates_view import update_message, primary_label, primary_enabled, run_primary

SIZE = (400, 612)
LOOKS = (("system", "Follow Windows"), ("light", "Light mode"), ("dark", "Dark mode"))
# Each preview shows the page colour on its left and right half.
PREVIEWS = {"system": ("#EEF1F5", "#0E1116", "#7A8594"), "light": ("#EEF1F5", "#EEF1F5", "#C9D1DB"),
            "dark": ("#0E1116", "#0E1116", "#2A313B")}


def section(parent, text):
    label = localized(paint(tk.Label(parent, text=text.upper(), font=font(8, "bold"), anchor="w", bd=0),
                            bg="BG", fg="MUTED"))
    # Upper case is a presentation of the translated label.
    refresh_on_language(label, lambda: label.configure(text=tr(label, text).upper()))
    label.configure(text=tr(label, text).upper())
    return label


class SettingsPanel:
    def __init__(self, app):
        self.app = app
        root = app.root
        self.previous_grab = root.grab_current()
        self.window = tk.Toplevel(root)
        app.settings_panel = self
        localized_title(self.window, "Room AC Control · Settings")
        self.window.resizable(False, False)
        paint(self.window, bg="BG")
        self.window.transient(root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        from .window_header import WindowHeader
        # Open beside the Settings button, at the top right of the main window.
        x = root.winfo_rootx() + root.winfo_width() - SIZE[0] - 8
        y = root.winfo_rooty() + 44
        self.window.geometry("{}x{}+{}+{}".format(*SIZE, max(0, x), max(0, y)))
        self.header = WindowHeader(self.window, "Settings", self.close, maximize=False, size=SIZE)
        body = paint(tk.Frame(self.window, padx=20, pady=6), bg="BG")
        body.pack(fill="both", expand=True)

        section(body, "Appearance").pack(fill="x", pady=(0, 8))
        self.looks = paint(tk.Canvas(body, height=104, highlightthickness=0, cursor="hand2", takefocus=True), bg="BG")
        self.looks.pack(fill="x")
        self.looks.bind("<Configure>", lambda event: self.draw_looks())
        self.looks.bind("<Button-1>", self.pick_look)
        self.looks.bind("<Left>", lambda event: self.step_look(-1))
        self.looks.bind("<Right>", lambda event: self.step_look(1))
        refresh_on_theme(self.looks, self.draw_looks)
        refresh_on_language(self.looks, self.draw_looks)

        section(body, "Language").pack(fill="x", pady=(16, 8))
        self.languages = [("system", "System language", "SYS")] + [
            (value, label, "PT" if value == "pt-PT" else "EN") for value, label in LANGUAGES.items()]
        self.language_rows = paint(tk.Canvas(body, height=len(self.languages)*46, highlightthickness=0,
                                             cursor="hand2", takefocus=True), bg="BG")
        self.language_rows.pack(fill="x")
        self.language_rows.bind("<Configure>", lambda event: self.draw_languages())
        self.language_rows.bind("<Button-1>", self.pick_language)
        self.language_rows.bind("<Up>", lambda event: self.step_language(-1))
        self.language_rows.bind("<Down>", lambda event: self.step_language(1))
        refresh_on_theme(self.language_rows, self.draw_languages)
        refresh_on_language(self.language_rows, self.draw_languages)

        section(body, "Updates").pack(fill="x", pady=(16, 8))
        updates = ttk.Frame(body)
        updates.pack(fill="x")
        self.update_button = ttk.Button(updates, command=lambda: run_primary(app, self.window), cursor="hand2")
        self.update_button.pack(side="right", padx=(10, 0))
        self.update_card = paint(tk.Canvas(updates, height=72, highlightthickness=0), bg="BG")
        self.update_card.pack(side="left", fill="x", expand=True)
        self.update_card.bind("<Configure>", lambda event: self.draw_update())
        refresh_on_theme(self.update_card, self.draw_update)
        refresh_on_language(self.update_card, self.draw_update)
        self.automatic = tk.BooleanVar(self.window, value=app.updater.enabled)
        self.automatic_toggle = localized(ttk.Checkbutton(body, text="Check for updates automatically",
                                                          variable=self.automatic,
                                                          command=lambda: app.set_auto_update(self.automatic.get())))
        self.automatic_toggle.pack(anchor="w", pady=(10, 0))
        localized(ttk.Button(body, text="Update details and diagnostics", style="Ghost.TButton",
                             command=lambda: app.open_updates(self.window))).pack(anchor="w", pady=(4, 0))

        paint(tk.Frame(body, height=1), bg="EDGE").pack(fill="x", pady=(14, 10))
        self.sign_out = localized(ttk.Button(body, text="Sign out", style="Danger.Ghost.TButton", command=self.logout))
        self.sign_out.pack(anchor="w")
        self.sign_out.state(["!disabled"] if app.selected and not app.busy and not app.demo else ["disabled"])
        refresh_on_language(self.update_button, self.refresh_updates)
        self.unlisten = app.updater.listen(self.refresh_updates)
        self.refresh_updates()
        self.looks.focus_set()

    # Appearance

    def look_boxes(self):
        width = max(self.looks.winfo_width(), SIZE[0]-40)
        tile = (width-16)/3
        return [(value, label, index*(tile+8), index*(tile+8)+tile) for index, (value, label) in enumerate(LOOKS)]

    def draw_looks(self):
        c = self.looks
        c.delete("all")
        for value, label, x1, x2 in self.look_boxes():
            active = value == self.app.theme_preference
            left, right, ring = PREVIEWS[value]
            outline = C.BRAND if active else C.EDGE
            middle = (x1+x2)/2
            rounded(c, x1+1, 1, x2-1, 72, 12, fill=left, outline="")
            if right != left:
                rounded(c, middle, 1, x2-1, 72, 12, fill=right, outline="")
                c.create_rectangle(middle, 1, middle+14, 72, fill=right, outline="")
            rounded(c, x1+1, 1, x2-1, 72, 12, fill="", outline=outline, width=2.5 if active else 1)
            c.create_arc(middle-16, 12, middle+16, 44, start=-45, extent=270, style="arc", outline=ring, width=4)
            c.create_arc(middle-16, 12, middle+16, 44, start=135, extent=-120, style="arc", outline=C.BRAND, width=4)
            rounded(c, x1+14, 54, x2-14, 60, 3, fill=ring, outline="")
            c.create_text(middle, 88, text=tr(c, label), fill=C.BRAND if active else C.MUTED,
                          font=font(9, "bold"), width=x2-x1)

    def pick_look(self, event):
        self.looks.focus_set()
        for value, label, x1, x2 in self.look_boxes():
            if x1 <= event.x <= x2:
                self.app.set_theme(value)
                self.draw_looks()

    def step_look(self, direction):
        values = [value for value, label in LOOKS]
        index = values.index(self.app.theme_preference) if self.app.theme_preference in values else 0
        self.app.set_theme(values[max(0, min(len(values)-1, index+direction))])
        self.draw_looks()
        return "break"

    # Language

    def draw_languages(self):
        c = self.language_rows
        c.delete("all")
        width = max(c.winfo_width(), SIZE[0]-40)
        focused = c.focus_get() is c
        for index, (value, label, code) in enumerate(self.languages):
            top = index*46
            active = value == self.app.i18n.preference
            fill = C.SOFT if active else C.BG
            rounded(c, 1, top+1, width-1, top+41, 10, fill=fill,
                    outline=C.BRAND if active and focused else (C.BRAND if active else C.BG), width=1.5)
            rounded(c, 10, top+10, 42, top+32, 6, fill=C.SURFACE if not active else C.CARD, outline="")
            c.create_text(26, top+21, text=code, fill=C.MUTED, font=font(7, "bold"))
            text = tr(c, label) if value == "system" else label
            c.create_text(54, top+21, text=text, anchor="w", fill=C.ON_SOFT if active else C.TEXT, font=font(10, "bold"))
            c.create_oval(width-30, top+12, width-12, top+30, outline=C.BRAND if active else C.FAINT, width=2)
            if active:
                c.create_oval(width-25, top+17, width-17, top+25, fill=C.BRAND, outline="")

    def pick_language(self, event):
        self.language_rows.focus_set()
        index = int(event.y // 46)
        if 0 <= index < len(self.languages):
            self.app.set_language(self.languages[index][0])
            self.draw_languages()

    def step_language(self, direction):
        values = [value for value, label, code in self.languages]
        index = values.index(self.app.i18n.preference) if self.app.i18n.preference in values else 0
        self.app.set_language(values[max(0, min(len(values)-1, index+direction))])
        self.draw_languages()
        return "break"

    # Updates

    def draw_update(self):
        c = self.update_card
        c.delete("all")
        width = max(c.winfo_width(), 200)
        state = self.app.updater.state
        failed, current = state == "failed", state == "current"
        circle = C.DANGER_BG if failed else C.OK_BG if current else C.SOFT
        ink = C.DANGER_TEXT if failed else C.OK_TEXT if current else C.ON_SOFT
        c.create_oval(2, 10, 42, 50, fill=circle, outline="")
        icon(c, "alert" if failed else "check" if current else "update", 22, 30, ink, scale=.72, bg=circle)
        c.create_text(54, 16, text=tr(c, "Version {version}".format(version=__version__)), anchor="w",
                      fill=C.TEXT, font=font(10, "bold"))
        headline, detail = update_message(self.app.updater)
        c.create_text(54, 28, text=tr(c, headline), anchor="nw",
                      fill=C.OK_TEXT if current else C.MUTED, font=font(9), width=width-58)

    def refresh_updates(self):
        if not self.window.winfo_exists():
            return
        updater = self.app.updater
        self.automatic.set(updater.enabled)
        self.automatic_toggle.state(["!disabled"] if updater.supported else ["disabled"])
        label = primary_label(updater)
        self.update_button.configure(text=tr(self.update_button, label),
                                     style="Accent.TButton" if label == "Update" else "TButton")
        self.update_button.state(["!disabled"] if primary_enabled(updater) else ["disabled"])
        self.draw_update()

    def logout(self):
        self.close()
        self.app.logout()

    def close(self):
        self.unlisten()
        self.app.settings_panel = None
        self.app.settings_button.set_pressed(False)
        if self.window.winfo_exists():
            self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
