"""Theme-matched tile selectors in place of native popup menus."""
from .i18n import tr, localized, localized_title, refresh_on_language
import tkinter as tk
from tkinter import ttk

from .theme import C, font, paint, rounded, icon, refresh_on_theme


def matches(value, current):
    if isinstance(value, dict) and isinstance(current, dict):
        return all(matches(v,current.get(key)) for key,v in value.items())
    try:
        return float(value)==float(current)
    except (ValueError,TypeError):
        return str(value)==str(current)


class ChoicePanel:
    def __init__(self, parent, title, options, current, selected):
        self.parent, self.options, self.selected = parent, options, selected
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        localized_title(self.window,title)
        paint(self.window, bg="BG")
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, title, self.close, maximize=False)
        body = paint(tk.Frame(self.window, padx=22, pady=16), bg="BG")
        body.pack(fill="both", expand=True)
        localized(paint(tk.Label(body, text=title, font=font(18, "black"), anchor="w"), bg="BG", fg="TEXT")).pack(fill="x")
        localized(paint(tk.Label(body, text="Select an option", font=font(10), anchor="w"), bg="BG", fg="MUTED")).pack(fill="x", pady=(2, 16))
        viewport = paint(tk.Canvas(body, width=456, height=min(480, ((len(options)+1)//2)*98), highlightthickness=0), bg="BG")
        viewport.pack(fill="x")
        grid = paint(tk.Frame(viewport), bg="BG")
        viewport.create_window(0, 0, window=grid, anchor="nw")
        grid.bind("<Configure>", lambda event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta/120), "units"))
        self.tiles = []
        for index, option in enumerate(options):
            active = matches(option["value"], current)
            tile = tk.Canvas(grid, width=222, height=86, highlightthickness=0, cursor="hand2", takefocus=True)
            tile.grid(row=index//2, column=index%2, padx=(0, 12), pady=(0, 12))
            def draw(hover=False, widget=tile, item=option, active=active):
                widget.delete("all")
                widget.configure(bg=C.BG)
                fill = C.SOFT if active else C.HOVER if hover else C.CARD
                rounded(widget, 1, 1, 221, 85, 12, fill=fill, outline=C.BRAND if active or hover else C.EDGE,
                        width=1.5 if active or hover else 1)
                glyph = "moon" if "night" in item["label"].lower() else item.get("glyph", "snow")
                circle = C.CARD if active else C.SOFT
                widget.create_oval(14, 12, 46, 44, fill=circle, outline="")
                icon(widget, glyph, 30, 28, C.ON_SOFT, scale=.72, bg=circle)
                foreground = C.ON_SOFT if active else C.TEXT
                label = tr(widget, item["label"]) if item.get("translate_label",True) else item["label"]
                widget.create_text(56, 28, text=label, anchor="w", fill=foreground, width=132, font=font(11, "bold"))
                if active: icon(widget, "check", 201, 28, C.ON_SOFT, scale=.8, bg=fill)
                description = tr(widget, item.get("description", "")) if item.get("translate_label",True) else item.get("description","")
                widget.create_text(15, 66, text=description, anchor="w", fill=C.ON_SOFT if active else C.MUTED, font=font(9), width=194)
            draw()
            refresh_on_language(tile,draw)
            refresh_on_theme(tile,draw)
            tile.bind("<Enter>", lambda event, draw=draw: draw(True))
            tile.bind("<Leave>", lambda event, draw=draw: draw(False))
            tile.bind("<FocusIn>", lambda event, draw=draw: draw(True))
            tile.bind("<FocusOut>", lambda event, draw=draw: draw(False))
            tile.bind("<Button-1>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<Return>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<space>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta/120), "units"))
            self.tiles.append(tile)
        localized(ttk.Button(body, text="Cancel", command=self.close)).pack(anchor="e", pady=(4, 0))
        self.window.update_idletasks()
        owner = parent.winfo_toplevel()
        x = max(0, owner.winfo_rootx()+(owner.winfo_width()-self.window.winfo_reqwidth())//2)
        y = max(0, owner.winfo_rooty()+(owner.winfo_height()-self.window.winfo_reqheight())//2)
        self.window.geometry(f"+{x}+{y}")
        if self.tiles:
            index=next((i for i,option in enumerate(options) if matches(option["value"],current)),0)
            self.tiles[index].focus_set()

    def choose(self, value):
        self.close()
        self.selected(value)

    def close(self):
        if self.window.winfo_exists(): self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()


class SelectField(tk.Canvas):
    def __init__(self, parent, variable, options, title, choices=None):
        super().__init__(parent, width=236, height=44, highlightthickness=0, cursor="hand2", takefocus=True)
        self.variable, self.options, self.title = variable, options, title
        self.choices = choices
        self.hover = False
        variable.trace_add("write", lambda *args: self.draw())
        self.bind("<Button-1>", lambda event: self.open())
        self.bind("<Return>", lambda event: self.open())
        self.bind("<space>", lambda event: self.open())
        self.bind("<Enter>",lambda event:self.highlight(True))
        self.bind("<Leave>",lambda event:self.highlight(False))
        self.bind("<FocusIn>",lambda event:self.highlight(True))
        self.bind("<FocusOut>",lambda event:self.highlight(False))
        refresh_on_language(self,self.draw)
        refresh_on_theme(self,self.draw)
        self.draw()

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        rounded(self, 1, 1, 235, 43, 8, fill=C.HOVER if self.hover else C.CARD, outline=C.BRAND if self.hover else C.FIELD)
        self.create_text(14, 22, text=tr(self, self.variable.get()), anchor="w", fill=C.TEXT, font=font(10))
        icon(self, "chevron", 214, 22, C.MUTED)

    def highlight(self, active):
        self.hover = active
        self.draw()

    def open(self):
        ChoicePanel(self, self.title, self.choices or [{"label": label, "value": label} for label in self.options],
                    self.variable.get(), self.variable.set)
