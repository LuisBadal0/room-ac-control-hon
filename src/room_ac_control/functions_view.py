"""Dashboard-style controls, with everyday presets separate from maintenance."""
import tkinter as tk
from tkinter import ttk

from .controller import function_group, readable, mode_choices, mode_label
from .choice_widgets import ChoicePanel
from .control_choices import mode_icon, airflow_icon, airflow_choices
from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, GREEN, rounded, ac_art, unit_photo, control_card
from .canvas_hover import CanvasHover
from .airflow import AirflowAnimation

SECTIONS = (("settings", "Settings"), ("everyday", "Everyday use"), ("maintenance", "Maintenance"))


def matches_search(item, query):
    """Match words in names, descriptions and user-facing adjustable options."""
    parts = [item["label"], item.get("description", ""), item.get("command_label", "")]
    specs = [item["spec"]] if item["kind"] == "setting" else item.get("form", {}).get("parameters", [])
    for spec in specs:
        parts.append(spec["label"])
        parts.extend(spec.get("options", {}))
    text = " ".join(parts).casefold()
    return all(word in text for word in query.casefold().split())


def section_items(device, section):
    items = []
    if section in {"settings", "maintenance"}:
        for key, spec in device.get("controls", {}).items():
            if key == "onOffStatus":
                continue
            group = function_group(key, label=spec["label"])
            if (section == "maintenance") != (group == "maintenance"):
                continue
            items.append({"kind": "setting", "key": key, "label": spec["label"], "spec": spec})
    if section in {"everyday", "maintenance"}:
        for command, entry in device.get("commands", {}).items():
            for form in entry["forms"]:
                group = form.get("group", function_group(command, form["category"], form["label"]))
                if group != section:
                    continue
                items.append({"kind": "function", "command": command, "form": form,
                              "label": form["label"], "command_label": entry["label"]})
    if section == "everyday":
        existing = {item["label"].lower().replace(" ", "") for item in items}
        for option in mode_choices(device):
            if option["label"].endswith(" Night") and option["label"].lower().replace(" ", "") not in existing:
                items.append({"kind": "night", "label": option["label"], "changes": option["value"], "description": option["description"]})
    return items


def glyph_for(name):
    name = name.lower()
    if name in {"auto","cool","dry","heat","fan","cool night","heat night"}: return mode_icon(name)
    if "fan" in name: return "fan"
    if "airflow" in name or "wind" in name: return "wind"
    if "sleep" in name or "night" in name or "quiet" in name: return "moon"
    if "eco" in name or "health" in name: return "leaf"
    if "cool" in name or "mode" in name or "temp" in name: return "snow"
    return "wind"


