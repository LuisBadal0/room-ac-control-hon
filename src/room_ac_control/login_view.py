"""Welcome screen with a product hero and a contained sign-in form."""
from .i18n import tr, localized, refresh_on_language
import tkinter as tk
from tkinter import ttk

from .theme import C, ASSETS, font, paint, rounded, unit_photo, ac_art, blend, refresh_on_theme
from .login_loading import LoginLoadingAnimation


class LoginView:
    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.body)
        self.photo = unit_photo(app.root, 300)
        self.mark = tk.PhotoImage(master=app.root, file=str(ASSETS / "app-icon.png")).subsample(8)
        self.hero = tk.Canvas(self.frame, height=282, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", self.draw_hero)
        refresh_on_language(self.hero,self.draw_hero)
        refresh_on_theme(self.hero,self.draw_hero)
        self.surface = tk.Canvas(self.frame, height=380, highlightthickness=0)
        self.surface.pack(fill="x", pady=(0, 14))
        form = paint(tk.Frame(self.surface), bg="CARD")
        self.form_id = self.surface.create_window(0, 24, window=form, anchor="n")
        self.surface.bind("<Configure>", self.draw_card)
        refresh_on_theme(self.surface, self.draw_card)
        self.loading = False
        self.animation = LoginLoadingAnimation(self.surface)
        localized(paint(tk.Label(form, text="Welcome home", font=font(18, "black")), bg="CARD", fg="TEXT")).pack(anchor="w")
        localized(paint(tk.Label(form, text="Sign in with your hOn account.", font=font(10)), bg="CARD", fg="MUTED")).pack(anchor="w", pady=(2, 16))
        app.email = self.field(form, "Email address")
        app.password = self.field(form, "Password", password=True)
        app.login_button = localized(ttk.Button(form, text="Sign in  →", style="Login.Accent.TButton", command=app.connect))
        app.login_button.pack(fill="x", pady=(6, 14))
        app.remember_account = tk.BooleanVar(value=False)
        localized(ttk.Checkbutton(form, text="Remember me on this computer", style="Login.TCheckbutton", variable=app.remember_account)).pack(anchor="w")
        localized(paint(tk.Label(self.frame, text="Remember me saves your email and password, encrypted by Windows.\nPrograms running as your Windows user can decrypt them.",
                 font=font(9), wraplength=460, justify="center"), bg="BG", fg="MUTED")).pack()
        diagnostic_link = localized(paint(tk.Label(self.frame, text="Export diagnostics", font=font(9, "bold"), cursor="hand2"),
                                          bg="BG", fg="BRAND"))
        diagnostic_link.pack(pady=(6,0))
        diagnostic_link.bind("<Button-1>", lambda event: app.export_diagnostics())
        app.password.bind("<Return>", lambda event: app.connect())
        app.email.bind("<Return>", lambda event: app.password.focus_set())

    def field(self, parent, label, password=False):
        localized(paint(tk.Label(parent, text=label, font=font(10, "bold")), bg="CARD", fg="TEXT")).pack(anchor="w", pady=(0, 6))
        border = paint(tk.Frame(parent, highlightthickness=1), bg="CARD", highlightbackground="FIELD", highlightcolor="BRAND")
        border.pack(fill="x", pady=(0, 14))
        entry = tk.Entry(border, relief="flat", bd=0, highlightthickness=0, font=font(11),
                         show="•" if password else "")
        paint(entry, bg="CARD", fg="TEXT", insertbackground="TEXT", disabledbackground="CARD",
              disabledforeground="MUTED", selectbackground="SOFT", selectforeground="ON_SOFT")
        entry.pack(fill="x", padx=13, pady=11)
        # A thicker brand ring marks focus, as in hOn's text fields.
        entry.bind("<FocusIn>", lambda event: (border.configure(highlightthickness=2, highlightbackground=C.BRAND),
                                               entry.pack_configure(pady=10)))
        entry.bind("<FocusOut>", lambda event: (border.configure(highlightthickness=1, highlightbackground=C.FIELD),
                                                entry.pack_configure(pady=11)))
        return entry

    def draw_hero(self, event=None):
        c = self.hero
        c.delete("all")
        c.configure(bg=C.BG)
        center = c.winfo_width()/2
        c.create_image(center, 46, image=self.mark)
        c.create_text(center, 104, text=tr(c, "Room AC Control"), fill=C.TEXT, font=font(21, "black"))
        c.create_text(center, 133, text=tr(c, "Your room. Your comfort."), fill=C.MUTED, font=font(11))
        c.create_text(center, 155, text=tr(c, "for hOn accounts · unofficial"), fill=C.MUTED, font=font(9))
        ac_art(c, center, 204, photo=self.photo)
        stroke = blend(C.BRAND, C.BG, .45)
        for offset in range(-3, 4):
            x = center+offset*31
            c.create_line(x, 252, x-5, 258, x+5, 266, x, 274, fill=stroke, width=2, smooth=True, capstyle="round")

    def draw_card(self, event=None):
        c = self.surface
        width = c.winfo_width()
        c.configure(bg=C.BG)
        c.delete("surface")
        rounded(c, 1, 1, width-1, 379, 24, fill=C.CARD, outline=C.EDGE, tags="surface")
        c.tag_lower("surface")
        c.coords(self.form_id, width/2, 24)
        c.itemconfigure(self.form_id, width=max(200, width-48))
        self.animation.resize()

    def set_loading(self, active, automatic=False):
        self.loading = active
        self.surface.itemconfigure(self.form_id, state="hidden" if active else "normal")
        if active:
            self.surface.focus_set()
            self.animation.start(automatic)
        else:
            self.animation.stop()

    def close(self):
        self.loading = False
        self.animation.close()
