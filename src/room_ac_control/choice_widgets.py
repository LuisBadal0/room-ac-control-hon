"""Theme-matched tile selectors in place of native popup menus."""
import tkinter as tk

from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, rounded, icon


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
        self.window.title(title)
        self.window.configure(bg=BG)
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, title, self.close, maximize=False)
        body = tk.Frame(self.window, bg=BG, padx=22, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text="Select an option", bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(5, 18))
        viewport = tk.Canvas(body, bg=BG, width=456, height=min(480, ((len(options)+1)//2)*98), highlightthickness=0)
        viewport.pack(fill="x")
        grid = tk.Frame(viewport, bg=BG)
        viewport.create_window(0, 0, window=grid, anchor="nw")
        grid.bind("<Configure>", lambda event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta/120), "units"))
        self.tiles = []
        for index, option in enumerate(options):
            active = matches(option["value"], current)
            tile = tk.Canvas(grid, bg=BG, width=220, height=86, highlightthickness=0, cursor="hand2", takefocus=True)
            tile.grid(row=index//2, column=index%2, padx=(0, 12), pady=(0, 12))
            def draw(hover=False, widget=tile, item=option, active=active):
                widget.delete("all")
                rounded(widget, 1, 1, 219, 85, 12, fill="#30372b" if hover or active else CARD, outline=ACCENT if active or hover else "", width=1)
                glyph = "moon" if "night" in item["label"].lower() else item.get("glyph", "snow")
                icon(widget, glyph, 23, 24)
                widget.create_text(46, 24, text=item["label"], anchor="w", fill=TEXT, width=143, font=("Segoe UI", 12, "bold"))
                if active: widget.create_text(197, 24, text="✓", fill=ACCENT, font=("Segoe UI", 12, "bold"))
                widget.create_text(15, 57, text=item.get("description", ""), anchor="w", fill=MUTED, font=("Segoe UI", 9), width=192)
            draw()
            tile.bind("<Enter>", lambda event, draw=draw: draw(True))
            tile.bind("<Leave>", lambda event, draw=draw: draw(False))
            tile.bind("<FocusIn>", lambda event, draw=draw: draw(True))
            tile.bind("<FocusOut>", lambda event, draw=draw: draw(False))
            tile.bind("<Button-1>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<Return>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<space>", lambda event, value=option["value"]: self.choose(value))
            tile.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta/120), "units"))
            self.tiles.append(tile)
        tk.Button(body, text="Cancel", command=self.close, bg=CARD, fg=TEXT, relief="flat", padx=15, pady=8,
                  activebackground="#30372b", activeforeground=TEXT, font=("Segoe UI", 10)).pack(anchor="e", pady=(12, 0))
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
        super().__init__(parent, width=236, height=40, bg=BG, highlightthickness=0, cursor="hand2", takefocus=True)
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
        self.draw()

    def draw(self):
        self.delete("all")
        rounded(self, 1, 1, 235, 39, 9, fill=HOVER if self.hover else CARD, outline=ACCENT if self.hover else "#394035")
        self.create_text(13, 20, text=self.variable.get(), anchor="w", fill=TEXT, font=("Segoe UI", 10))

    def highlight(self, active):
        self.hover = active
        self.draw()

    def open(self):
        ChoicePanel(self, self.title, self.choices or [{"label": label, "value": label} for label in self.options],
                    self.variable.get(), self.variable.set)
