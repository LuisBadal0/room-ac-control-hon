"""Dark welcome screen with a product hero and a contained sign-in form."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from .theme import BG, CARD, TEXT, MUTED, ACCENT, rounded, unit_photo, ac_art


class LoginView:
    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.body)
        self.photo = unit_photo(app.root, 300)
        self.mark = tk.PhotoImage(master=app.root, file=str(Path(__file__).parent / "assets" / "app-mark.png"))
        self.hero = tk.Canvas(self.frame, height=225, bg=BG, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", self.draw_hero)
        self.surface = tk.Canvas(self.frame, height=378, bg=BG, highlightthickness=0)
        self.surface.pack(fill="x", pady=(0, 14))
        form = tk.Frame(self.surface, bg=CARD)
        self.form_id = self.surface.create_window(0, 20, window=form, anchor="n")
        self.surface.bind("<Configure>", self.draw_card)
        tk.Label(form, text="Welcome home", bg=CARD, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(form, text="Sign in with your hOn account.", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 18))
        app.email = self.field(form, "Email address")
        app.password = self.field(form, "Password", password=True)
        app.login_button = ttk.Button(form, text="Sign in  →", style="Login.Accent.TButton", command=app.connect)
        app.login_button.pack(fill="x", pady=(3, 11))
        app.remember_account = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Remember me on this computer", style="Login.TCheckbutton", variable=app.remember_account).pack(anchor="w")
        tk.Label(self.frame, text="Saved sign-in is encrypted by Windows.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack()
        app.password.bind("<Return>", lambda event: app.connect())
        app.email.bind("<Return>", lambda event: app.password.focus_set())

    def field(self, parent, label, password=False):
        tk.Label(parent, text=label, bg=CARD, fg=ACCENT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 5))
        border = tk.Frame(parent, bg="#262b26", highlightbackground="#343a32", highlightthickness=1)
        border.pack(fill="x", pady=(0, 14))
        entry = tk.Entry(border, bg="#262b26", fg=TEXT, insertbackground=ACCENT,
                         disabledbackground="#262b26", disabledforeground=MUTED,
                         relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 11),
                         show="•" if password else "", selectbackground="#516550")
        entry.pack(fill="x", padx=13, pady=10)
        entry.bind("<FocusIn>", lambda event: border.configure(highlightbackground=ACCENT))
        entry.bind("<FocusOut>", lambda event: border.configure(highlightbackground="#343a32"))
        return entry

    def draw_hero(self, event=None):
        c = self.hero
        c.delete("all")
        center = c.winfo_width()/2
        c.create_image(center, 32, image=self.mark)
        c.create_text(center, 85, text="Room AC Control", fill=TEXT, font=("Segoe UI", 25, "bold"))
        c.create_text(center, 115, text="Your room. Your comfort.", fill=MUTED, font=("Segoe UI", 11))
        c.create_text(center, 139, text="for hOn accounts · unofficial", fill=MUTED, font=("Segoe UI", 8))
        ac_art(c, center, 174, photo=self.photo)

    def draw_card(self, event=None):
        c = self.surface
        width = c.winfo_width()
        c.delete("surface")
        rounded(c, 1, 1, width-1, 377, 20, fill=CARD, outline="#2b3029", tags="surface")
        c.tag_lower("surface")
        c.coords(self.form_id, width/2, 20)
        c.itemconfigure(self.form_id, width=max(200, width-48))
