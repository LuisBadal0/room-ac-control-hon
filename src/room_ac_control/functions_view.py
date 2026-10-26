"""Dashboard-style controls, with everyday presets separate from maintenance."""
from .i18n import tr, localized, localized_title, refresh_on_language, TranslatedVariable, translator, search_text
import tkinter as tk
from tkinter import ttk

from .controller import function_group, readable, mode_choices, mode_label
from .choice_widgets import ChoicePanel
from .control_choices import mode_icon, airflow_icon, airflow_choices
from .theme import C, font, measure, paint, icon, rounded, ac_art, unit_photo, control_card, refresh_on_theme
from .worker import degrees
from .canvas_hover import CanvasHover
from .airflow import AirflowAnimation

SECTIONS = (("settings", "Settings"), ("everyday", "Everyday use"), ("maintenance", "Maintenance"))
SECTION_GLYPHS = {"settings": "sliders", "everyday": "sparkle", "maintenance": "wrench"}
NEUTRAL = {"Off", "Unknown", "Unavailable"}


def matches_search(item, query):
    """Match words in names, descriptions and user-facing adjustable options."""
    parts = [item["label"], item.get("description", ""), item.get("command_label", "")]
    specs = [item["spec"]] if item["kind"] == "setting" else item.get("form", {}).get("parameters", [])
    for spec in specs:
        parts.append(spec["label"])
        parts.extend(spec.get("options", {}))
    text = search_text(parts)
    return all(word in text for word in search_text([query]).split())


def section_items(device, section):
    items = []
    if section in {"settings", "maintenance"}:
        for key, spec in device.get("controls", {}).items():
            if key == "onOffStatus":
                continue
            group = function_group(key, label=spec["label"])
            if (section == "maintenance") != (group == "maintenance"):
                continue
            items.append({"kind": "setting", "key": key, "label": spec["label"], "spec": spec,
                          "description": spec.get("description", "")})
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
    if "sleep" in name or "night" in name or "quiet" in name or "silent" in name: return "moon"
    if "eco" in name or "health" in name: return "leaf"
    if "temperature" in name: return "thermo"
    if "cool" in name or "mode" in name or "temp" in name: return "snow"
    return "wind"


