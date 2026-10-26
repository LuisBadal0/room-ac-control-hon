"""Theme-aware ttk styles; rounded button surfaces keep native ttk input and focus behavior."""
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

from .theme import C, font


def _surface(master, fill, outline=None, radius=12):
    scale = 3
    image = Image.new("RGBA", (40*scale,40*scale))
    if fill or outline:
        ImageDraw.Draw(image).rounded_rectangle((scale,scale,39*scale,39*scale),
                                               radius=radius*scale,fill=fill,outline=outline,width=scale)
    return ImageTk.PhotoImage(image.resize((40,40),Image.Resampling.LANCZOS),master=master)


def _palettes():
    # normal, disabled, pressed, active (hover), focus
    return {
        "TButton": ((C.CARD,C.EDGE),(C.DISABLED,None),(C.STRONG,C.BRAND),(C.HOVER,C.BRAND),(C.CARD,C.BRAND)),
        "Accent.TButton": ((C.BRAND,None),(C.DISABLED,None),(C.BRAND_ACTIVE,None),(C.BRAND_ACTIVE,None),(C.BRAND,C.TEXT)),
        "Ghost.TButton": ((None,None),(None,None),(C.STRONG,None),(C.SURFACE,None),(None,C.BRAND)),
    }


def _install_buttons(root, style):
    # Nine-slice images keep the corners round at every button width. One set
    # of elements exists per palette; switching themes swaps the layouts.
    cache = root.__dict__.setdefault("button_theme_images", {})
    if C.mode not in cache:
        cache[C.mode] = []
        for name, palettes in _palettes().items():
            surfaces = [_surface(root, *palette, radius=8 if name == "Ghost.TButton" else 12) for palette in palettes]
            cache[C.mode].extend(surfaces)
            style.element_create(f"RoomAC.{C.mode}.{name}.surface","image",surfaces[0],("disabled",surfaces[1]),
                                 ("pressed",surfaces[2]),("active",surfaces[3]),("focus",surfaces[4]),
                                 border=12,padding=0,sticky="nsew")
    for name in _palettes():
        style.layout(name,[(f"RoomAC.{C.mode}.{name}.surface",{"sticky":"nsew","children":[
            ("Button.padding",{"sticky":"nsew","children":[("Button.label",{"sticky":"nsew"})]})]})])
    for name, foreground in (("TButton",C.TEXT),("Accent.TButton",C.ON_BRAND),("Ghost.TButton",C.TEXT)):
        style.configure(name,background=C.BG,foreground=foreground,padding=(14,10),font=font(10,"bold"),anchor="center")
        style.map(name,foreground=[("disabled",C.ON_DISABLED if name != "Ghost.TButton" else C.FAINT)],background=[])
    style.configure("Ghost.TButton",padding=(10,8))
    style.configure("Login.Accent.TButton",padding=(14,12),font=font(11,"bold"),background=C.CARD)
    style.configure("Card.TButton",background=C.CARD)
    style.configure("Card.Ghost.TButton",background=C.CARD)


def configure_styles(root):
    """Apply the active palette to every ttk style the app uses; safe to repeat."""
    style = ttk.Style(root)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    field = dict(fieldbackground=C.CARD, foreground=C.TEXT, bordercolor=C.FIELD, lightcolor=C.CARD,
                 darkcolor=C.CARD, insertcolor=C.TEXT, selectbackground=C.SOFT, selectforeground=C.ON_SOFT)
    style.configure("TFrame", background=C.BG)
    style.configure("Card.TFrame", background=C.CARD)
    style.configure("TLabel", background=C.BG, foreground=C.TEXT, font=font(10))
    style.configure("Muted.TLabel", foreground=C.MUTED)
    style.configure("Heading.TLabel", font=font(18, "black"))
    style.configure("TCheckbutton", background=C.BG, foreground=C.TEXT, font=font(10), indicatorbackground=C.CARD,
                    indicatorforeground=C.ON_BRAND, upperbordercolor=C.FIELD, lowerbordercolor=C.FIELD)
    style.map("TCheckbutton", background=[("active", C.BG)], foreground=[("disabled", C.MUTED)],
              indicatorbackground=[("selected", C.BRAND), ("active", C.HOVER)])
    style.configure("Login.TCheckbutton", background=C.CARD, foreground=C.TEXT, font=font(10))
    style.map("Login.TCheckbutton", background=[("active", C.CARD)], foreground=[("disabled", C.MUTED)])
    style.configure("TCombobox", background=C.CARD, arrowcolor=C.BRAND, padding=5, **field)
    style.map("TCombobox", fieldbackground=[("readonly", C.CARD)], foreground=[("readonly", C.TEXT)],
              bordercolor=[("focus", C.BRAND)])
    style.configure("TEntry", padding=8, **field)
    style.map("TEntry", bordercolor=[("focus", C.BRAND)])
    style.configure("TSpinbox", background=C.CARD, arrowcolor=C.BRAND, padding=5, **field)
    style.map("TSpinbox", bordercolor=[("focus", C.BRAND)])
    style.configure("TNotebook", background=C.BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=C.CARD, foreground=C.MUTED, padding=(14,9), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", C.SOFT)], foreground=[("selected", C.ON_SOFT)])
    style.configure("Vertical.TScrollbar", background=C.RAISED if C.mode == "light" else C.SURFACE, troughcolor=C.BG,
                    bordercolor=C.BG, lightcolor=C.BG, darkcolor=C.BG, arrowcolor=C.MUTED, borderwidth=0)
    style.map("Vertical.TScrollbar", background=[("active", C.STRONG)])
    root.option_add("*TCombobox*Listbox.background", C.CARD)
    root.option_add("*TCombobox*Listbox.foreground", C.TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", C.SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", C.ON_SOFT)
    _install_buttons(root, style)
    return style


def install_button_theme(root, style=None):
    """Kept for callers of the earlier API."""
    return configure_styles(root)
