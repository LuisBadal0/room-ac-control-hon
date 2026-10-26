"""Light or dark desktop dashboard with live-discovered appliance controls."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue

from .controller import code, readable, mode_choices, mode_label
from .choice_widgets import ChoicePanel, SelectField
from .control_choices import mode_icon, airflow_choices
from .theme import (C, THEMES, ASSETS, font, measure, paint, rounded, icon, ac_art, unit_photo, control_card,
                    resolve_theme, refresh_on_theme, broadcast_theme)
from .button_theme import configure_styles
from .canvas_hover import CanvasHover
from .worker import Worker, degrees
from .secure_state import SecureState
from .program_memory import ProgramMemory
from .airflow import AirflowAnimation
from pathlib import Path
from .device_picker import DevicePicker, PowerButton
from .diagnostics import diagnostics
from .inline_timers import InlineTimers, TimerCard
from .temperature_wheel import TemperatureWheel
from .i18n import Translator, LANGUAGES, tr, localized, TranslatedVariable, localized_title, broadcast_language, refresh_on_language

# The dashboard canvas is laid out in a 520 px space and scaled with the window.
WIDTH = 520
TEMP_TOP = 172
TRACK = (18, 502)
TRACK_Y = TEMP_TOP + 132
TIMER_TOP = 368
TILE_TOP = TIMER_TOP + TimerCard.HEIGHT + 12
TILE_HEIGHT = 104
CANVAS_HEIGHT = TILE_TOP + TILE_HEIGHT + 2
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
        self.unit_image = unit_photo(root, 330)
        root.iconbitmap(str(ASSETS / "app.ico"))
        self.app_icon = tk.PhotoImage(master=root, file=str(ASSETS / "app-icon.png"))
        root.iconphoto(True, self.app_icon)
        localized_title(root,"Room AC Control for hOn" + (" · Design preview" if demo else ""))
        root.geometry("560x960")
        root.minsize(540, 920)
        paint(root, bg="BG")
        configure_styles(root)
        from .window_header import WindowHeader, HeaderIconButton
        self.header = WindowHeader(root, "Room AC Control · hOn", self.close, self.minimize_window)
        self.language_code = tk.StringVar(root, value="PT" if self.i18n.language == "pt-PT" else "EN")
        self.language_button = tk.Button(self.header.frame,textvariable=self.language_code,command=self.language_menu,
                                        relief="flat",bd=0,font=font(9,"black"),padx=10,cursor="hand2")
        paint(self.language_button,bg="BG",fg="BRAND",activebackground="SURFACE",activeforeground="TEXT")
        self.language_button.pack(side="right",fill="y")
        self.theme_button = HeaderIconButton(self.header.frame,"half",self.theme_menu)
        self.theme_button.pack(side="right")
        self.content = ttk.Frame(root)
        self.content.pack(fill="both",expand=True)
        self.body = ttk.Frame(self.content, padding=(20,6,20,16))
        self.body.place(relx=.5,y=0,anchor="n",relheight=1,width=560)
        self.content.bind("<Configure>",lambda event:self.body.place_configure(width=min(560,event.width)))
        from .login_view import LoginView
        self.login_view = LoginView(self)
        self.login_frame = self.login_view.frame
        self.login_frame.pack(fill="x",pady=(5,0))
        self.panel=ttk.Frame(self.body)
        top=ttk.Frame(self.panel)
        top.pack(fill="x",pady=(0,12))
        self.power_button=PowerButton(top,self.toggle_power)
        self.power_button.pack(side="right",padx=(12,0))
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
        self.canvas.bind("<Left>",lambda e:self.step_temp(-1) if not self.busy and self.selected else None)
        self.canvas.bind("<Right>",lambda e:self.step_temp(1) if not self.busy and self.selected else None)
        # Main selectors retain Tk variables for menu and keyboard support.
        self.mode,self.temp,self.fan=tk.StringVar(),tk.StringVar(),tk.StringVar()
        controls=ttk.Frame(self.panel)
        controls.pack(fill="x",pady=(12,10))
        controls.columnconfigure(0,weight=13,uniform="actions")
        controls.columnconfigure(1,weight=10,uniform="actions")
        self.apply_button=ttk.Button(controls,style="Accent.TButton",command=lambda:self.action("apply"))
        refresh_on_language(self.apply_button,self.update_apply_label)
        self.update_apply_label()
        self.apply_button.grid(row=0,column=0,sticky="ew",padx=(0,6))
        self.all_button=localized(ttk.Button(controls,text="All functions",command=self.open_functions))
        self.all_button.grid(row=0,column=1,sticky="ew",padx=(6,0))
        footer=ttk.Frame(self.panel)
        footer.pack(fill="x")
        self.connection=tk.StringVar()
        self.connection_display=TranslatedVariable(root,self.connection)
        self.connection_dot=tk.Label(footer,text="●",font=("Segoe UI",8),bd=0)
        self.connection_dot.pack(side="left",padx=(2,6))
        refresh_on_theme(self.connection_dot,self.paint_connection)
        self.connection.trace_add("write",lambda *args:self.paint_connection())
        self.paint_connection()
        ttk.Label(footer,textvariable=self.connection_display,style="Muted.TLabel",font=font(9)).pack(side="left")
        self.refresh_button=localized(ttk.Button(footer,text="↻ Refresh",style="Ghost.TButton",command=self.refresh))
        self.refresh_button.pack(side="right")
        self.logout_button=localized(ttk.Button(footer,text="Sign out",style="Ghost.TButton",command=self.logout))
        self.logout_button.pack(side="right",padx=(0,2))
        self.status=tk.StringVar(value="Sign in to connect to your air conditioner.")
        self.status_display=TranslatedVariable(root,self.status)
        self.status_label=tk.Label(self.body,textvariable=self.status_display,font=font(9),anchor="w",justify="left",
                                   padx=12,pady=8,wraplength=480,bd=0)
        paint(self.status_label,bg="SOFT",fg="ON_SOFT")
        self.status_label.pack(fill="x",pady=(10,0))
        self.status_label.bind("<Configure>",lambda event:self.status_label.configure(wraplength=max(1,event.width-24)))
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.root.report_callback_exception = self.callback_failed
        self.root.bind("<Unmap>",self.on_minimize,add="+")
        root.after(100,self.poll)
        if not demo:root.after(200,self.auto_sign_in)

    def language_menu(self, parent=None):
        parent = parent or self.root
        options = [{"label":"System language","value":"system","glyph":"globe","description":"Follow Windows language"}]
        options.extend({"label":label,"value":value,"glyph":"globe"} for value,label in LANGUAGES.items())
        self.language_panel = ChoicePanel(parent,"Language",options,self.i18n.preference,self.set_language)

    def set_language(self, preference):
        self.i18n.set_language(preference)
        self.language_code.set("PT" if self.i18n.language == "pt-PT" else "EN")
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
                    if operation in {"auto-refresh", "login", "timer"}:
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
        # Follow Windows: notice an app-mode switch within about two seconds.
        self.theme_checks += 1
        if self.theme_checks >= 20:
            self.theme_checks = 0
            if self.theme_preference == "system":
                self.apply_theme()
        self.root.after(100,self.poll)

    def update_apply_label(self):
        count = len(self.dirty)
        self.apply_button.configure(text=tr(self.apply_button,"Apply changes")+(f" ({count})" if count else ""))

    def paint_connection(self):
        connected = self.connection.get().startswith("Connected")
        self.connection_dot.configure(bg=C.BG, fg=C.OK if connected else C.FAINT)

    def set_busy(self,value):
        self.busy=value
        state="disabled" if value else "normal"
        for widget in (self.email,self.password,self.login_button):
            widget.configure(state=state)
        available=self.selected is not None and not value
        for widget in (self.refresh_button,self.logout_button,self.all_button):
            widget.configure(state="normal" if available else "disabled")
        self.apply_button.configure(state="normal" if available and self.dirty else "disabled")
        self.update_apply_label()
        self.device_picker.set_enabled(available)
        self.power_button.set_state(self.selected is not None and self.selected["power"]=="On", available)
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
        self.panel.pack(fill="x",before=self.status_label)
        self.device_picker.set_devices(devices)
        index=0
        self.device_picker.current(index)
        self.show_device(devices[index])
        self.status.set("Design preview · No AC commands are sent." if self.demo else "Connected. Select changes, then apply.")
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

    def draw(self):
        if not self.selected:return
        c=self.canvas
        c.delete("all")
        c.configure(bg=C.BG)
        self.hits=[]
        width=max(c.winfo_width(),480)
        s=width/WIDTH
        self.canvas_hover.reset(s,enabled=not self.busy)
        def hover(box,item,fill=None,outline=None):
            normal={"fill":fill or C.CARD,"outline":C.EDGE if outline is None else outline}
            self.canvas_hover.add(box,item,normal,{"fill":C.HOVER if fill is None else C.STRONG,"outline":C.BRAND})
        text=lambda x,y,t,size=10,color=None,anchor="w",weight="normal",translate=True:c.create_text(
            x,y,text=tr(c,t) if translate else t,fill=color or C.TEXT,anchor=anchor,font=font(size,weight))
        hit=lambda box,fn:self.hits.append((box,fn))
        # Hero: room temperature, status chip and the unit with its live airflow.
        icon(c,"thermo",8,14,C.MUTED,scale=.7,bg=C.BG)
        room=text(20,14,"Room",10,C.MUTED)
        text(c.bbox(room)[2]+8,14,self.i18n.number(degrees(self.selected["room"])),11,weight="bold")
        if self.dirty:status,fill,ink="Changes pending",C.WARN_BG,C.WARN_TEXT
        elif self.pending_changes:status,fill,ink="Awaiting confirmation",C.SOFT,C.ON_SOFT
        elif self.selected["power"]=="On":status,fill,ink="On",C.OK_BG,C.OK_TEXT
        else:status,fill,ink=self.selected["power"],C.SURFACE,C.TEXT
        status=tr(c,status)
        chip=measure(c,status,9,"bold")
        rounded(c,WIDTH-chip-34,1,WIDTH,27,13,fill=fill,outline="")
        c.create_oval(WIDTH-chip-23,10.5,WIDTH-chip-16,17.5,fill=ink,outline="")
        text(WIDTH-12,14,status,9,ink,"e","bold",translate=False)
        ac_art(c,260,82,photo=self.unit_image)
        # Target temperature card: −/+, Eco toggle and the stepped slider.
        T=TEMP_TOP
        rounded(c,0,T,WIDTH,T+182,12,fill=C.CARD,outline=C.EDGE)
        text(16,T+24,"Target temperature",10,weight="bold")
        eco=self.selected.get("controls",{}).get("ecoMode")
        if eco:
            active=code(self.current("ecoMode"))=="1"
            rounded(c,464,T+12,504,T+36,12,fill=C.BRAND if active else C.FIELD,outline="")
            c.create_oval(482 if active else 466,T+14,502 if active else 486,T+34,fill=C.THUMB,outline="")
            label=text(454,T+24,"Eco Mode",10,anchor="e")
            left=c.bbox(label)[0]
            icon(c,"leaf",left-14,T+24,C.ECO,scale=.7)
            hit((left-26,T+4,WIDTH-8,T+44),lambda:self.staged("ecoMode","0" if active else "1"))
        else:
            text(504,T+24,"Eco Mode · Unavailable",9,C.MUTED,"e")
        values=[float(v) for v in self.selected.get("temperatures",[])]
        for x,direction in ((40,-1),(480,1)):
            step=c.create_oval(x-24,T+62,x+24,T+110,fill=C.SURFACE,outline="")
            if values:hover((x-24,T+62,x+24,T+110),step,fill=C.SURFACE,outline="")
            mark=C.TEXT if values else C.FAINT
            c.create_line(x-9,T+86,x+9,T+86,fill=mark,width=2,capstyle="round")
            if direction>0:c.create_line(x,T+77,x,T+95,fill=mark,width=2,capstyle="round")
            if values:hit((x-24,T+62,x+24,T+110),lambda direction=direction:self.step_temp(direction))
        value=self.temp.get()
        try:value=f"{float(value):g}"
        except ValueError:value="—"
        temperature=text(260,T+86,self.i18n.number(value),46,anchor="center",weight="black",translate=False)
        c.itemconfigure(temperature,tags="target-temperature")
        unit=text(300,T+70,"°C",16,C.MUTED,"nw",translate=False)
        c.itemconfigure(unit,tags="temperature-unit")
        x1,x2=TRACK
        rounded(c,x1,TRACK_Y-4,x2,TRACK_Y+4,4,fill=C.TRACK,outline="")
        if values:
            try:ratio=(float(self.temp.get())-min(values))/(max(values)-min(values)) if max(values)!=min(values) else 0
            except ValueError:ratio=0
            tx=x1+max(0,min(1,ratio))*(x2-x1)
            rounded(c,x1,TRACK_Y-4,max(x1+8,tx),TRACK_Y+4,4,fill=C.BRAND,outline="")
            thumb=c.create_oval(tx-11,TRACK_Y-11,tx+11,TRACK_Y+11,fill=C.THUMB,outline=C.BRAND,width=2)
            self.canvas_hover.add((x1-10,TRACK_Y-20,x2+10,TRACK_Y+24),thumb,{"outline":C.BRAND,"width":2},
                                  {"outline":C.BRAND_ACTIVE,"width":3})
            for index in range(9):
                tick=x1+index*(x2-x1)/8
                c.create_line(tick,TRACK_Y+16,tick,TRACK_Y+22,fill=C.FAINT)
            low,high=min(values),max(values)
            text(x1,T+168,self.i18n.number(f"{low:g}°"),9,C.MUTED,translate=False)
            text(260,T+168,self.i18n.number(f"{(low+high)/2:g}°"),9,C.MUTED,"center",translate=False)
            text(x2,T+168,self.i18n.number(f"{high:g}°"),9,C.MUTED,"e",translate=False)
            hit((x1-10,TRACK_Y-20,x2+10,TRACK_Y+24),self.slider_from_event)
        self.inline_timers.refresh(self.selected, self.busy)
        timer_row = c.create_window(0, TIMER_TOP, window=self.inline_timers, anchor="nw", width=WIDTH, height=TimerCard.HEIGHT)
        c.itemconfigure(timer_row,tags="inline-timers")
        airflow=self.airflow_label()
        cards=[("Mode",self.mode.get(),mode_icon(self.mode.get()),lambda:self.choice_menu("machMode")),
               ("Fan speed",self.fan.get(),"fan",lambda:self.choice_menu("windSpeed")),
               ("Sleep",self.toggle_label("silentSleepStatus"),"moon",lambda:self.choice_menu("silentSleepStatus")),
               ("Airflow",airflow,"swing" if airflow in {"Vertical","Both"} else "wind",self.airflow_menu)]
        tile=(WIDTH-24)/4
        for i,(label,value,glyph,fn) in enumerate(cards):
            x=i*(tile+8)
            card=control_card(c,x,TILE_TOP,tile,label,value,glyph,s,active=value not in {"Off","Unavailable","Unknown"},height=TILE_HEIGHT)
            if value!="Unavailable":hover((x,TILE_TOP,x+tile,TILE_TOP+TILE_HEIGHT),card)
            hit((x,TILE_TOP,x+tile,TILE_TOP+TILE_HEIGHT),fn)
        if s!=1:c.scale("all",0,0,s,s)
        # Canvas scaling also changes embedded window dimensions. Apply its final
        # width once, while preserving the native wheels' full height.
        c.itemconfigure(timer_row,width=round(WIDTH*s),height=TimerCard.HEIGHT)
        number,symbol=c.bbox(temperature),c.bbox(unit)
        left=260*s-((number[2]-number[0])+6+(symbol[2]-symbol[0]))/2
        c.move(temperature,left-number[0],0)
        number=c.bbox(temperature)
        c.coords(unit,number[2]+6,number[1]+12)
        self.canvas.configure(height=int(CANVAS_HEIGHT*s))
        self.airflow.set_state(self.selected,260,129,275,38,s)
        self.canvas_hover.update()
        if self.busy:
            self.hits=[]

    def click(self,event):
        if self.busy:return
        self.canvas.focus_set()
        s=max(self.canvas.winfo_width(),480)/WIDTH
        x,y=event.x/s,event.y/s
        for (x1,y1,x2,y2),fn in self.hits:
            if x1<=x<=x2 and y1<=y<=y2:
                if fn==self.slider_from_event:fn(event)
                else:fn()
                break

    def slider_from_event(self,event):
        values=[float(v) for v in self.selected["temperatures"]]
        s=max(self.canvas.winfo_width(),480)/WIDTH
        ratio=max(0,min(1,(event.x/s-TRACK[0])/(TRACK[1]-TRACK[0])))
        self.staged("tempSel",min(values,key=lambda v:abs(v-(min(values)+ratio*(max(values)-min(values))))))

    def drag_temperature(self,event):
        s=max(self.canvas.winfo_width(),480)/WIDTH
        if (not self.busy and self.selected and self.selected["temperatures"]
                and TRACK_Y-20<=event.y/s<=TRACK_Y+24 and TRACK[0]-10<=event.x/s<=TRACK[1]+10):
            self.slider_from_event(event)

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
        self.inline_timers.cards[action].draft = False
        self.status.set("Offline timer preview only. No schedule or AC command was sent.")
        self.draw()

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
            self.airflow.set_state(None,260,129,275,38)
            self.panel.pack_forget()
            self.login_frame.pack(fill="x",pady=(5,0),before=self.status_label)
            self.remember_account.set(False)
            self.status.set("Signed out.")
            self.set_busy(False)
        self.worker.submit(self.worker.controller.close(),done,"logout")

    def close(self):
        if self.closing:return
        self.closing=True
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
