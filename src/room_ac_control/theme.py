"""Light and dark palettes from the hOn design tokens, plus native vector artwork."""
from .i18n import tr
import ctypes
import itertools
import math
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
THEMES = ("system", "light", "dark")

# Light mirrors hOn's semantic colours. hOn 2.30.7 maps dark to the same values,
# so dark is built from hOn's own charcoal primitives with a lighter brand blue.
PALETTES = {
    "light": {
        "BG": "#F4F3EF", "SURFACE": "#EDECE8", "RAISED": "#E4E3D9", "STRONG": "#E4E3D9",
        "CARD": "#FFFFFF", "EDGE": "#E6E4DC", "HOVER": "#F7F6F2", "SEGMENT": "#FFFFFF",
        "TEXT": "#313131", "MUTED": "#6E6E6E", "FAINT": "#B0B0B0", "FIELD": "#8C8C8C",
        "BRAND": "#0A648B", "BRAND_ACTIVE": "#244766", "ON_BRAND": "#FFFFFF",
        "SOFT": "#C6DDE6", "ON_SOFT": "#244766", "TRACK": "#C6DDE6", "THUMB": "#FFFFFF",
        "OK": "#008000", "OK_BG": "#D1F6DB", "OK_TEXT": "#006008",
        "WARN_BG": "#FFF4D3", "WARN_TEXT": "#9A6000", "ECO": "#008000",
        "DANGER": "#D12E2E", "CLOSE_HOVER": "#D12E2E", "ON_DANGER": "#FFFFFF",
        "DISABLED": "#F4F4F4", "ON_DISABLED": "#6E6E6E",
    },
    "dark": {
        "BG": "#1C1C1E", "SURFACE": "#3A3A3C", "RAISED": "#2B2B2C", "STRONG": "#4A4A4A",
        "CARD": "#2B2B2C", "EDGE": "#38383A", "HOVER": "#333335", "SEGMENT": "#4A4A4A",
        "TEXT": "#F4F3EF", "MUTED": "#B0B0B0", "FAINT": "#6E6E6E", "FIELD": "#858585",
        "BRAND": "#74B4DB", "BRAND_ACTIVE": "#A7D4ED", "ON_BRAND": "#1C1C1E",
        "SOFT": "#244766", "ON_SOFT": "#C6DDE6", "TRACK": "#244766", "THUMB": "#F4F3EF",
        "OK": "#76E392", "OK_BG": "#14381F", "OK_TEXT": "#A4EDB6",
        "WARN_BG": "#3D3110", "WARN_TEXT": "#FFDE79", "ECO": "#99CC99",
        "DANGER": "#E76868", "CLOSE_HOVER": "#A21919", "ON_DANGER": "#FFFFFF",
        "DISABLED": "#313131", "ON_DISABLED": "#8E8E8E",
    },
}


class Colors:
    """The active palette; draw code reads it at draw time, so a switch is live."""
    def __init__(self, mode="light"):
        self.mode = None
        self.use(mode)

    def use(self, mode):
        mode = mode if mode in PALETTES else "light"
        self.__dict__.update(PALETTES[mode])
        self.mode = mode


C = Colors()