class FunctionsView:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        app.dialog = self.window
        app.dialog_view = self
        localized_title(self.window,"Room AC Control · All functions")
        self.window.geometry("740x820")
        self.window.minsize(620, 700)
        paint(self.window, bg="BG")
        self.window.transient(app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, "Room AC Control · All functions", self.close, maximize=False)
        self.photo = unit_photo(self.window, 230)
        self.section = "settings"
        self.settings_changes = dict(app.dirty)
        self.card_widgets = []
        self.selected_function = None
        self.body = ttk.Frame(self.window, padding=(24, 4, 24, 20))
        self.body.pack(fill="both", expand=True)
        self.hero = paint(tk.Canvas(self.body, height=112, highlightthickness=0), bg="BG")
        self.hero.pack(fill="x", pady=(0, 12))
        self.airflow = AirflowAnimation(self.hero)
        self.hero.bind("<Configure>", lambda event: self.draw_hero())
        refresh_on_language(self.hero,self.draw_hero)
        refresh_on_theme(self.hero,self.draw_hero)
        self.navigation = paint(tk.Canvas(self.body, height=48, highlightthickness=0), bg="BG")
        self.navigation_hover = CanvasHover(self.navigation)
        self.navigation.pack(fill="x", pady=(0, 12))
        self.navigation.bind("<Configure>", lambda event: self.draw_navigation())
        self.navigation.bind("<Button-1>", self.navigate)
        refresh_on_language(self.navigation,self.draw_navigation)
        refresh_on_theme(self.navigation,self.draw_navigation)
        self.search = tk.StringVar()
        search_bar = paint(tk.Frame(self.body, highlightthickness=1), bg="CARD", highlightbackground="EDGE")
        search_bar.pack(fill="x", pady=(0, 12))
        glass = paint(tk.Canvas(search_bar, width=22, height=22, highlightthickness=0), bg="CARD")
        glass.pack(side="left", padx=(14, 8))
        draw_glass = lambda: (glass.delete("all"), icon(glass, "search", 11, 11, C.MUTED, scale=.8))
        draw_glass()
        refresh_on_theme(glass, draw_glass)
        self.search_entry = tk.Entry(search_bar, textvariable=self.search, relief="flat", font=font(11), bd=0)
        paint(self.search_entry, bg="CARD", fg="TEXT", insertbackground="TEXT", disabledbackground="CARD",
              disabledforeground="MUTED", selectbackground="SOFT", selectforeground="ON_SOFT")
        self.search_entry.pack(side="left", fill="x", expand=True, pady=12)
        self.placeholder = localized(paint(tk.Label(self.search_entry, text="Search functions", font=font(11), bd=0, cursor="xterm"),
                                           bg="CARD", fg="MUTED"))
        self.placeholder.bind("<Button-1>", lambda event: self.search_entry.focus_set())
        self.clear_search = localized(ttk.Button(search_bar, text="Clear", command=lambda: self.search.set(""),
                                                 style="Card.Ghost.TButton",cursor="hand2"))
        self.clear_search.pack(side="right", padx=(4, 6))
        shortcut = paint(tk.Label(search_bar, text="Ctrl+F", font=font(8, "bold"), padx=6, pady=2), bg="SURFACE", fg="TEXT")
        shortcut.pack(side="right")
        self.search_entry.bind("<FocusIn>", lambda event: (search_bar.configure(highlightbackground=C.BRAND), self.update_placeholder()))
        self.search_entry.bind("<FocusOut>", lambda event: (search_bar.configure(highlightbackground=C.EDGE), self.update_placeholder()))
        self.search_entry.bind("<Escape>", self.reset_search)
        self.window.bind("<Control-f>", self.focus_search)
        self.note = tk.StringVar()
        self.note_display=TranslatedVariable(self.window,self.note)
        ttk.Label(self.body, textvariable=self.note_display, style="Muted.TLabel", wraplength=680).pack(anchor="w", pady=(0, 14))
        area = ttk.Frame(self.body)
        area.pack(fill="both", expand=True)
        self.scroll = paint(tk.Canvas(area, highlightthickness=0), bg="BG")
        self.scrollable = False
        self.wheel_remainder = 0
        self.bar = ttk.Scrollbar(area, orient="vertical", command=self.scroll_to)
        self.bar.pack(side="right", fill="y")
        # Tk 8.6.15 also scrolls a ttk scrollbar from its class binding; route it once here.
        self.bar.bind("<MouseWheel>", self.wheel)
        self.scroll.pack(side="left", fill="both", expand=True)
        self.scroll.configure(yscrollcommand=self.bar.set)
        self.inner = ttk.Frame(self.scroll)
        self.inner_id = self.scroll.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self.update_scroll_region)
        self.scroll.bind("<Configure>", self.resize)
        # Toplevel bindtags cover cards, labels, frames and the empty canvas alike.
        self.window.bind("<MouseWheel>", self.wheel)
        self.footer = ttk.Frame(self.body)
        self.footer.pack(fill="x", pady=(16, 0))
        self.apply_button = ttk.Button(self.footer, style="Accent.TButton", command=self.apply)
        refresh_on_language(self.apply_button, self.update_apply)
        self.apply_button.pack(side="left", expand=True, fill="x", padx=(0, 10))
        localized(ttk.Button(self.footer, text="Close", command=self.close)).pack(side="right")
        localized(ttk.Button(self.footer, text="Diagnostics", style="Ghost.TButton", command=app.export_diagnostics)).pack(side="right", padx=(0, 6))
        localized(ttk.Button(self.footer, text="Appearance", style="Ghost.TButton", command=lambda:app.theme_menu(self.window))).pack(side="right",padx=(0,2))
        localized(ttk.Button(self.footer, text="Language", style="Ghost.TButton", command=lambda:app.language_menu(self.window))).pack(side="right",padx=(0,2))
        self.search.trace_add("write", lambda *args: self.update_placeholder())
        self.search.trace_add("write", lambda *args: self.render_section())
        self.render_section()
        self.window.after_idle(self.focus_search)

    def update_placeholder(self):
        empty = not self.search.get() and self.window.focus_get() is not self.search_entry
        if empty:
            self.placeholder.place(x=0, rely=.5, anchor="w")
        else:
            self.placeholder.place_forget()

    def draw_hero(self):
        c = self.hero
        c.delete("all")
        width = max(c.winfo_width(), 550)
        selected = self.app.selected
        c.create_text(2, 20, text=tr(c, "All functions"), anchor="w", fill=C.TEXT, font=font(21, "black"))
        c.create_text(2, 52, text=f"{selected['name']} · {selected['model']}", anchor="w", fill=C.MUTED, font=font(10))
        on = selected["power"] == "On"
        chips = ((tr(c, selected["power"]), C.OK_BG if on else C.SURFACE, C.OK_TEXT if on else C.TEXT, True),
                 (tr(c, mode_label(selected, self.settings_changes)) + " · " + translator(c).number(degrees(selected["target"])),
                  C.CARD, C.TEXT, False))
        x = 2
        for label, fill, ink, dot in chips:
            chip = measure(c, label, 9, "bold") + (34 if dot else 22)
            rounded(c, x, 74, x+chip, 100, 13, fill=fill, outline="" if dot else C.EDGE)
            if dot:
                c.create_oval(x+11, 83.5, x+18, 90.5, fill=ink, outline="")
            c.create_text(x+chip-11, 87, text=label, anchor="e", fill=ink, font=font(9, "bold"))
            x += chip + 8
        ac_art(c, width-112, 36, photo=self.photo)
        self.airflow.set_state(selected, width-112, 68, 180, 34)

    def draw_navigation(self):
        c = self.navigation
        c.delete("all")
        width = max(c.winfo_width(), 550)
        self.navigation_hover.reset()
        rounded(c, 0, 0, width, 48, 12, fill=C.RAISED, outline="")
        segment = (width-8)/3
        for index, (key, label) in enumerate(SECTIONS):
            x = 4+index*segment
            selected = key == self.section and not self.search.get().strip()
            fill = C.SEGMENT if selected else C.RAISED
            surface = rounded(c, x+2, 4, x+segment-2, 44, 8, fill=fill, outline="")
            self.navigation_hover.add((x, 0, x+segment, 48), surface, {"fill": fill}, {"fill": C.SEGMENT if selected else C.SURFACE})
            caption = tr(c, label)
            weight = "bold" if selected else "normal"
            left = x+segment/2-(measure(c, caption, 10, weight)+26)/2
            icon(c, SECTION_GLYPHS[key], left+9, 24, C.TEXT, scale=.7, bg=fill)
            c.create_text(left+26, 24, text=caption, anchor="w", fill=C.TEXT, font=font(10, weight))
        self.navigation_hover.update()

    def navigate(self, event):
        index = max(0, min(2, int(event.x / max(self.navigation.winfo_width(), 550) * 3)))
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
        self.update_scroll_region()
        for card in self.card_widgets:
            card.event_generate("<<RedrawCard>>")

    def update_scroll_region(self, event=None):
        height = max(1, self.scroll.winfo_height())
        content_height = self.inner.winfo_reqheight()
        self.scrollable = content_height > height
        self.scroll.configure(scrollregion=(0, 0, self.scroll.winfo_width(), max(height, content_height)))
        if self.scrollable:
            if not self.bar.winfo_manager():
                self.bar.pack(side="right", fill="y", before=self.scroll)
        else:
            self.scroll.yview_moveto(0)
            self.wheel_remainder = 0
            self.bar.pack_forget()

    def scroll_to(self, *args):
        if self.scrollable:
            self.scroll.yview(*args)

    def wheel(self, event):
        widget = event.widget
        if widget.winfo_class() in {"Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Scale", "TScale", "Text"}:
            return  # Editable fields keep their own wheel behavior.
        while widget not in {self.scroll, self.bar}:
            if widget is self.window or widget is None:
                return  # Header, search, footer and other windows are not this list.
            widget = widget.master
        if self.scrollable:
            self.wheel_remainder -= event.delta / 120
            steps = int(self.wheel_remainder)
            if steps:
                self.scroll.yview_scroll(steps, "units")
                self.wheel_remainder -= steps
        return "break"

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
                localized(ttk.Label(self.inner, text=title, style="Muted.TLabel", font=font(10, "bold"))).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(4, 10))
                row += 1
            self.visible_items.extend(items)
            for index, item in enumerate(items):
                card = self.card(item)
                card.grid(row=row+index//3, column=index%3, sticky="nsew", padx=(0, 10), pady=(0, 12))
            row += (len(items)+2)//3
        if not count:
            text = "No matching functions. Try another word or clear the search." if query else "No functions in this section are exposed by your AC."
            localized(ttk.Label(self.inner, text=text, style="Muted.TLabel", wraplength=520)).grid(row=0, column=0, columnspan=3, pady=40)
        self.update_apply()

    def setting_value(self, spec):
        key = spec["key"]
        spec = self.app.selected.get("controls", {}).get(key, spec)
        if key in self.settings_changes: return self.settings_changes[key]
        if key in self.app.pending_changes: return self.app.pending_changes[key]
        return spec["value"] if spec.get("reported") else None

    def refresh_status(self):
        # Redraw values in place; keep open menus, preset forms, scroll position and edits.
        self.draw_hero()
        for card in self.card_widgets:
            card.event_generate("<<RedrawCard>>")

    def card(self, item):
        card = tk.Canvas(self.inner, highlightthickness=0, width=200, height=105, cursor="hand2", takefocus=True)
        card.hover_style = CanvasHover(card)
        def draw(event=None):
            card.delete("all")
            card.configure(bg=C.BG)
            width = max(card.winfo_width(), 150)
            card.hover_style.reset()
            glyph=glyph_for(item["label"])
            heading=item["label"]
            active, pending = True, False
            if item["kind"] == "setting":
                spec = item["spec"]
                value = self.setting_value(spec)
                if spec["kind"] == "enum":
                    from .dashboard import equal
                    label = next((label for label, option in spec["options"].items() if equal(option, value)), "Unknown")
                else:
                    label = "Unknown" if value is None else translator(card).number(f"{float(value):g}")
                if spec["key"] == "tempSel" and value is not None: label += " °C"
                if spec["key"] == "machMode":
                    label = mode_label(self.app.selected,self.settings_changes)
                    glyph = mode_icon(label)
                elif spec["key"] in {"windDirectionVertical","windDirectionHorizontal"}:
                    glyph = airflow_icon(label)
                active = label not in NEUTRAL
                pending = spec["key"] in self.settings_changes
            else:
                heading = "Maintenance routine" if item.get("section", self.section) == "maintenance" else "Preset" if item.get("command") == "startProgram" or item["kind"] == "night" else "Function"
                label = item["label"]
            surface=control_card(card,1,1,width-2,heading,label,glyph,active=active,pending=pending,height=103)
            outline = C.BRAND if pending else C.EDGE
            card.hover_style.add((0,0,width,105),surface,{"fill":C.CARD,"outline":outline},{"fill":C.HOVER,"outline":C.BRAND})
            card.hover_style.update()
        def choose(event=None):
            if item["kind"] != "setting": self.configure_function(item)
            else: self.edit_setting(item["spec"], card)
        card.bind("<Configure>", draw)
        card.bind("<<RedrawCard>>", draw)
        refresh_on_language(card,draw)
        refresh_on_theme(card,draw)
        card.bind("<Button-1>", choose)
        card.bind("<Return>", choose)
        card.bind("<space>", choose)
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
        self.draw_hero()
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
                           else [{"label":label,"value":value,"glyph":glyph_for(spec["label"]),
                                  "description":spec.get("description", "")} for label,value in spec["options"].items()])
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
        localized_title(window,spec["label"])
        paint(window, bg="BG")
        window.transient(self.window)
        window.grab_set()
        def close_detail():
            window.destroy()
            self.window.grab_set()
        from .window_header import WindowHeader
        window.header = WindowHeader(window, spec["label"], close_detail, maximize=False)
        body = ttk.Frame(window, padding=22)
        body.pack(fill="both", expand=True)
        getter, initial = self.app.field(body, spec, self.setting_value(spec), use_reported=True,
                                         show_label=spec["key"] != "tempSel")
        hint = (f"Drag, scroll or use ↑ ↓ · {spec['min']:g}–{spec['max']:g}°C · Step {spec['step']:g}"
                if spec["key"] == "tempSel" else f"Range {spec['min']:g}–{spec['max']:g} · Step {spec['step']:g}")
        localized(ttk.Label(body, text=hint, style="Muted.TLabel")).pack(anchor="w", pady=12)
        def done():
            value = getter()
            if value is not None: self.change_setting(spec["key"], value)
            close_detail()
        localized(ttk.Button(body, text="Set value", style="Accent.TButton", command=done)).pack(fill="x")
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
        localized(ttk.Button(detail, text="‹ Back to cards", command=self.render_section)).pack(anchor="w", pady=(0, 18))
        localized(ttk.Label(detail, text=item["label"], style="Heading.TLabel")).pack(anchor="w", pady=(0, 6))
        description = "Cleaning / service routine" if maintenance else "Everyday comfort preset"
        localized(ttk.Label(detail, text=description, style="Muted.TLabel")).pack(anchor="w", pady=(0, 20))
        saved=self.app.memory.function_values(self.app.selected["id"],item["command"],item["form"]) if item["kind"]=="function" else {}
        fields = {spec["key"]: self.app.field(detail, spec, saved.get(spec["key"])) for spec in item.get("form", {}).get("parameters", [])}
        if item["kind"] == "night":
            localized(ttk.Label(detail,text=item["description"],style="Muted.TLabel")).pack(anchor="w",pady=14)
        if not fields:
            localized(ttk.Label(detail, text="This routine has no adjustable options.", style="Muted.TLabel")).pack(anchor="w", pady=14)
        text = "This routine may interrupt the current operation." if maintenance else "Starting this preset may turn the AC on and replace its settings."
        localized(ttk.Label(detail, text=text, wraplength=580, style="Muted.TLabel")).pack(anchor="w", pady=20)
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
        localized(ttk.Button(detail, text=button, style="Accent.TButton", command=run)).pack(fill="x")
        self.scroll.yview_moveto(0)
        self.update_apply()

    def update_apply(self):
        count = len(self.settings_changes)
        self.apply_button.configure(text=tr(self.apply_button, "Apply changes")+(f" ({count})" if count else ""),
                                    state="normal" if self.settings_changes and self.selected_function is None else "disabled")

    def apply(self):
        if not self.settings_changes or self.selected_function is not None: return
        changes = dict(self.settings_changes)
        self.close()
        self.app.action("configure", changes)

    def close(self):
        self.app.dialog = None
        self.app.dialog_view = None
        self.airflow.close()
        self.window.destroy()
