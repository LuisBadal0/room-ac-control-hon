"""Light or dark desktop dashboard with live-discovered appliance controls."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue

import math

from .controller import code, readable, mode_choices, mode_label
from .choice_widgets import ChoicePanel, SelectField
from .control_choices import mode_icon, airflow_choices, airflow_icon
from .theme import (C, THEMES, ASSETS, font, measure, paint, rounded, icon, ac_art, unit_photo, blend, accent,
                    resolve_theme, refresh_on_theme, broadcast_theme)
from .button_theme import configure_styles
from .canvas_hover import CanvasHover
from .worker import Worker, degrees
from .secure_state import SecureState
from .program_memory import ProgramMemory
from .airflow import AirflowAnimation
from pathlib import Path
from . import updates, __version__
from .device_picker import DevicePicker, PowerButton
from .diagnostics import diagnostics
from .inline_timers import InlineTimers, EndAtCard
from .temperature_wheel import TemperatureWheel
from .widgets import PillButton, Toast, fan_bars
from .i18n import Translator, LANGUAGES, tr, localized, TranslatedVariable, localized_title, broadcast_language, refresh_on_language
from .smooth import aa_arc, aa_line, aa_oval, pil_font, aa_text

# The dashboard canvas uses the mockup's 500 px grid and is scaled with the window.
WIDTH = 500
UNIT = (270, 0)          # picture width, top
FLOW = (76, 230, 30)     # airflow outlet y, spread, length
CHIP = (78, 104)         # status chip top and bottom, at the left
BANNER = (0, 74, WIDTH, 108)
READINGS_TOP, READINGS_HEIGHT = 115, 58
# The target-temperature dial: a 270° ring that opens at the bottom.
DIAL_TOP = 182
DIAL = (250, DIAL_TOP + 150, 120)  # centre x, centre y, radius
DIAL_START, DIAL_SWEEP = 135, 270
MODES_TOP, MODES_HEIGHT = 473, 60
TILE_TOP, TILE_HEIGHT = 542, 70
TIMER_TOP = 621
CANVAS_HEIGHT = TIMER_TOP + EndAtCard.HEIGHT + 1
AIR_COLORS = {"Good": "OK", "Medium": "WARN_TEXT", "Poor": "DANGER"}
ALERTS = {
    "error": ("alert", "DANGER_BG", "DANGER_TEXT", "AC error {code}", "Check the unit, or see troubleshooting in hOn."),
    "defrost": ("snow", "SOFT", "ON_SOFT", "Defrosting", "Heating pauses while the outdoor unit melts ice."),
    "filter": ("wrench", "WARN_BG", "WARN_TEXT", "Clean the air filter", "The AC reports that its filter needs cleaning."),
}
# What the dial says above the number, by mode.
VERBS = {"Cool": "Cooling to", "Heat": "Heating to", "Dry": "Drying at", "Fan": "Fan only", "Auto": "Holding at"}
FAN_LEVELS = {"Low": 1, "Medium": 2, "High": 3}
# The window opens at its minimum size and stays fixed; the layout is designed for it.
WINDOW_SIZE = (540, 920)
THEME_CHOICES = [
    {"label": "Follow Windows", "value": "system", "glyph": "monitor", "description": "Match the Windows app mode"},
    {"label": "Light mode", "value": "light", "glyph": "sun", "description": "Sand and white surfaces"},
    {"label": "Dark mode", "value": "dark", "glyph": "moon", "description": "Charcoal surfaces for low light"},
]


def equal(left, right):
    try:
        return float(left) == float(right)
    except (ValueError, TypeError):
        return str(left) == str(right)


class App:
    def __init__(self, root, demo=False, state=None, enable_tray=True, language=None, theme=None):
        self.root, self.demo = root, demo
        self.storage = state if state is not None else SecureState(persistent=not demo)
        self.i18n = root.i18n = Translator(self.storage.language() if language is None else language)
        self.theme_preference = self.storage.theme() if theme is None else (theme if theme in THEMES else "system")
        C.use(resolve_theme(self.theme_preference))
        self.theme_checks = 0
        self.memory = ProgramMemory(self.storage)
        self.preview_timers = {}
        self.preview_records = {}  # Fictional schedules for the offline preview.
        self.schedules_view = None
        self.updates_view = None
        self.update_job = None
        self.update_notice = None
        self.worker = Worker(memory=self.memory)
        self.tray = None
        self.closing = False
        if enable_tray and not demo:
            try:
                from .tray import SystemTray
                self.tray = SystemTray(self.i18n)
            except Exception as error:
                diagnostics.record("tray_start_failed", error)
        self.devices, self.selected = [], None
        self.busy, self.dirty = False, {}
        self.pending_changes = {}
        self.hits = []
        self.dialog = None
        self.dialog_view = None
        self.auto_job = None
        self.auto_inflight = False
        self.auto_pending = False
        self.auto_failures = 0
        self.refresh_epoch = 0
        self.unit_image = unit_photo(root, UNIT[0])
        self.settings_panel = None
        self.dial_drag = False
        root.iconbitmap(str(ASSETS / "app.ico"))
        self.app_icon = tk.PhotoImage(master=root, file=str(ASSETS / "app-icon.png"))
        root.iconphoto(True, self.app_icon)
        localized_title(root,"Room AC Control for hOn" + (" · Design preview" if demo else ""))
        root.geometry("{}x{}".format(*WINDOW_SIZE))
        root.resizable(False, False)
        paint(root, bg="BG")
        configure_styles(root)
        from .window_header import WindowHeader, HeaderPillButton
        self.header = WindowHeader(root, "Room AC Control", self.close, self.minimize_window, maximize=False, size=WINDOW_SIZE)
        # Appearance, language, updates and sign-out live in one Settings panel;
        # a dot marks a signed update waiting to install.
        self.settings_button = HeaderPillButton(self.header.frame,"gear","Settings",self.open_settings)
        self.settings_button.pack(side="right",padx=(0,6))
        location = None if demo else updates.install_location()
        self.updater = updates.Updater(__version__, location, enabled=self.storage.auto_update(), demo=demo)
        self.updater.listen(self.updates_changed)
        if location is not None:
            try:self.update_notice = updates.finish(location, __version__)
            except OSError as error:diagnostics.record("update_failed", error)
        self.content = ttk.Frame(root)
        self.content.pack(fill="both",expand=True)
        self.body = ttk.Frame(self.content, padding=(20,0,20,20))
        self.body.pack(fill="both",expand=True)
        from .login_view import LoginView
        self.login_view = LoginView(self)
        self.login_frame = self.login_view.frame
        self.login_frame.pack(fill="x",pady=(5,0))
        self.panel=ttk.Frame(self.body)
        top=ttk.Frame(self.panel)
        top.pack(fill="x",pady=(0,4))
        self.power_button=PowerButton(top,self.toggle_power)
        self.power_button.pack(side="right",padx=(8,0))
        self.device_picker=DevicePicker(top,self.select_device)
        self.device_picker.pack(side="left",fill="x",expand=True)
        self.canvas=paint(tk.Canvas(self.panel,highlightthickness=0,height=CANVAS_HEIGHT),bg="BG")
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>",lambda e:self.draw())
        refresh_on_language(self.canvas,self.draw)
        refresh_on_theme(self.canvas,self.draw)
        self.canvas_hover = CanvasHover(self.canvas)
        self.airflow = AirflowAnimation(self.canvas)
        self.inline_timers = InlineTimers(self)
        self.canvas.bind("<Button-1>",self.click)
        self.canvas.bind("<B1-Motion>",self.drag_temperature)
        self.canvas.bind("<ButtonRelease-1>",self.release_dial)
        self.canvas.bind("<MouseWheel>",self.wheel_temperature)
        for key,direction in (("<Left>",-1),("<Right>",1),("<Down>",-1),("<Up>",1)):
            self.canvas.bind(key,lambda e,direction=direction:self.step_temp(direction) if not self.busy and self.selected else None)
        # Main selectors retain Tk variables for menu and keyboard support.
        self.mode,self.temp,self.fan=tk.StringVar(),tk.StringVar(),tk.StringVar()
        # The action row: All functions and Refresh on the left; Discard and Apply, or
        # "In sync with the AC", on the right.
        controls=ttk.Frame(self.panel)
        controls.pack(side="bottom",fill="x")
        self.all_button=PillButton(controls,"All functions",self.open_functions,glyph="grid")
        self.all_button.pack(side="left")
        self.refresh_button=PillButton(controls,"",self.refresh,glyph="refresh",width=48)
        self.refresh_button.pack(side="left",padx=(8,0))
        self.apply_button=PillButton(controls,"Apply",lambda:self.action("apply"),kind="accent",size=-14,tone=self.dial_accent)
        self.discard_button=PillButton(controls,"Discard",self.discard,kind="ghost")
        self.sync_label=tk.Canvas(controls,height=48,highlightthickness=0)
        self.sync_label.bind("<Configure>",lambda event:self.draw_sync())
        refresh_on_theme(self.sync_label,self.draw_sync)
        refresh_on_language(self.sync_label,self.draw_sync)
        self.update_apply_label()
        # The connection line is shown under the room name.
        self.connection=tk.StringVar()
        self.connection.trace_add("write",lambda *args:self.paint_connection())
        self.status=tk.StringVar(value="Sign in to connect to your air conditioner.")
        self.status_display=TranslatedVariable(root,self.status)
        self.status_label=tk.Label(self.body,textvariable=self.status_display,font=font(9),anchor="w",justify="left",
                                   padx=12,pady=6,wraplength=480,bd=0)
        paint(self.status_label,bg="SOFT",fg="ON_SOFT")
        self.status_label.pack(fill="x",pady=(8,0))
        self.status_label.bind("<Configure>",lambda event:self.status_label.configure(wraplength=max(1,event.width-24)))
        # Signed in, messages appear briefly above the action row instead.
        self.toast=Toast(root)
        self.status.trace_add("write",lambda *args:self.status_changed())
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.root.report_callback_exception = self.callback_failed
        self.root.bind("<Unmap>",self.on_minimize,add="+")
        self.poll_job = root.after(100,self.poll)
        if not demo:root.after(200,self.auto_sign_in)
        if self.update_notice:self.status.set(self.update_notice)
        if self.updater.supported:
            self.update_job = root.after(updates.FIRST_CHECK_MS, self.auto_check_updates)

    def language_menu(self, parent=None):
        parent = parent or self.root
        options = [{"label":"System language","value":"system","glyph":"globe","description":"Follow Windows language"}]
        options.extend({"label":label,"value":value,"glyph":"globe"} for value,label in LANGUAGES.items())
        self.language_panel = ChoicePanel(parent,"Language",options,self.i18n.preference,self.set_language)

    def set_language(self, preference):
        self.i18n.set_language(preference)
        broadcast_language(self.root)
        if self.tray:
            try:self.tray.refresh_language()
            except Exception as error:diagnostics.record("tray_language_failed",error)
        try:self.storage.save_language(self.i18n.preference)
        except OSError:self.status.set("Language changed for this session, but the preference could not be saved.")

    def theme_menu(self, parent=None):
        parent = parent or self.root
        self.theme_panel = ChoicePanel(parent,"Appearance",THEME_CHOICES,self.theme_preference,self.set_theme)

    def set_theme(self, preference):
        self.theme_preference = preference if preference in THEMES else "system"
        self.apply_theme()
        try:self.storage.save_theme(self.theme_preference)
        except OSError:self.status.set("Appearance changed for this session, but the preference could not be saved.")

    def apply_theme(self):
        """Repaint every open window in place; edits, drafts and dialogs are kept."""
        mode = resolve_theme(self.theme_preference)
        if mode == C.mode:
            return False
        C.use(mode)
        configure_styles(self.root)
        broadcast_theme(self.root)
        return True

    def poll(self):
        if self.closing:return
        try:
            while True:
                callback,value,error,operation=self.worker.results.get_nowait()
                if operation != "auto-refresh":
                    self.set_busy(False)
                if error:
                    if operation in {"auto-refresh", "login", "timer", "schedule", "schedule-list"}:
                        callback(error)
                    else:
                        self.status.set(error)
                        messagebox.showerror("Room AC Control",tr(self.root,error),parent=self.root)
                else:
                    callback(value)
        except queue.Empty:
            pass
        try:
            while True:
                device_id = self.worker.changes.get_nowait()
                if self.selected and self.selected["id"] == device_id:
                    self.auto_pending = True
                    if not self.auto_inflight:
                        self.schedule_auto(750)
        except queue.Empty:
            pass
        if self.tray:
            try:
                while True:
                    event=self.tray.events.get_nowait()
                    if event=="ready":
                        self.tray.ready=True
                        if self.root.state()=="iconic":self.minimize_to_tray()
                    elif event=="restore":self.restore_window()
                    elif event=="exit":
                        self.close()
                        return
            except queue.Empty:
                pass
        self.updater.poll()
        # Follow Windows: notice an app-mode switch within about two seconds.
        self.theme_checks += 1
        if self.theme_checks >= 20:
            self.theme_checks = 0
            if self.theme_preference == "system":
                self.apply_theme()
        self.poll_job = self.root.after(100,self.poll)

    def update_apply_label(self):
        """Discard and Apply (with a count) while edits wait; otherwise "In sync with the AC"."""
        count = len(self.dirty)
        self.apply_button.set_badge(count if count else None)
        if count:
            self.sync_label.pack_forget()
            if not self.apply_button.winfo_manager():
                self.apply_button.pack(side="right")
                self.discard_button.pack(side="right",padx=(0,4))
        else:
            self.apply_button.pack_forget()
            self.discard_button.pack_forget()
            if not self.sync_label.winfo_manager():
                self.sync_label.pack(side="right",fill="x",expand=True)

    def draw_sync(self):
        c=self.sync_label
        c.delete("all")
        c.configure(bg=C.BG)
        width=max(c.winfo_width(),1)
        label=tr(c,"In sync with the AC")
        right=width-4
        aa_text(c, right,24,text=label,anchor="e",fill=C.MUTED,font=font(-12,"semibold"))
        icon(c,"check",right-measure(c,label,-12,"semibold")-12,24,C.MUTED,scale=.6,bg=C.BG)

    QUIET = {"Changes ready. Apply them, or use the power button to turn on.", "No pending changes.",
             "Connected. Select changes, then apply.", "Design preview · No AC commands are sent.",
             "Status retrieved from the cloud service.", "Refreshing reported AC status…"}

    def status_changed(self):
        """Show a dashboard message as a toast; routine confirmations stay quiet."""
        message=self.status.get()
        if not self.panel.winfo_ismapped() or not message or message in self.QUIET:
            return
        bottom=self.content.winfo_y()+self.body.winfo_y()+self.panel.winfo_y()+self.panel.winfo_height()-58
        self.toast.show(tr(self.root,message),bottom)

    def paint_connection(self):
        text = self.connection.get()
        self.device_picker.set_status(text, text.startswith("Connected"))

    def open_settings(self):
        if self.settings_panel:
            self.settings_panel.close()  # The button toggles the dropdown.
            return
        from .settings_panel import SettingsPanel
        self.settings_button.set_pressed(True)
        SettingsPanel(self)

    def discard(self):
        """Drop staged edits and show the reported (or awaiting) values again."""
        if self.busy or not self.selected or not self.dirty:return
        self.dirty={}
        self.show_device(self.selected)
        self.status.set("Changes discarded.")

    def set_busy(self,value):
        self.busy=value
        state="disabled" if value else "normal"
        for widget in (self.email,self.password,self.login_button):
            widget.configure(state=state)
        available=self.selected is not None and not value
        for widget in (self.refresh_button,self.all_button,self.discard_button):
            widget.set_enabled(available)
        self.apply_button.set_enabled(available and bool(self.dirty))
        self.update_apply_label()
        self.device_picker.set_enabled(available)
        self.power_button.set_state(self.selected is not None and self.selected["power"]=="On", available,
                                    self.mode.get() if self.selected else None)
        self.draw()

    def connect(self):
        if self.busy:return
        email,password=self.email.get().strip(),self.password.get()
        if not email or not password:
            self.status.set("Enter your cloud account email and password.");return
        self.password.delete(0,"end")
        self.sign_in(email,password)

    def auto_sign_in(self):
        if self.closing or self.busy or self.selected:return
        login=self.storage.credentials()
        if login:
            # Existing saved accounts retain their previously chosen auto sign-in.
            self.remember_account.set(True)
            self.email.delete(0,"end")
            self.email.insert(0,login[0])
            self.sign_in(*login,automatic=True)
        elif self.storage.load_error:
            self.status.set("Saved sign-in could not be decrypted. Sign in again to replace it.")

    def sign_in(self,email,password,automatic=False):
        if self.closing or self.busy:return
        self.set_busy(True)
        self.login_view.set_loading(True, automatic)
        self.status.set("Signing in with your saved account…" if automatic else "Connecting to the cloud service…")
        def done(devices):
            persistence_error=False
            try:
                if self.remember_account.get():self.storage.save_credentials(email,password)
                else:self.storage.forget_credentials()
            except OSError as error:
                diagnostics.record("credential_save_failed", error)
                persistence_error=True
            self.connected(devices)
            if persistence_error:self.status.set("Connected, but Windows could not save the encrypted sign-in.")
        def failed(error):
            self.login_view.set_loading(False)
            self.set_busy(False)
            self.status.set(("Automatic sign-in failed. " if automatic else "")+error)
        self.worker.submit(self.worker.controller.connect(email,password),done,"login",on_error=failed)

    def connected(self,devices):
        self.login_view.set_loading(False)
        if self.demo and not self.memory.account:
            self.memory.use_account("preview@example.test")
        self.reset_auto()
        self.devices=devices
        self.login_frame.pack_forget()
        self.panel.pack(fill="both",expand=True)
        self.status_label.pack_forget()
        self.device_picker.set_devices(devices)
        index=0
        self.device_picker.current(index)
        self.show_device(devices[index])
        self.status.set("Design preview · No AC commands are sent." if self.demo else "Connected. Select changes, then apply.")
        if self.update_notice:
            self.status.set(self.update_notice)
            self.update_notice = None
        self.schedule_auto()

    def show_device(self,device,preserve_edits=False):
        pending = dict(self.dirty) if preserve_edits else {}
        self.selected=device
        self.devices[self.device_picker.current()]=device
        self.dirty=pending
        self.pending_changes=dict(device.get("pending_changes",{}))
        displayed={**self.pending_changes,**pending}
        self.mode.set(mode_label(device,displayed))
        fan_value=displayed.get("windSpeed",device.get("controls",{}).get("windSpeed",{}).get("value"))
        self.fan.set(next((label for label,value in device["fans"].items() if equal(value,fan_value)),device["fan"]))
        self.temp.set(displayed.get("tempSel",str(device["target"]) if device["target"] is not None else ""))
        state=device.get("connection","Unknown")
        label="Connected" if state=="CONNECTED" else ("Disconnected" if state=="DISCONNECTED" else "Connection unknown")
        self.connection.set(f"{label} · {device['fetched']}" + (" · Auto" if not self.demo else ""))
        if device.get("confirmation_expired"):
            self.status.set("The cloud has not confirmed the changes. Showing reported status; check hOn before retrying.")
        self.set_busy(self.busy if preserve_edits else False)
        if self.dialog and self.dialog.winfo_exists():
            self.dialog_view.refresh_status()

    def select_device(self,event=None):
        if not self.busy:
            self.reset_auto()
            self.selected=self.devices[self.device_picker.current()]
            self.dirty={}
            self.pending_changes={}
            self.refresh()

    def staged(self,key,value):
        if self.busy:return
        spec=self.selected.get("controls",{}).get(key)
        if spec and spec.get("reported") and equal(value,self.pending_changes.get(key,spec["value"])):
            self.dirty.pop(key,None)
        else:self.dirty[key]=str(value)
        if key in {"machMode","silentSleepStatus"}:self.mode.set(mode_label(self.selected,{**self.pending_changes,**self.dirty}))
        if key=="windSpeed":self.fan.set(next((label for label,v in self.selected["fans"].items() if equal(v,value)),"Other"))
        if key=="tempSel":self.temp.set(str(value))
        self.status.set("Changes ready. Apply them, or use the power button to turn on." if self.dirty else "No pending changes.")
        self.set_busy(False)

    def current(self,key):
        if key in self.dirty:return self.dirty[key]
        if key in self.pending_changes:return self.pending_changes[key]
        spec=self.selected.get("controls",{}).get(key)
        return spec.get("value") if spec and spec.get("reported") else None

    def toggle_power(self):
        if self.busy or not self.selected:return
        self.action("off" if self.selected["power"]=="On" else "on")

    def base_mode(self):
        """The displayed mode without its Night (Sleep) suffix, such as "Cool"."""
        return self.mode.get().replace(" Night", "")

    def dial_accent(self):
        if not self.selected:
            return C.BRAND
        return accent("off") if self.selected["power"] != "On" else accent(self.base_mode())

    def soft(self, color, base=None):
        """The mockup's accent tint: the colour at about 14% over a surface."""
        return blend(color, base or C.CARD, .14 if C.mode == "dark" else .10)

    def mode_options(self):
        """Standard modes for the mode bar; Night variants are Sleep on the Sleep tile."""
        return [option for option in mode_choices(self.selected) if not option["label"].endswith(" Night")]

    def draw(self):
        if not self.selected:return
        c=self.canvas
        c.delete("all")
        c.configure(bg=C.BG)
        self.hits=[]
        width=max(c.winfo_width(),480)
        s=width/WIDTH
        self.canvas_hover.reset(s,enabled=not self.busy)
        tone=self.dial_accent()
        text=lambda x,y,t,size=-13,color=None,anchor="w",weight="normal",translate=True:aa_text(c, 
            x,y,text=tr(c,t) if translate else t,fill=color or C.TEXT,anchor=anchor,font=font(size,weight))
        hit=lambda box,fn:self.hits.append((box,fn))
        self.draw_glow(c,tone)
        # The unit, its live airflow and the status chip; an alert banner covers the airflow.
        c.create_image(WIDTH/2,UNIT[1],image=self.unit_image,anchor="n")
        if not self.draw_alert(c,text):
            self.draw_chip(c,text,tone)
        self.draw_readings(c,text)
        self.draw_dial(c,text,hit,tone)
        self.draw_modes(c,text,hit)
        self.draw_tiles(c,text,hit)
        self.inline_timers.refresh(self.selected, self.busy)
        timer_row = c.create_window(0, TIMER_TOP, window=self.inline_timers, anchor="nw", width=WIDTH, height=EndAtCard.HEIGHT)
        c.itemconfigure(timer_row,tags="inline-timers")
        if s!=1:c.scale("all",0,0,s,s)
        # Canvas scaling also changes embedded window dimensions. Apply its final
        # width once, while preserving the native wheels' full height.
        c.itemconfigure(timer_row,width=round(WIDTH*s),height=EndAtCard.HEIGHT)
        self.canvas.configure(height=int(CANVAS_HEIGHT*s))
        flowing=self.selected if not c.find_withtag("alert") else None
        self.airflow.set_state(flowing,WIDTH/2,FLOW[0],FLOW[1],FLOW[2],s)
        self.canvas_hover.update()
        self.apply_button.draw()
        if self.busy:
            self.hits=[]

    def draw_glow(self,c,tone):
        """A soft accent glow around the dial, like the mockup's blurred shadow."""
        if self.selected["power"]!="On":return
        key=(tone,C.BG)
        if getattr(self,"glow_key",None)!=key:
            from PIL import Image, ImageDraw, ImageTk
            size,inner=420,95
            strength=.22 if C.mode=="dark" else .19
            mask=Image.new("L",(size,size),0)
            draw=ImageDraw.Draw(mask)
            centre=size/2
            for d in range(int(centre),inner-1,-1):
                a=strength*(1 if d<inner+18 else math.exp(-((d-inner-18)/45)**2))
                draw.ellipse((centre-d,centre-d,centre+d,centre+d),fill=round(255*a))
            draw.ellipse((centre-inner,centre-inner,centre+inner,centre+inner),fill=0)
            image=Image.composite(Image.new("RGB",(size,size),tone),Image.new("RGB",(size,size),C.BG),mask)
            self.glow_image=ImageTk.PhotoImage(image,master=c)
            self.glow_key=key
        c.create_image(DIAL[0],DIAL[1],image=self.glow_image)

    def draw_chip(self,c,text,tone):
        if self.pending_changes and not self.dirty:label="Awaiting confirmation"
        elif self.selected["power"]=="On":label=tr(c,self.base_mode())+" · "+tr(c,"running")
        else:label="Standby"
        label=tr(c,label)
        on=self.selected["power"]=="On"
        fill,ink=(self.soft(tone,C.BG),tone) if on else (C.CARD,C.MUTED)
        # The chip sits beside the unit, so a long label drops the mode name.
        if measure(c,label,-11,"bold")+36>112 and self.selected["power"]=="On" and not self.pending_changes:
            label=tr(c,"running").capitalize()
        width=measure(c,label,-11,"bold")+36
        rounded(c,0,CHIP[0],width,CHIP[1],13,fill=fill,outline="")
        middle=(CHIP[0]+CHIP[1])/2
        aa_oval(c, 10,middle-3,16,middle+3,fill=ink,outline="")
        text(22,middle,label,-11,ink,weight="bold",translate=False)

    def draw_readings(self,c,text):
        """Room, outside, humidity and air quality, as one row of chips."""
        sensors=self.selected.get("sensors",{})
        number=lambda value,places:self.i18n.number(f"{float(value):.{places}f}")+"°"
        try:room=number(self.selected["room"],1)
        except (TypeError,ValueError):room="—"
        outside=number(sensors["outdoor"],0) if "outdoor" in sensors else "—"
        humidity=f"{sensors['humidity']:.0f}%" if "humidity" in sensors else "—"
        quality=sensors.get("air")
        chips=[("Room",room,None),("Outside",outside,None),("Humidity",humidity,None),
               ("Air quality",tr(c,quality) if quality else "—",getattr(C,AIR_COLORS[quality]) if quality else None)]
        gap=8
        width=(WIDTH-gap*(len(chips)-1))/len(chips)
        top=READINGS_TOP
        for index,(label,value,dot) in enumerate(chips):
            x=index*(width+gap)
            items=[rounded(c,x,top,x+width,top+READINGS_HEIGHT,14,fill=C.CARD,outline="")]
            caption=tr(c,label)
            while measure(c,caption,-11,"semibold")>width-24 and len(caption)>3:caption=caption[:-2]+"…"
            items.append(text(x+12,top+19,caption,-11,C.MUTED,weight="semibold",translate=False))
            value_x=x+12
            if dot:
                items.append(aa_oval(c, x+12,top+36,x+20,top+44,fill=dot,outline=""))
                value_x+=14
            items.append(text(value_x,top+40,value,-17,weight="bold",translate=False))
            for item in items:c.addtag_withtag("reading",item)

    def draw_dial(self,c,text,hit,tone):
        """A 270° ring: drag along it, click it, scroll on it or use −/+."""
        cx,cy,r=DIAL
        top=DIAL_TOP
        values=[float(v) for v in self.selected.get("temperatures",[])]
        try:current=float(self.temp.get())
        except ValueError:current=None
        low,high=(min(values),max(values)) if values else (16,32)
        ratio=0 if current is None or high==low else max(0,min(1,(current-low)/(high-low)))
        point=lambda angle,radius:(cx+radius*math.cos(math.radians(angle)),cy+radius*math.sin(math.radians(angle)))
        for index in range(17):
            angle=DIAL_START+DIAL_SWEEP*index/16
            aa_line(c, *point(angle,135 if index%4==0 else 139),*point(angle,145),fill=C.FAINT,width=2,capstyle="round")
        box=(cx-r,cy-r,cx+r,cy+r)
        aa_arc(c, *box,start=-45,extent=270,style="arc",outline=C.TRACK,width=14)
        cap=lambda angle,color:aa_oval(c, point(angle,r)[0]-7,point(angle,r)[1]-7,point(angle,r)[0]+7,point(angle,r)[1]+7,fill=color,outline="")
        cap(DIAL_START+DIAL_SWEEP,C.TRACK)
        cap(DIAL_START,tone if values and current is not None else C.TRACK)
        if values and current is not None:
            if ratio>0:aa_arc(c, *box,start=225,extent=-DIAL_SWEEP*ratio,style="arc",outline=tone,width=14)
            tx,ty=point(DIAL_START+DIAL_SWEEP*ratio,r)
            halo=blend(tone,C.BG,.28 if self.dial_drag else .14)
            aa_oval(c, tx-22,ty-22,tx+22,ty+22,fill=halo,outline="",tags="dial-halo")
            aa_oval(c, tx-14,ty-14,tx+14,ty+14,fill=C.BG,outline=tone,width=4,tags="dial-thumb")
            aa_oval(c, tx-4,ty-4,tx+4,ty+4,fill=tone,outline="")
            self.canvas_hover.add((tx-24,ty-24,tx+24,ty+24),c.find_withtag("dial-halo")[0],{"fill":halo},
                                  {"fill":blend(tone,C.BG,.28)})
        text(cx-80,top+262,self.i18n.number(f"{low:g}°"),-12,C.MUTED,"center","semibold",translate=False)
        text(cx+80,top+262,self.i18n.number(f"{high:g}°"),-12,C.MUTED,"center","semibold",translate=False)
        # Centre: what the AC is doing above the target. The digits are centred on the
        # ring by their drawn outline, with °C hanging off their top right.
        verb="Off" if self.selected["power"]!="On" else VERBS.get(self.base_mode(),"Target temperature")
        value="—" if current is None else self.i18n.number(f"{current:g}")
        size=96
        face,unit_face=pil_font(c,font(-size,"light")),pil_font(c,font(-26,"normal"))
        middle=cy+6
        if face is not None and unit_face is not None:
            # Whole degrees keep the mockup's 96 px; wider values such as 25,5 shrink to stay in the ring.
            unit_width=unit_face.getlength("°C")
            room=2*(r-24)
            left,top_edge,right,bottom=face.getbbox(value)
            while size>56 and (right-left)+6+unit_width>room:
                size-=4
                face=pil_font(c,font(-size,"light"))
                left,top_edge,right,bottom=face.getbbox(value)
            x,y=cx-(left+right)/2,middle-(top_edge+bottom)/2
            # Keep °C inside the ring: shift the pair left only as far as needed.
            x-=max(0,x+right+6+unit_width-(cx+room/2))
            number=text(x,y,value,-size,anchor="nw",weight="light",translate=False)
            unit_top=unit_face.getbbox("°C")[1]
            unit=text(x+right+6,y+top_edge-unit_top,"°C",-26,C.MUTED,"nw",translate=False)
            digits_top=y+top_edge
        else:
            number=text(cx,middle,value,-96,anchor="center",weight="light",translate=False)
            box=c.bbox(number)
            unit=text(box[2]+4,box[1]+14,"°C",-26,C.MUTED,"nw",translate=False)
            digits_top=box[1]+14
        c.itemconfigure(number,tags="target-temperature")
        c.itemconfigure(unit,tags="temperature-unit")
        text(cx,digits_top-26,tr(c,verb).upper(),-12,tone,"center","black",translate=False)
        # −/+ beside the ring's open end.
        for x,direction in ((48,-1),(WIDTH-48,1)):
            y=top+222
            step=aa_oval(c, x-26,y-26,x+26,y+26,fill=C.CARD,outline="")
            mark=C.TEXT if values else C.FAINT
            aa_line(c, x-8,y,x+8,y,fill=mark,width=2.4,capstyle="round")
            if direction>0:aa_line(c, x,y-8,x,y+8,fill=mark,width=2.4,capstyle="round")
            if values:
                self.canvas_hover.add((x-26,y-26,x+26,y+26),step,{"fill":C.CARD},{"fill":C.HOVER})
                hit((x-26,y-26,x+26,y+26),lambda direction=direction:self.step_temp(direction))
        # Eco sits in the ring's opening.
        eco=self.selected.get("controls",{}).get("ecoMode")
        if eco:
            active=code(self.current("ecoMode"))=="1"
            label=tr(c,"Eco")
            width=measure(c,label,-12,"bold")+44
            x1,x2,y1,y2=cx-width/2,cx+width/2,top+248,top+280
            fill=self.soft(tone,C.BG) if active else C.BG
            ink=tone if active else C.MUTED
            chip=rounded(c,x1,y1,x2,y2,16,fill=fill,outline=tone if active else C.TRACK,width=1.2)
            icon(c,"leaf",x1+18,(y1+y2)/2,ink,scale=.55,bg=fill)
            text(x1+30,(y1+y2)/2,label,-12,ink,weight="bold",translate=False)
            self.canvas_hover.add((x1,y1,x2,y2),chip,{"outline":tone if active else C.TRACK},{"outline":tone})
            hit((x1,y1,x2,y2),lambda:self.staged("ecoMode","0" if active else "1"))

    def draw_modes(self,c,text,hit):
        """One button per standard mode; the selected one takes its own accent."""
        options=self.mode_options()
        top,bottom=MODES_TOP,MODES_TOP+MODES_HEIGHT
        rounded(c,0,top,WIDTH,bottom,18,fill=C.CARD,outline="")
        if not options:
            text(WIDTH/2,(top+bottom)/2,"Mode · Unavailable",-13,C.MUTED,"center")
            return
        gap=4
        width=(WIDTH-8-gap*(len(options)-1))/len(options)
        selected=self.base_mode()
        for index,option in enumerate(options):
            x=4+index*(width+gap)
            label=option["label"]
            on=label==selected
            color=accent(label)
            fill=self.soft(color) if on else C.CARD
            segment=rounded(c,x,top+4,x+width,bottom-4,14,fill=fill,outline="")
            if not on:
                self.canvas_hover.add((x,top+4,x+width,bottom-4),segment,{"fill":C.CARD},{"fill":C.HOVER})
            ink=color if on else C.MUTED
            icon(c,mode_icon(label),x+width/2,top+21,ink,scale=.72,bg=fill)
            caption=tr(c,label)
            size=-12 if measure(c,caption,-12,"bold")<=width-6 else -10
            text(x+width/2,top+42,caption,size,ink,"center","bold",translate=False)
            hit((x,top,x+width,bottom),lambda option=option:self.pick_mode(option))

    def pick_mode(self,option):
        for name,value in self.memory.mode_values(self.selected,dict(option["value"])).items():
            self.staged(name,value)

    def airflow_spec(self):
        controls=self.selected.get("controls",{})
        return controls.get("windDirectionVertical") or controls.get("windDirectionHorizontal")

    def airflow_value(self):
        """The current airflow option's label, such as Swing or Position 2."""
        spec=self.airflow_spec()
        if not spec:return "Unavailable"
        value=self.current(spec["key"])
        if value is None:return "Unknown"
        return next((label for label,option in spec["options"].items() if equal(option,value)),"Unknown")

    def draw_tiles(self,c,text,hit):
        controls=self.selected.get("controls",{})
        fan=self.fan.get() if "windSpeed" in controls else "Unavailable"
        tiles=[("Fan speed",fan,"bars",self.cycle_fan),
               ("Airflow",self.airflow_value(),"swing",self.cycle_airflow),
               ("Sleep",self.toggle_label("silentSleepStatus"),"moon",self.toggle_sleep)]
        gap=8
        width=(WIDTH-gap*2)/3
        top,bottom=TILE_TOP,TILE_TOP+TILE_HEIGHT
        tone=self.dial_accent()
        for index,(label,value,glyph,command) in enumerate(tiles):
            x=index*(width+gap)
            card=rounded(c,x,top,x+width,bottom,16,fill=C.CARD,outline="")
            text(x+14,top+19,label,-11,C.MUTED,weight="semibold")
            if glyph=="bars":
                fan_bars(c,x+width-14-18,top+26,FAN_LEVELS.get(value,0) if value!="Auto" else 0,tone,C.CARD)
            else:
                icon(c,glyph,x+width-21,top+19,C.MUTED,scale=.5,bg=C.CARD)
            text(x+14,top+49,value,-16,C.TEXT if value not in {"Unavailable","Unknown"} else C.MUTED,weight="bold")
            if value!="Unavailable":
                self.canvas_hover.add((x,top,x+width,bottom),card,{"fill":C.CARD},{"fill":C.HOVER})
                hit((x,top,x+width,bottom),command)

    def cycle(self,key,options):
        """Step to the next option, wrapping around, as the mockup's tiles do."""
        values=list(options.values())
        if not values:return
        current=self.current(key)
        index=next((i for i,value in enumerate(values) if equal(value,current)),-1)
        self.staged(key,values[(index+1)%len(values)])

    def cycle_fan(self):
        spec=self.selected.get("controls",{}).get("windSpeed")
        if spec:self.cycle("windSpeed",self.selected.get("fans") or spec["options"])

    def cycle_airflow(self):
        spec=self.airflow_spec()
        if spec:self.cycle(spec["key"],spec["options"])

    def toggle_sleep(self):
        if "silentSleepStatus" not in self.selected.get("controls",{}):return
        value="0" if code(self.current("silentSleepStatus"))=="1" else "1"
        patch={"silentSleepStatus":value}
        if code(self.current("machMode")) in {"1","4"}:
            patch["machMode"]=code(self.current("machMode"))
            patch=self.memory.mode_values(self.selected,patch)
        for name,new_value in patch.items():self.staged(name,new_value)

    def draw_alert(self,c,text):
        """A banner for an error, defrosting or filter cleaning; it clears with the condition."""
        alerts=[alert for alert in self.selected.get("alerts",[]) if alert.get("kind") in ALERTS]
        if not alerts:return False
        alert=alerts[0]
        glyph,surface,ink,title,detail=ALERTS[alert["kind"]]
        fill,color=getattr(C,surface),getattr(C,ink)
        x1,y1,x2,y2=BANNER
        items=[rounded(c,x1,y1,x2,y2,12,fill=fill,outline="")]
        icon(c,glyph,20,(y1+y2)/2,color,scale=.62,bg=fill,tags=("alert",))
        items.append(text(38,y1+10,title.format(code=alert.get("code","")),-12,color,weight="bold"))
        items.append(text(38,y1+24,detail,-11,color))
        if len(alerts)>1:
            items.append(text(x2-12,(y1+y2)/2,f"+{len(alerts)-1}",-12,color,"e","bold",translate=False))
        for item in items:c.addtag_withtag("alert",item)
        return True

    def scale(self):
        return max(self.canvas.winfo_width(),480)/WIDTH

    def click(self,event):
        if self.busy:return
        self.canvas.focus_set()
        s=self.scale()
        x,y=event.x/s,event.y/s
        for (x1,y1,x2,y2),fn in self.hits:
            if x1<=x<=x2 and y1<=y<=y2:
                fn()
                return
        if self.dial_angle(x,y,strict=True) is not None:
            self.dial_drag=True
            self.dial_from_event(event)

    def release_dial(self,event=None):
        if self.dial_drag:
            self.dial_drag=False
            self.draw()

    def dial_angle(self,x,y,strict=False):
        """The ring position (0–1) under a point, or None away from the ring."""
        cx,cy,r=DIAL
        distance=math.hypot(x-cx,y-cy)
        if strict and not r-34<=distance<=r+28:return None
        if distance<8:return None
        angle=(math.degrees(math.atan2(y-cy,x-cx))-DIAL_START)%360
        if angle>DIAL_SWEEP:
            if strict:return None
            angle=0 if angle>DIAL_SWEEP+(360-DIAL_SWEEP)/2 else DIAL_SWEEP
        return angle/DIAL_SWEEP

    def dial_from_event(self,event):
        values=[float(v) for v in self.selected.get("temperatures",[])]
        if not values:return
        s=self.scale()
        ratio=self.dial_angle(event.x/s,event.y/s)
        if ratio is None:return
        target=min(values)+ratio*(max(values)-min(values))
        value=min(values,key=lambda v:abs(v-target))
        try:same=float(self.temp.get())==value
        except ValueError:same=False
        if not same:self.staged("tempSel",value)
        else:self.draw()

    def drag_temperature(self,event):
        if self.dial_drag and not self.busy and self.selected:
            self.dial_from_event(event)

    def wheel_temperature(self,event):
        if self.busy or not self.selected or not event.delta:return
        s=self.scale()
        cx,cy,r=DIAL
        if math.hypot(event.x/s-cx,event.y/s-cy)<=r+30:
            self.step_temp(1 if event.delta>0 else -1)

    def step_temp(self,direction):
        values=[float(v) for v in self.selected["temperatures"]]
        if not values:return
        try:current=float(self.temp.get())
        except ValueError:current=values[0]
        index=min(range(len(values)),key=lambda n:abs(values[n]-current))
        self.staged("tempSel",values[max(0,min(len(values)-1,index+direction))])

    def toggle_label(self,key):
        if key not in self.selected.get("controls",{}):return "Unavailable"
        value=self.current(key)
        return {"0":"Off","1":"On"}.get(code(value),"Unknown")

    def choice_menu(self,key):
        spec=self.selected.get("controls",{}).get(key)
        if not spec:return
        if key=="machMode":
            options=mode_choices(self.selected)
            current={"machMode":self.current("machMode"),
                     "silentSleepStatus":self.current("silentSleepStatus")}
            current.update(self.dirty)
            def selected(patch):
                for name,value in self.memory.mode_values(self.selected,patch).items():self.staged(name,value)
        else:
            options=[{"label":label,"value":value,"glyph":"fan" if key=="windSpeed" else "moon"} for label,value in spec.get("options",{}).items()]
            current=self.current(key)
            def selected(value):
                patch={key:value}
                if key=="silentSleepStatus" and code(self.current("machMode")) in {"1","4"}:
                    patch["machMode"]=code(self.current("machMode"))
                    patch=self.memory.mode_values(self.selected,patch)
                for name,new_value in patch.items():self.staged(name,new_value)
        self.choice_panel=ChoicePanel(self.root,spec["label"],options,current,selected)

    def airflow_label(self):
        controls=self.selected.get("controls",{})
        if not any(k in controls for k in ("windDirectionVertical","windDirectionHorizontal")):return "Unavailable"
        if all(self.current(k) is None for k in ("windDirectionVertical","windDirectionHorizontal")):return "Unknown"
        vertical=code(self.current("windDirectionVertical"))=="8"
        horizontal=code(self.current("windDirectionHorizontal"))=="7"
        if vertical and horizontal:return "Both"
        if vertical:return "Vertical"
        if horizontal:return "Horizontal"
        return "Fixed"

    def airflow_menu(self):
        options=[]
        current={}
        for key in ("windDirectionVertical","windDirectionHorizontal"):
            spec=self.selected.get("controls",{}).get(key)
            if not spec:continue
            current[key]=self.current(key)
            options.extend(airflow_choices(spec,patch=True))
        def selected(patch):
            for key,value in patch.items():self.staged(key,value)
        if options:self.choice_panel=ChoicePanel(self.root,"Airflow",options,current,selected)

    def refresh(self):
        if self.busy or not self.selected:return
        if self.demo:
            self.show_device(self.selected);self.status.set("Preview refreshed. No network connection.");return
        self.set_busy(True)
        self.status.set("Refreshing reported AC status…")
        def done(device):
            self.show_device(device,preserve_edits=True)
            if not device.get("confirmation_expired"):
                self.status.set("Status retrieved from the cloud service.")
            self.schedule_auto()
        self.worker.submit(self.worker.controller.refresh(self.selected["id"]),done,"refresh")

    def reset_auto(self):
        self.refresh_epoch += 1
        if self.auto_job is not None:
            self.root.after_cancel(self.auto_job)
        self.auto_job = None
        self.auto_inflight = False
        self.auto_pending = False
        self.auto_failures = 0

    def schedule_auto(self, delay=15000):
        if self.demo or self.selected is None:
            return
        if self.auto_job is not None:
            self.root.after_cancel(self.auto_job)
        self.auto_job = self.root.after(delay, self.auto_refresh)

    def auto_refresh(self):
        self.auto_job = None
        if self.demo or self.selected is None:
            return
        if self.busy or self.auto_inflight:
            self.auto_pending = True
            self.schedule_auto(1000)
            return
        self.auto_inflight = True
        self.auto_pending = False
        epoch, device_id = self.refresh_epoch, self.selected["id"]
        def valid():
            return epoch == self.refresh_epoch and self.selected is not None and device_id == self.selected["id"]
        def done(device):
            if not valid(): return
            self.auto_inflight = False
            self.auto_failures = 0
            self.show_device(device,preserve_edits=True)
            self.schedule_auto(750 if self.auto_pending else 15000)
        def failed(error):
            if not valid(): return
            self.auto_inflight = False
            self.auto_failures += 1
            self.connection.set("Status unavailable · Retrying automatically")
            self.schedule_auto(min(60000,15000 * 2**min(self.auto_failures,2)))
        self.worker.submit(self.worker.controller.refresh(device_id),done,"auto-refresh",on_error=failed)

    def action(self,action,requested=None):
        if self.busy or not self.selected:return
        if self.demo:
            self.status.set("Design preview only. No command sent.");return
        if requested is None:requested={} if action=="off" else dict(self.dirty)
        if action=="on":requested=self.memory.mode_values(self.selected,requested)
        if action=="apply":action="configure"
        # Results requested before this command must not overwrite its selection.
        self.refresh_epoch+=1
        self.auto_inflight=False
        self.set_busy(True)
        self.status.set("Sending changes to the cloud service…")
        def done(text):
            if action in {"on","configure"}:
                self.pending_changes.update({key:str(value) for key,value in requested.items() if key in self.selected.get("controls",{})})
            else:self.pending_changes={}
            self.dirty={}
            self.set_busy(False)
            device={**self.selected,"pending_changes":dict(self.pending_changes)}
            device.pop("confirmation_expired",None)
            self.show_device(device,preserve_edits=True)
            self.status.set(text)
            # Allow the unit time to acknowledge; do not present optimistic state as confirmed.
            self.schedule_auto(12000)
        self.worker.submit(self.worker.controller.action(self.selected["id"],action,requested),done,"command")

    def open_functions(self):
        if self.busy or not self.selected:
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        from .functions_view import FunctionsView
        self.functions_view = FunctionsView(self)

    def change_timer(self, action, due):
        if self.busy or not self.selected:
            return
        if not self.demo:
            timers = self.selected.get("timers", {})
            item = timers.get("values", {}).get(action, {})
            if not timers.get("available") or not item.get("supported"):
                self.status.set("Timers unavailable. Refresh, or manage them in hOn.")
                return
            device_id, epoch = self.selected["id"], self.refresh_epoch
            requested = self.memory.mode_values(self.selected, dict(self.dirty)) if action == "on" and due else {}
            self.set_busy(True)
            self.status.set("Saving timer to hOn…" if due else "Stopping timer in hOn…")
            def done(snapshot):
                if epoch != self.refresh_epoch or not self.selected or self.selected["id"] != device_id:
                    return
                if action in self.inline_timers.cards:
                    self.inline_timers.cards[action].draft = False
                self.show_device(snapshot, preserve_edits=True)
                self.status.set("Timer saved in hOn. It works with your PC off." if due else "Timer stopped in hOn.")
                self.schedule_auto(750)
            def failed(error):
                self.status.set(error)
                self.schedule_auto(750)
            self.worker.submit(self.worker.controller.change_timer(device_id, action, due, item.get("expected"), requested), done, "timer", on_error=failed)
            return
        self.preview_timers.setdefault(self.selected["id"], {})[action] = due
        if action in self.inline_timers.cards:
            self.inline_timers.cards[action].draft = False
        self.status.set("Offline timer preview only. No schedule or AC command was sent.")
        self.draw()

    # Repeating schedules. The offline preview keeps fictional records locally.

    def open_schedules(self, parent=None):
        if self.busy or not self.selected:
            return
        if self.schedules_view and self.schedules_view.window.winfo_exists():
            self.schedules_view.window.lift()
            return
        from .schedules_view import SchedulesView
        SchedulesView(self, parent)

    def preview_rows(self):
        from .schedules import schedule_rows
        return schedule_rows({"scheduledPrograms": self.preview_records.get(self.selected["id"], [])})

    def load_schedules(self, done, failed):
        if self.demo:
            done(self.preview_rows())
            return
        device_id = self.selected["id"]
        self.worker.submit(self.worker.controller.schedule_list(device_id), done, "schedule-list", on_error=failed)

    def confirm_conflict(self, found, parent):
        from .schedules import clock_text, day_labels
        item = found[0]
        days = ", ".join(tr(self.root, label) for label in day_labels(item["days"]))
        message = f"This overlaps another schedule at {clock_text(item['time'])} on {days}. Save anyway?"
        return messagebox.askyesno("Room AC Control", tr(self.root, message), parent=parent)

    def save_schedule(self, ident, start, end, days, requested, done, failed, parent=None, cancelled=None, allow_conflict=False):
        """Create or edit a repeating schedule, asking before saving over an overlap."""
        parent = parent or self.root
        if self.demo:
            from .schedules import conflicts, preview_record
            from .controller import ControlError
            rows = self.preview_rows()
            found = conflicts(rows, start, end, days, ignore=ident)
            if found and not allow_conflict and not self.confirm_conflict(found, parent):
                if cancelled: cancelled()
                return
            records = self.preview_records.setdefault(self.selected["id"], [])
            try:
                record = preview_record(ident or f"preview-{len(records)+1}", start, end, days, requested)
            except ControlError as error:
                failed(str(error))
                return
            records[:] = [item for item in records if item["id"] != ident] + [record]
            done(self.preview_rows())
            return
        device_id = self.selected["id"]
        def finished(result):
            if not result["saved"]:
                if self.confirm_conflict(result["conflicts"], parent):
                    if parent is self.root:
                        self.set_busy(True)  # The dashboard stays locked for the second request.
                    self.save_schedule(ident, start, end, days, requested, done, failed, parent, cancelled, allow_conflict=True)
                elif cancelled:
                    cancelled()
                return
            if self.selected and self.selected["id"] == device_id:
                self.show_device(result["snapshot"], preserve_edits=True)
            done(result["rows"])
        self.worker.submit(self.worker.controller.change_schedule(
            device_id, "save", ident=ident, start=start, end=end, days=days, requested=requested,
            allow_conflict=allow_conflict), finished, "schedule", on_error=failed)

    def change_schedule(self, operation, ident, done, failed, active=None):
        """Pause, resume or delete a schedule."""
        if self.demo:
            records = self.preview_records.get(self.selected["id"], [])
            if operation == "delete":
                records[:] = [item for item in records if item["id"] != ident]
            else:
                for item in records:
                    if item["id"] == ident:
                        item["isActive"] = bool(active)
            done(self.preview_rows())
            return
        device_id = self.selected["id"]
        options = {"ident": ident} if operation == "delete" else {"ident": ident, "active": active}
        def finished(result):
            if self.selected and self.selected["id"] == device_id:
                self.show_device(result["snapshot"], preserve_edits=True)
            done(result["rows"])
        self.worker.submit(self.worker.controller.change_schedule(device_id, operation, **options),
                           finished, "schedule", on_error=failed)

    def timer_repeat_menu(self, card):
        """Once, every day, weekdays, weekend or chosen days for a Start at / End at card."""
        from .schedules import EVERY_DAY, WEEKDAYS, WEEKEND
        presets = {"every": EVERY_DAY, "weekdays": WEEKDAYS, "weekend": WEEKEND}
        current = next((key for key, days in presets.items() if days == card.repeat), "custom") if card.repeat else "once"
        options = [{"label": "Once", "value": "once", "glyph": "clock", "description": "Runs one time, then clears"},
                   {"label": "Every day", "value": "every", "glyph": "clock", "description": "Saved as a repeating schedule"},
                   {"label": "Weekdays", "value": "weekdays", "glyph": "clock", "description": "Monday to Friday"},
                   {"label": "Weekend", "value": "weekend", "glyph": "clock", "description": "Saturday and Sunday"},
                   {"label": "Choose days…", "value": "custom", "glyph": "clock", "description": "Pick days of the week"}]
        def chosen(value):
            if value == "custom":
                from .schedules_view import DayPicker
                DayPicker(self.root, card.repeat or WEEKDAYS, lambda days: card.set_repeat(days))
            else:
                card.set_repeat(presets.get(value, ()))
        self.repeat_panel = ChoicePanel(self.root, "Repeat", options, current, chosen)

    def save_repeating_timer(self, action, clock, days):
        """A Start at / End at card with a repeat creates a repeating schedule."""
        if self.busy or not self.selected:
            return
        start, end = (clock, None) if action == "on" else (None, clock)
        requested = self.memory.mode_values(self.selected, dict(self.dirty)) if action == "on" else {}
        card = self.inline_timers.cards.get(action)
        def saved(rows):
            if card is not None:
                card.repeat, card.draft = (), False
            self.status.set("Offline timer preview only. No schedule or AC command was sent." if self.demo
                            else "Repeating schedule saved in hOn. Manage it in Schedules.")
            self.draw()
            if not self.demo:
                self.schedule_auto(750)
        def failed(error):
            self.status.set(error)
            if not self.demo:
                self.schedule_auto(750)
        if not self.demo:
            self.set_busy(True)
            self.status.set("Saving schedule to hOn…")
        self.save_schedule(None, start, end, days, requested, saved, failed,
                           cancelled=lambda: self.status.set("Not saved. Adjust the time or days."))

    def field(self,parent,spec,override=None,use_reported=False,show_label=True):
        row=ttk.Frame(parent,padding=(0,7))
        row.pack(fill="x")
        label=spec["label"]
        value=override if override is not None else (spec["value"] if not use_reported or spec.get("reported") else "")
        if show_label:localized(ttk.Label(row,text=label)).pack(side="left")
        if spec["kind"]=="enum":
            options=spec["options"]
            variable=tk.StringVar(value=next((k for k,v in options.items() if equal(v,value)),"Choose…"))
            choices=None
            if spec["key"] in {"windDirectionVertical","windDirectionHorizontal"}:
                choices=[dict(option,value=option["label"]) for option in airflow_choices(spec)]
            elif spec["key"]=="machMode":
                choices=[{"label":label,"value":label,"glyph":mode_icon(label)} for label in options]
            widget=SelectField(row,variable,options,spec["label"],choices=choices)
            getter=lambda:options.get(variable.get())
        elif spec["key"] == "tempSel":
            widget=TemperatureWheel(row,spec,value)
            getter=widget.get
        else:
            variable=tk.StringVar(value=f"{float(value):g}" if value!="" else "")
            widget=ttk.Spinbox(row,textvariable=variable,from_=spec["min"],to=spec["max"],increment=spec["step"],width=20)
            getter=lambda:variable.get() or None
        widget.pack(side="right" if show_label else "top")
        if use_reported and value=="":
            localized(ttk.Label(parent,text="Current value not reported",style="Muted.TLabel",font=font(8))).pack(anchor="e")
        return getter,value

    def logout(self):
        if self.busy:return
        if self.demo:return
        try:
            self.storage.forget_credentials()
        except OSError:
            self.status.set("Could not remove saved sign-in. Check access to the app's data folder.")
            return
        self.reset_auto()
        self.set_busy(True)
        def done(value):
            self.selected=None;self.devices=[];self.dirty={}
            self.airflow.set_state(None,WIDTH/2,*FLOW)
            self.toast.hide()
            self.panel.pack_forget()
            self.login_frame.pack(fill="x",pady=(5,0))
            self.status_label.pack(fill="x",pady=(8,0))
            self.remember_account.set(False)
            self.status.set("Signed out.")
            self.set_busy(False)
        self.worker.submit(self.worker.controller.close(),done,"logout")

    # Signed app updates for the portable build.

    def auto_check_updates(self):
        self.update_job = None
        if self.closing:return
        if self.updater.enabled:self.updater.check(quiet=True)
        self.update_job = self.root.after(updates.CHECK_EVERY_MS, self.auto_check_updates)

    def set_auto_update(self, value):
        self.updater.enabled = bool(value)
        try:self.storage.save_auto_update(bool(value))
        except OSError:self.status.set("Update setting changed for this session, but the preference could not be saved.")
        if value and self.updater.state in {"idle", "current"}:self.updater.check(quiet=True)
        self.updater.notify()

    def updates_changed(self):
        if self.closing:return
        waiting = self.updater.release is not None and self.updater.state in {"available", "downloading", "verifying", "ready", "failed"}
        self.settings_button.set_badge(waiting)
        if self.updater.state == "ready":
            # The person clicked Update; the helper waits for this process to exit.
            try:applied = self.updater.apply()
            except OSError as error:
                diagnostics.record("update_failed", error)
                self.updater.state, self.updater.error = "failed", "Could not start the update helper. Nothing was changed."
                self.updater.notify()
                return
            if applied:self.root.after(300, self.close)

    def open_updates(self, parent=None):
        if self.updates_view and self.updates_view.window.winfo_exists():
            self.updates_view.window.lift()
            return
        from .updates_view import UpdatesView
        UpdatesView(self, parent or self.root)

    def close(self):
        if self.closing:return
        self.closing=True
        self.updater.close()
        if getattr(self, "poll_job", None) is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        if self.update_job is not None:
            self.root.after_cancel(self.update_job)
            self.update_job = None
        self.login_view.close()
        self.reset_auto()
        self.airflow.close()
        if self.tray:
            try:self.tray.close()
            except Exception as error:diagnostics.record("tray_close_failed",error)
        self.worker.close()
        self.root.destroy()

    def on_minimize(self,event):
        if event.widget is self.root and not self.closing and self.root.state()=="iconic":
            self.root.after(50,self.minimize_to_tray)

    def minimize_window(self):
        if not self.closing:
            self.root.iconify()

    def minimize_to_tray(self):
        if not self.closing and self.tray and self.root.state()=="iconic" and self.tray.show():
            self.root.withdraw()

    def restore_window(self):
        if self.closing:return
        if self.tray:
            try:self.tray.hide()
            except Exception as error:diagnostics.record("tray_hide_failed",error)
        self.root.deiconify()
        self.root.lift()
        active=self.root.grab_current()
        if active and active.winfo_exists():
            active.deiconify()
            active.lift()
            active.focus_force()
        else:self.root.focus_force()

    def callback_failed(self, kind, error, traceback):
        diagnostics.record("ui_callback_failed", error)
        if self.login_view.loading:
            self.login_view.set_loading(False)
            self.set_busy(False)
        self.status.set("An interface action failed. You can export diagnostics for troubleshooting.")

    def export_diagnostics(self):
        destination=filedialog.asksaveasfilename(parent=self.root, title=tr(self.root,"Save diagnostics"),
                initialfile="room-ac-diagnostics.json", defaultextension=".json", filetypes=[(tr(self.root,"JSON report"),"*.json")])
        if destination:
            try:diagnostics.export(Path(destination))
            except OSError:self.status.set("Could not save the diagnostic report. Choose a writable folder.")