def windows_mode():
    """Windows stores the app mode as AppsUseLightTheme (0 dark, 1 light)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except (ImportError, OSError, TypeError, IndexError):
        return "light"


def resolve_theme(preference):
    return preference if preference in PALETTES else windows_mode()


def refresh_on_theme(widget, callback):
    # Direct callbacks, not a virtual event: Tk drops events for unmapped widgets,
    # such as the sign-in form while the dashboard is shown.
    widget.__dict__.setdefault("theme_callbacks", []).append(callback)


def paint(widget, **tokens):
    """Configure colour options by palette name and repaint them on a theme switch."""
    apply = lambda: widget.configure(**{option: getattr(C, token) for option, token in tokens.items()})
    apply()
    refresh_on_theme(widget, apply)
    return widget


def broadcast_theme(root):
    def visit(widget):
        children = list(widget.winfo_children())
        for callback in list(widget.__dict__.get("theme_callbacks", ())):
            if widget.winfo_exists():
                callback()
        for child in children:
            if child.winfo_exists():
                visit(child)
    visit(root)


def blend(color, background, strength):
    channels = []
    for index in (1, 3, 5):
        base = int(background[index:index+2], 16)
        target = int(color[index:index+2], 16)
        channels.append(f"{round(base+(target-base)*strength):02x}")
    return "#" + "".join(channels)


FONT, HEAVY = "Segoe UI", "Segoe UI Black"


def load_fonts():
    """Load the bundled Lato (SIL OFL) privately for this process; else keep Segoe UI."""
    global FONT, HEAVY
    try:
        add = ctypes.windll.gdi32.AddFontResourceExW
    except AttributeError:
        return False
    loaded = [add(str(ASSETS / "fonts" / f"Lato-{weight}.ttf"), 0x10, 0) > 0
              for weight in ("Regular", "Bold", "Black")]
    if all(loaded):
        FONT, HEAVY = "Lato", "Lato Black"
    return all(loaded)


load_fonts()


def font(size, weight="normal"):
    if weight == "black":
        return (HEAVY, size)
    return (FONT, size, "bold") if weight == "bold" else (FONT, size)


def measure(widget, text, size, weight="normal"):
    return tkfont.Font(widget, font=font(size, weight)).measure(text)


def unit_photo(master, width=390):
    """Load original, unbranded appliance artwork."""
    photo = tk.PhotoImage(master=master, file=str(ASSETS / "unit.png"))
    factor = max(1, math.ceil(photo.width() / width))
    return photo.subsample(factor)


def rounded(canvas, x1, y1, x2, y2, radius=12, **options):
    points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


_icon_ids = itertools.count()


def icon(canvas, name, x, y, color=None, scale=1, bg=None, tags=()):
    """Stroke glyphs drawn around (x, y) at about 24 px, then scaled in place."""
    color = color or C.BRAND
    bg = bg or C.CARD
    tag = f"icon-{next(_icon_ids)}"
    tags = (tag, *tags)
    line = lambda *p, width=1.6: canvas.create_line(*p, fill=color, width=width, capstyle="round", joinstyle="round", tags=tags)
    oval = lambda x1, y1, x2, y2, **o: canvas.create_oval(x1, y1, x2, y2, tags=tags, **({"outline": color, "width": 1.5} | o))
    if name.startswith("vane_"):
        # The louver progressively opens away from the fixed top edge.
        angle = math.radians((4, 21, 38, 55, 72)[int(name[-1])-1])
        line(x-12, y-9, x+12, y-9)
        line(x-12, y-9, x-12, y-4)
        line(x-10, y-4, x-10+23*math.cos(angle), y-4+23*math.sin(angle))
        oval(x-12, y-6, x-8, y-2, fill=color, outline="")
    elif name == "swing":
        line(x, y-12, x, y+12, width=1.8)
        line(x-5, y-7, x, y-12, x+5, y-7, width=1.8)
        line(x-5, y+7, x, y+12, x+5, y+7, width=1.8)
    elif name == "clock":
        oval(x-11, y-11, x+11, y+11)
        line(x, y-6, x, y, x+5, y+3)
    elif name == "unit":
        rounded(canvas, x-13, y-8, x+13, y+5, 3, fill="", outline=color, width=1.5, tags=tags)
        line(x-9, y+1, x+9, y+1)
        line(x-5, y+9, x-6, y+11)
        line(x, y+9, x, y+11)
        line(x+5, y+9, x+6, y+11)
    elif name == "snow":
        for angle in (90, 30, 150):
            dx, dy = 12*math.cos(math.radians(angle)), 12*math.sin(math.radians(angle))
            line(x-dx, y-dy, x+dx, y+dy)
            for sign in (-1, 1):
                ex, ey = x+sign*dx*.72, y+sign*dy*.72
                for offset in (-40, 40):
                    a = math.radians(angle+offset)
                    line(ex, ey, ex+sign*4*math.cos(a), ey+sign*4*math.sin(a))
    elif name == "fan":
        for angle in (0, 90, 180, 270):
            a = math.radians(angle)
            dx, dy = 7*math.cos(a), 7*math.sin(a)
            oval(x+dx-5, y+dy-5, x+dx+5, y+dy+5, width=1.4)
        oval(x-3, y-3, x+3, y+3, fill=bg, width=1.4)
    elif name == "moon":
        # A crescent outline: the outer disc minus an offset inner disc.
        (ox, oy, r), (ix, iy, ri) = (x, y, 10.5), (x+6, y-5, 9)
        inside_inner = lambda p: (p[0]-ix)**2+(p[1]-iy)**2 < ri*ri
        inside_outer = lambda p: (p[0]-ox)**2+(p[1]-oy)**2 < r*r
        circle = lambda cx, cy, radius: [(cx+radius*math.cos(math.radians(d)), cy+radius*math.sin(math.radians(d))) for d in range(0, 360, 6)]
        def run(points, keep):
            start = next(i for i in range(len(points)) if not keep(points[i-1]) and keep(points[i]))
            return [p for p in points[start:]+points[:start] if keep(p)]
        arc = run(circle(ox, oy, r), lambda p: not inside_inner(p))
        inner = run(circle(ix, iy, ri), inside_outer)
        if math.dist(inner[0], arc[-1]) > math.dist(inner[-1], arc[-1]):
            inner.reverse()
        canvas.create_polygon(*arc, *inner, fill="", outline=color, width=1.5, joinstyle="round", tags=tags)
    elif name == "wind":
        for offset, length in ((-6, 16), (0, 22), (6, 14)):
            line(x-12, y+offset, x+length-12, y+offset)
            canvas.create_arc(x+length-17, y+offset-7, x+length-6, y+offset+1, start=0, extent=170,
                              style="arc", outline=color, width=1.5, tags=tags)
    elif name == "leaf":
        canvas.create_polygon(x-10, y+9, x-8, y-3, x+2, y-9, x+11, y-11, x+9, y-1, x+2, y+7, x-6, y+10,
                              fill="", outline=color, width=1.6, smooth=True, tags=tags)
        line(x-10, y+11, x+3, y-2)
    elif name == "sun":
        oval(x-5, y-5, x+5, y+5)
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            line(x+8.5*math.cos(a), y+8.5*math.sin(a), x+12*math.cos(a), y+12*math.sin(a))
    elif name == "drop":
        canvas.create_polygon(x, y-12, x-8, y+1, x-7, y+9, x, y+12, x+7, y+9, x+8, y+1,
                              fill="", outline=color, width=1.5, smooth=True, tags=tags)
    elif name == "thermo":
        rounded(canvas, x-3, y-11, x+3, y+4, 3, fill="", outline=color, width=1.5, tags=tags)
        oval(x-5.5, y+2, x+5.5, y+13, fill=bg)
        line(x, y-4, x, y+7)
    elif name == "power":
        canvas.create_arc(x-10, y-10, x+10, y+10, start=125, extent=290, style="arc",
                          outline=color, width=2.2, tags=tags)
        line(x, y-12, x, y-1, width=2.2)
    elif name == "check":
        line(x-7, y, x-2, y+5, x+8, y-6, width=2.2)
    elif name == "chevron":
        line(x-6, y-3, x, y+3, x+6, y-3, width=2)
    elif name == "search":
        oval(x-8, y-8, x+5, y+5, width=1.8)
        line(x+4, y+4, x+9, y+9, width=1.8)
    elif name == "half":
        oval(x-9, y-9, x+9, y+9, width=1.6)
        canvas.create_arc(x-9, y-9, x+9, y+9, start=-90, extent=180, style="chord",
                          fill=color, outline=color, tags=tags)
    elif name == "monitor":
        rounded(canvas, x-11, y-9, x+11, y+5, 2, fill="", outline=color, width=1.5, tags=tags)
        line(x-5, y+10, x+5, y+10)
        line(x, y+5, x, y+10)
    elif name == "globe":
        oval(x-10, y-10, x+10, y+10)
        oval(x-4.5, y-10, x+4.5, y+10, width=1.3)
        line(x-10, y, x+10, y, width=1.3)
    elif name == "sliders":
        line(x-10, y-5, x+2, y-5)
        line(x+7, y-5, x+10, y-5)
        oval(x+2, y-7.5, x+7, y-2.5)
        line(x-10, y+5, x-5, y+5)
        line(x, y+5, x+10, y+5)
        oval(x-5, y+2.5, x, y+7.5)
    elif name == "sparkle":
        canvas.create_polygon(x, y-11, x+2.5, y-2.5, x+11, y, x+2.5, y+2.5, x, y+11, x-2.5, y+2.5, x-11, y, x-2.5, y-2.5,
                              fill="", outline=color, width=1.5, tags=tags)
    elif name == "wrench":
        line(x-8, y+8, x+2, y-2, width=3)
        oval(x, y-11, x+11, y, width=1.8)
        canvas.create_oval(x+4, y-12, x+12, y-4, fill=bg, outline=bg, tags=tags)
    if scale != 1:
        canvas.scale(tag, x, y, scale, scale)
    return tag


def control_card(canvas, x, y, width, label, value, glyph, scale=1, active=True, pending=False, height=104):
    """The same compact control surface on both screens."""
    surface = rounded(canvas, x, y, x+width, y+height, 12, fill=C.CARD,
                      outline=C.BRAND if pending else C.EDGE, width=1.5 if pending else 1)
    circle = C.SOFT if active else C.SURFACE
    canvas.create_oval(x+14, y+14, x+50, y+50, fill=circle, outline="")
    icon(canvas, glyph, x+32, y+32, C.ON_SOFT if active else C.MUTED, scale=.74, bg=circle)
    if pending:
        canvas.create_text(x+width-14, y+24, text=tr(canvas, "Changed"), anchor="e", fill=C.BRAND, font=font(8, "bold"))
        left = canvas.bbox(canvas.find_all()[-1])[0]
        canvas.create_oval(left-12, y+20, left-5, y+27, fill=C.BRAND, outline="")
    value = tr(canvas, value)
    multiline = tkfont.Font(canvas, font=font(11, "bold")).measure(value) > (width-28)*scale
    canvas.create_text(x+14, y+(60 if multiline else height-36), text=tr(canvas, label), anchor="w", width=width-28,
                       fill=C.MUTED, font=font(9))
    canvas.create_text(x+14, y+(70 if multiline else height-17), text=value, anchor="nw" if multiline else "w", width=width-24,
                       fill=C.TEXT, font=font(10 if multiline else 11, "bold"))
    return surface


def ac_art(canvas, x, y, running=False, target="23", photo=None):
    """Original appliance illustration; airflow is rendered separately."""
    if photo is not None:
        canvas.create_image(x,y,image=photo)
        return
    canvas.create_polygon(x+108,y-22,x+121,y-15,x+121,y+31,x+107,y+37,fill="#c7cbc5",outline="#929a90")
    rounded(canvas,x-108,y-30,x+111,y+37,7,fill="#f1f3ee",outline="#c6cdc2",width=1)
    canvas.create_polygon(x-100,y+14,x+105,y+22,x+102,y+35,x-100,y+27,fill="#171b17")
    for n in range(28):
        lx=x-94+n*7
        canvas.create_line(lx,y+18,lx,y+30,fill="#7e877b",width=.7)
    canvas.create_line(x-103,y-18,x+103,y-10,fill="#ffffff",width=2)
    canvas.create_text(x+79,y-15,text=tr(canvas, target),fill="#a1a89b",font=font(8))