class FunctionsView:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        app.dialog = self.window
        self.window.title("Room AC Control · All functions")
        self.window.geometry("740x820")
        self.window.minsize(620, 700)
        self.window.configure(bg=BG)
        self.window.transient(app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, "Room AC Control · All functions", self.close, maximize=False)
        self.photo = unit_photo(self.window, 300)
        self.section = "settings"
        self.settings_changes = dict(app.dirty)
        self.card_widgets = []
        self.selected_function = None
        self.body = ttk.Frame(self.window, padding=(22, 16, 22, 18))
        self.body.pack(fill="both", expand=True)
        self.hero = tk.Canvas(self.body, bg=BG, height=211, highlightthickness=0)
        self.hero.pack(fill="x")
        self.airflow = AirflowAnimation(self.hero)
        self.hero.bind("<Configure>", lambda event: self.draw_hero())
        self.navigation = tk.Canvas(self.body, bg=BG, height=51, highlightthickness=0)
        self.navigation_hover = CanvasHover(self.navigation)
        self.navigation.pack(fill="x", pady=(0, 12))
        self.navigation.bind("<Configure>", lambda event: self.draw_navigation())
        self.navigation.bind("<Button-1>", self.navigate)
        self.search = tk.StringVar()
        search_bar = tk.Frame(self.body, bg=CARD, highlightthickness=1, highlightbackground="#394035")
        search_bar.pack(fill="x", pady=(0, 12))
        tk.Label(search_bar, text="Search", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(12, 8))
        self.search_entry = tk.Entry(search_bar, textvariable=self.search, bg=CARD, fg=TEXT,
                                     insertbackground=TEXT, relief="flat", font=("Segoe UI", 11))
        self.search_entry.pack(side="left", fill="x", expand=True, pady=11)
        self.clear_search = tk.Button(search_bar, text="Clear", command=lambda: self.search.set(""),
                                      bg=CARD, fg=MUTED, activebackground=HOVER, activeforeground=TEXT,
                                      relief="flat", font=("Segoe UI", 10), cursor="hand2", padx=12)
        self.clear_search.pack(side="right", padx=(8, 4))
        self.search_entry.bind("<FocusIn>", lambda event: search_bar.configure(highlightbackground=ACCENT))
        self.search_entry.bind("<FocusOut>", lambda event: search_bar.configure(highlightbackground="#394035"))
        self.search_entry.bind("<Escape>", self.reset_search)
        self.window.bind("<Control-f>", self.focus_search)
        self.note = tk.StringVar()
        ttk.Label(self.body, textvariable=self.note, style="Muted.TLabel", wraplength=680).pack(anchor="w", pady=(0, 14))
        area = ttk.Frame(self.body)
        area.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(area, bg=BG, highlightthickness=0)
        self.bar = ttk.Scrollbar(area, orient="vertical", command=self.scroll.yview)
        self.bar.pack(side="right", fill="y")
        self.scroll.pack(side="left", fill="both", expand=True)
        self.scroll.configure(yscrollcommand=self.bar.set)
        self.inner = ttk.Frame(self.scroll)
        self.inner_id = self.scroll.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda event: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.scroll.bind("<Configure>", self.resize)
        self.scroll.bind("<MouseWheel>", self.wheel)
        self.footer = ttk.Frame(self.body)
        self.footer.pack(fill="x", pady=(16, 0))
        self.apply_button = ttk.Button(self.footer, text="Apply changes", style="Accent.TButton", command=self.apply)
        self.apply_button.pack(side="left", expand=True, fill="x", padx=(0, 10))
        ttk.Button(self.footer, text="Close", command=self.close).pack(side="right")
        ttk.Button(self.footer, text="Diagnostics", command=app.export_diagnostics).pack(side="right", padx=(0, 8))
        self.search.trace_add("write", lambda *args: self.render_section())
        self.render_section()
        self.window.after_idle(self.focus_search)

    def draw_hero(self):
        c = self.hero
        c.delete("all")
        width = max(c.winfo_width(), 550)
        c.create_text(3, 15, text="All functions", anchor="w", fill=TEXT, font=("Segoe UI", 22, "bold"))
        c.create_text(width-3, 15, text=self.app.selected["name"], anchor="e", fill=MUTED, font=("Segoe UI", 10))
        ac_art(c, width/2, 93, photo=self.photo)
        c.create_text(width/2, 192, text=self.app.selected["model"], fill=MUTED, font=("Segoe UI", 9))
        self.airflow.set_state(self.app.selected,width/2,135,235,42)

    def draw_navigation(self):
        c = self.navigation
        c.delete("all")
        width = max(c.winfo_width(), 550)
        self.navigation_hover.reset()
        for index, (key, label) in enumerate(SECTIONS):
            x = index*width/3
            selected = key == self.section and not self.search.get().strip()
            surface=rounded(c, x+2, 3, x+width/3-6, 47, 12, fill=ACCENT if selected else CARD, outline="")
            self.navigation_hover.add((x+2,3,x+width/3-6,47),surface,{"fill":ACCENT if selected else CARD,"outline":""},
                                      {"fill":"#cbc6ad" if selected else HOVER,"outline":ACCENT})
            c.create_text(x+width/6-2, 25, text=label, fill=BG if selected else TEXT, font=("Segoe UI", 11, "bold" if selected else "normal"))
        self.navigation_hover.update()

    def navigate(self, event):
        index = min(2, int(event.x / max(self.navigation.winfo_width(), 550) * 3))
        self.section = ("settings", "everyday", "maintenance")[index]
        if self.search.get(): self.search.set("")
        else: self.render_section()

    def focus_search(self, event=None):
        if self.selected_function is None:
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, "end")
        return "break"

    def reset_search(self, event=None):
        self.search.set("")
        return "break"

    def resize(self, event):
        self.scroll.itemconfigure(self.inner_id, width=event.width)
        for card in self.card_widgets:
            card.event_generate("<<RedrawCard>>")

    def wheel(self, event):
        self.scroll.yview_scroll(-int(event.delta/120), "units")

    def render_section(self):
        for child in self.inner.winfo_children(): child.destroy()
        self.card_widgets = []
        self.selected_function = None
        self.search_entry.configure(state="normal")
        self.clear_search.configure(state="normal" if self.search.get() else "disabled")
        self.draw_navigation()
        self.scroll.yview_moveto(0)
        notes = {
            "settings": "Comfort, airflow and everyday features. Select changes, then apply.",
            "everyday": "Presets for normal use. Select a card to review and start a preset.",
            "maintenance": "Cleaning and service routines. Select a card to review its controls.",
        }
        query = self.search.get().strip()
        groups = []
        for section, title in SECTIONS:
            if query or section == self.section:
                items = [dict(item, section=section) for item in section_items(self.app.selected, section)
                         if matches_search(item, query)]
                groups.append((title, items))
        count = sum(len(items) for _, items in groups)
        self.note.set(f"{count} {'result' if count == 1 else 'results'} across all functions" if query else notes[self.section])
        for column in range(3): self.inner.columnconfigure(column, weight=1, uniform="cards")
        row = 0
        self.visible_items = []
        for title, items in groups:
            if not items: continue
            if query:
                ttk.Label(self.inner, text=title, style="Muted.TLabel", font=("Segoe UI", 10, "bold")).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(4, 10))
                row += 1
            self.visible_items.extend(items)
            for index, item in enumerate(items):
                card = self.card(item)
                card.grid(row=row+index//3, column=index%3, sticky="nsew", padx=(0, 10), pady=(0, 12))
            row += (len(items)+2)//3
        if not count:
            text = "No matching functions. Try another word or clear the search." if query else "No functions in this section are exposed by your AC."
            ttk.Label(self.inner, text=text, style="Muted.TLabel", wraplength=520).grid(row=0, column=0, columnspan=3, pady=40)
        self.update_apply()

    def setting_value(self, spec):
        key = spec["key"]
        spec = self.app.selected.get("controls", {}).get(key, spec)
        if key in self.settings_changes: return self.settings_changes[key]
        return spec["value"] if spec.get("reported") else None

    def refresh_status(self):
        # Redraw values in place; keep open menus, preset forms, scroll position and edits.
        self.draw_hero()
        for card in self.card_widgets:
            card.event_generate("<<RedrawCard>>")

    def card(self, item):
        card = tk.Canvas(self.inner, bg=BG, highlightthickness=0, width=200, height=103, cursor="hand2", takefocus=True)
        card.hover_style = CanvasHover(card)
        def draw(event=None):
            card.delete("all")
            width = max(card.winfo_width(), 150)
            card.hover_style.reset()
            glyph=glyph_for(item["label"])
            heading=item["label"]
            if item["kind"] == "setting":
                spec = item["spec"]
                value = self.setting_value(spec)
                if spec["kind"] == "enum":
                    from .dashboard import equal
                    label = next((label for label, option in spec["options"].items() if equal(option, value)), "Unknown")
                else:
                    label = "Unknown" if value is None else f"{float(value):g}"
                if spec["key"] == "tempSel" and value is not None: label += "°C"
                if spec["key"] == "machMode":
                    label = mode_label(self.app.selected,self.settings_changes)
                    glyph = mode_icon(label)
                elif spec["key"] in {"windDirectionVertical","windDirectionHorizontal"}:
                    glyph = airflow_icon(label)
            else:
                heading = "Maintenance routine" if item.get("section", self.section) == "maintenance" else "Preset" if item.get("command") == "startProgram" or item["kind"] == "night" else "Function"
                label = item["label"]
            surface=control_card(card,1,1,width-2,heading,label,glyph)
            card.hover_style.add((0,0,width,103),surface,{"fill":CARD,"outline":""},{"fill":HOVER,"outline":ACCENT})
            if item["kind"] == "setting" and item["spec"]["key"] in self.settings_changes:
                card.create_oval(width-22, 21, width-16, 27, fill=ACCENT, outline="")
            card.hover_style.update()
        def choose(event=None):
            if item["kind"] != "setting": self.configure_function(item)
            else: self.edit_setting(item["spec"], card)
        card.bind("<Configure>", draw)
        card.bind("<<RedrawCard>>", draw)
        card.bind("<Button-1>", choose)
        card.bind("<Return>", choose)
        card.bind("<space>", choose)
        card.bind("<MouseWheel>", self.wheel)
        self.card_widgets.append(card)
        return card

    def change_setting(self, key, value):
        from .dashboard import equal
        spec = self.app.selected["controls"][key]
        if spec.get("reported") and equal(value, spec["value"]):
            self.settings_changes.pop(key, None)
        else:
            self.settings_changes[key] = str(value)
        for card in self.card_widgets: card.event_generate("<<RedrawCard>>")
        self.update_apply()

    def edit_setting(self, spec, card):
        if spec["kind"] == "enum":
            if spec["key"] == "machMode":
                options = mode_choices(self.app.selected)
                current = {key: self.setting_value(self.app.selected["controls"][key]) for key in ("machMode", "silentSleepStatus") if key in self.app.selected["controls"]}
                def selected(patch):
                    for key,value in self.app.memory.mode_values(self.app.selected,patch).items(): self.change_setting(key,value)
            else:
                options = (airflow_choices(spec) if spec["key"] in {"windDirectionVertical","windDirectionHorizontal"}
                           else [{"label":label,"value":value,"glyph":glyph_for(spec["label"])} for label,value in spec["options"].items()])
                current = self.setting_value(spec)
                def selected(value):
                    patch={spec["key"]:value}
                    from .controller import code
                    mode=self.app.selected.get("controls",{}).get("machMode",{})
                    current_mode=self.setting_value(mode) if mode else None
                    if spec["key"]=="silentSleepStatus" and code(current_mode) in {"1","4"}:
                        patch["machMode"]=code(current_mode)
                        patch=self.app.memory.mode_values(self.app.selected,patch)
                    for key,new_value in patch.items():self.change_setting(key,new_value)
            self.choice_panel = ChoicePanel(self.window,spec["label"],options,current,selected)
            return
        window = tk.Toplevel(self.window)
        window.title(spec["label"])
        window.configure(bg=BG)
        window.transient(self.window)
        window.grab_set()
        def close_detail():
            window.destroy()
            self.window.grab_set()
        from .window_header import WindowHeader
        window.header = WindowHeader(window, spec["label"], close_detail, maximize=False)
        body = ttk.Frame(window, padding=22)
        body.pack(fill="both", expand=True)
        getter, initial = self.app.field(body, spec, self.setting_value(spec), use_reported=True)
        ttk.Label(body, text=f"Range {spec['min']:g}–{spec['max']:g} · Step {spec['step']:g}", style="Muted.TLabel").pack(anchor="w", pady=12)
        def done():
            value = getter()
            if value is not None: self.change_setting(spec["key"], value)
            close_detail()
        ttk.Button(body, text="Set value", style="Accent.TButton", command=done).pack(fill="x")
        window.protocol("WM_DELETE_WINDOW", close_detail)

    def configure_function(self, item):
        self.selected_function = item
        maintenance = item.get("section", self.section) == "maintenance"
        # Preserve an open preset's draft until the user returns to the cards.
        self.search_entry.configure(state="disabled")
        self.clear_search.configure(state="disabled")
        for child in self.inner.winfo_children(): child.destroy()
        self.card_widgets = []
        # Reset equal-width card columns for the full-width detail form.
        for column in range(3): self.inner.columnconfigure(column, weight=0, uniform="")
        self.inner.columnconfigure(0, weight=1)
        detail = ttk.Frame(self.inner, padding=(12, 8))
        detail.grid(row=0, column=0, sticky="ew", columnspan=3)
        ttk.Button(detail, text="‹ Back to cards", command=self.render_section).pack(anchor="w", pady=(0, 18))
        ttk.Label(detail, text=item["label"], font=("Segoe UI", 19, "bold")).pack(anchor="w", pady=(0, 6))
        description = "Cleaning / service routine" if maintenance else "Everyday comfort preset"
        ttk.Label(detail, text=description, style="Muted.TLabel").pack(anchor="w", pady=(0, 20))
        saved=self.app.memory.function_values(self.app.selected["id"],item["command"],item["form"]) if item["kind"]=="function" else {}
        fields = {spec["key"]: self.app.field(detail, spec, saved.get(spec["key"])) for spec in item.get("form", {}).get("parameters", [])}
        if item["kind"] == "night":
            ttk.Label(detail,text=item["description"],style="Muted.TLabel").pack(anchor="w",pady=14)
        if not fields:
            ttk.Label(detail, text="This routine has no adjustable options.", style="Muted.TLabel").pack(anchor="w", pady=14)
        text = "This routine may interrupt the current operation." if maintenance else "Starting this preset may turn the AC on and replace its settings."
        ttk.Label(detail, text=text, wraplength=580, style="Muted.TLabel").pack(anchor="w", pady=20)
        def run():
            if item["kind"] == "night":
                self.close()
                self.app.action("on",dict(item["changes"]))
                return
            request = {"command": item["command"], "category": item["form"]["category"],
                       "parameters": {key: get() for key, (get, initial) in fields.items() if get() is not None}}
            self.close()
            self.app.action("execute", request)
        button = "Start maintenance routine" if maintenance else "Start preset" if item.get("command") == "startProgram" or item["kind"] == "night" else "Run function"
        ttk.Button(detail, text=button, style="Accent.TButton", command=run).pack(fill="x")
        self.scroll.yview_moveto(0)
        self.update_apply()

    def update_apply(self):
        self.apply_button.configure(state="normal" if self.settings_changes and self.selected_function is None else "disabled")

    def apply(self):
        if not self.settings_changes or self.selected_function is not None: return
        changes = dict(self.settings_changes)
        self.close()
        self.app.action("configure", changes)

    def close(self):
        self.app.dialog = None
        self.airflow.close()
        self.window.destroy()
