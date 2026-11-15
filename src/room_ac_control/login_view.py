"""The sign-in screen, drawn with the dashboard's pieces.

The unit picture with its animated airflow, a rounded card with rounded fields, a
switch for Remember me, the accent pill button and messages inside the card, in the
same type scale, colours and spacing as the dashboard, its sheets and Settings.
"""

import tkinter as tk
from tkinter import ttk

from .airflow import AirflowAnimation
from .i18n import refresh_on_language, tr
from .login_loading import LoginLoadingAnimation
from .smooth import aa_oval, aa_text
from .theme import C, font, icon, measure, refresh_on_theme, rounded, unit_photo
from .widgets import PillButton, section_label, switch

# The welcome message is the card's own subtitle, so it is not repeated as a message.
QUIET = {"Sign in to connect to your air conditioner.", "Signed out."}
HERO_HEIGHT = 282
TOP = 18  # Space above the unit picture, as below the dashboard's room name.
UNIT_WIDTH = 270  # The dashboard's picture size.


class Field(tk.Canvas):
    """A rounded text field with a leading glyph; the outline takes the accent on focus."""

    HEIGHT = 50

    def __init__(self, parent, glyph, password=False):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0)
        self.glyph = glyph
        self.entry = tk.Entry(
            self, relief="flat", bd=0, highlightthickness=0, font=font(11), show="•" if password else ""
        )
        self.window = self.create_window(46, self.HEIGHT / 2, window=self.entry, anchor="w")
        self.entry.bind("<FocusIn>", lambda event: self.draw(), add="+")
        self.entry.bind("<FocusOut>", lambda event: self.draw(), add="+")
        self.bind("<Button-1>", lambda event: self.entry.focus_set())
        self.bind("<Configure>", lambda event: self.draw())
        refresh_on_theme(self, self.draw)
        self.draw()

    def draw(self):
        width = max(self.winfo_width(), 100)
        focused = self.focus_get() is self.entry
        enabled = str(self.entry.cget("state")) != "disabled"
        self.delete("box")
        self.configure(bg=C.CARD)
        rounded(
            self,
            1,
            1,
            width - 1,
            self.HEIGHT - 1,
            14,
            fill=C.SURFACE,
            outline=C.BRAND if focused else C.SURFACE,
            width=1.5,
            tags="box",
        )
        icon(
            self,
            self.glyph,
            24,
            self.HEIGHT / 2,
            C.BRAND if focused else C.MUTED,
            scale=0.62,
            bg=C.SURFACE,
            tags=("box",),
        )
        self.tag_lower("box")
        self.itemconfigure(self.window, width=width - 62)
        self.entry.configure(
            bg=C.SURFACE,
            fg=C.TEXT if enabled else C.MUTED,
            insertbackground=C.TEXT,
            disabledbackground=C.SURFACE,
            disabledforeground=C.MUTED,
            selectbackground=C.SOFT,
            selectforeground=C.ON_SOFT,
        )


class LoginView:
    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.body)
        self.photo = unit_photo(app.root, UNIT_WIDTH)
        self.hero = tk.Canvas(self.frame, height=HERO_HEIGHT, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", self.draw_hero)
        refresh_on_language(self.hero, self.draw_hero)
        refresh_on_theme(self.hero, self.draw_hero)
        self.airflow = AirflowAnimation(self.hero)
        self.surface = tk.Canvas(self.frame, height=420, highlightthickness=0)
        self.surface.pack(fill="x")
        self.loading = False
        self.animation = LoginLoadingAnimation(self.surface)
        self.email_field = Field(self.surface, "mail")
        self.password_field = Field(self.surface, "lock", password=True)
        app.email, app.password = self.email_field.entry, self.password_field.entry
        app.remember_account = tk.BooleanVar(value=False)
        app.remember_account.trace_add("write", lambda *args: self.draw_card())
        app.login_button = PillButton(
            self.surface, "Sign in", app.connect, glyph="next", kind="accent", height=50, size=-14, bg=lambda: C.CARD
        )
        self.windows = {
            "email": self.surface.create_window(0, 0, window=self.email_field, anchor="nw", tags="form"),
            "password": self.surface.create_window(0, 0, window=self.password_field, anchor="nw", tags="form"),
            "button": self.surface.create_window(0, 0, window=app.login_button, anchor="nw", tags="form"),
        }
        self.remember_box = None
        self.surface.bind("<Configure>", self.draw_card)
        self.surface.bind("<Button-1>", self.click)
        refresh_on_theme(self.surface, self.draw_card)
        refresh_on_language(self.surface, self.draw_card)
        self.diagnostics = PillButton(
            self.frame, "Export diagnostics", app.export_diagnostics, glyph="sliders", kind="ghost", height=40, size=-12
        )
        self.diagnostics.pack(pady=(10, 0))
        app.password.bind("<Return>", lambda event: app.connect())
        app.email.bind("<Return>", lambda event: app.password.focus_set())

    def draw_hero(self, event=None):
        """The unit picture with the dashboard's airflow, the app name and an unofficial chip."""
        c = self.hero
        c.delete("all")
        c.configure(bg=C.BG)
        center = c.winfo_width() / 2
        c.create_image(center, TOP, image=self.photo, anchor="n")
        # The same animated airflow as the dashboard, in its neutral colour.
        self.airflow.set_state({"power": "On", "mode": "Auto"}, center, 76 + TOP, 230, 30)
        aa_text(c, center, 152 + TOP, text=tr(c, "Room AC Control"), fill=C.TEXT, font=font(-26, "black"), tags="title")
        aa_text(
            c, center, 182 + TOP, text=tr(c, "Your room. Your comfort."), fill=C.MUTED, font=font(-14), tags="tagline"
        )
        label = tr(c, "for hOn accounts · unofficial")
        width = measure(c, label, -11, "bold") + 36
        rounded(c, center - width / 2, 210 + TOP, center + width / 2, 236 + TOP, 13, fill=C.CARD, outline="")
        aa_oval(c, center - width / 2 + 10, 220 + TOP, center - width / 2 + 16, 226 + TOP, fill=C.MUTED, outline="")
        aa_text(
            c,
            center - width / 2 + 22,
            223 + TOP,
            text=label,
            anchor="w",
            fill=C.MUTED,
            font=font(-11, "bold"),
            tags="unofficial",
        )

    def message(self):
        status = getattr(self.app, "status", None)  # The App creates it after this view.
        text = status.get() if status is not None else ""
        return "" if text in QUIET else tr(self.surface, text)

    def draw_card(self, event=None):
        c = self.surface
        width = max(c.winfo_width(), 300)
        c.configure(bg=C.BG)
        c.delete("surface", "drawn")
        inner = width - 48
        text = lambda x, y, value, size, color=None, anchor="w", weight="normal", wrap=None: aa_text(
            c,
            x,
            y,
            text=value,
            anchor=anchor,
            fill=color or C.TEXT,
            font=font(size, weight),
            tags="drawn",
            **({"width": wrap} if wrap else {}),
        )
        y = 26
        text(24, y + 12, tr(c, "Welcome home"), -22, weight="black")
        text(24, y + 40, tr(c, "Sign in with your hOn account."), -13, C.MUTED)
        y += 70
        c.addtag_withtag("drawn", section_label(c, 24, y + 6, "Email address"))
        c.coords(self.windows["email"], 24, y + 18)
        c.itemconfigure(self.windows["email"], width=inner, height=Field.HEIGHT)
        y += 18 + Field.HEIGHT + 16
        c.addtag_withtag("drawn", section_label(c, 24, y + 6, "Password"))
        c.coords(self.windows["password"], 24, y + 18)
        c.itemconfigure(self.windows["password"], width=inner, height=Field.HEIGHT)
        y += 18 + Field.HEIGHT + 18
        # Remember me, as a switch row like Settings.
        tone = C.BRAND
        text(24, y + 12, tr(c, "Remember me on this computer"), -13, weight="semibold")
        note = tr(
            c,
            "Remember me saves your email and password, encrypted by Windows.\n"
            "Programs running as your Windows user can decrypt them.",
        ).replace("\n", " ")
        note_item = text(24, y + 26, note, -11, C.MUTED, "nw", wrap=inner - 64)
        switch(c, width - 64, y + 2, self.app.remember_account.get(), tone, tags=("drawn",))
        bounds = c.bbox(note_item)
        bottom = bounds[3] if bounds else y + 56
        self.remember_box = (24, y - 4, width - 24, bottom + 4)
        y = bottom + 18
        if self.app.login_button.fixed_width != inner:
            self.app.login_button.fixed_width = inner
            self.app.login_button.draw()
        c.coords(self.windows["button"], 24, y)
        c.itemconfigure(self.windows["button"], width=inner, height=50)
        y += 50 + 16
        message = self.message()
        if message:
            box = rounded(c, 24, y, width - 24, y + 44, 12, fill=C.SOFT, outline="", tags="drawn")
            item = text(40, y + 22, message, -12, C.ON_SOFT, wrap=inner - 32)
            bounds = c.bbox(item)
            if bounds and bounds[3] - bounds[1] > 24:
                # A long message wraps: grow the box around it.
                height = bounds[3] - bounds[1] + 22
                c.delete(box, item)
                rounded(c, 24, y, width - 24, y + height, 12, fill=C.SOFT, outline="", tags="drawn")
                text(40, y + 11, message, -12, C.ON_SOFT, "nw", wrap=inner - 32)
                y += height + 16
            else:
                y += 44 + 16
        y += 8
        c.addtag_withtag("form", "drawn")
        rounded(c, 1, 1, width - 1, y, 24, fill=C.CARD, outline=C.EDGE, tags="surface")
        c.tag_lower("surface")
        c.configure(height=y + 2)
        if self.loading:
            c.itemconfigure("form", state="hidden")
        self.animation.resize()

    def click(self, event):
        box = self.remember_box
        if not self.loading and box and box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
            if str(self.app.email.cget("state")) != "disabled":
                self.app.remember_account.set(not self.app.remember_account.get())

    def set_enabled(self, value):
        state = "normal" if value else "disabled"
        for field in (self.email_field, self.password_field):
            field.entry.configure(state=state)
            field.draw()
        self.app.login_button.set_enabled(value)

    def set_loading(self, active, automatic=False):
        self.loading = active
        self.surface.itemconfigure("form", state="hidden" if active else "normal")
        if active:
            self.surface.focus_set()
            self.animation.start(automatic)
        else:
            self.animation.stop()

    def close(self):
        self.loading = False
        self.airflow.close()
        self.animation.close()
