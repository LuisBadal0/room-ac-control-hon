"""Dark desktop dashboard with live-discovered appliance controls."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue

from .controller import code, readable, mode_choices, mode_label
from .choice_widgets import ChoicePanel, SelectField
from .control_choices import mode_icon, airflow_choices
from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, GREEN, rounded, icon, ac_art, unit_photo, control_card
from .canvas_hover import CanvasHover
from .worker import Worker, degrees
from .secure_state import SecureState
from .program_memory import ProgramMemory
from .airflow import AirflowAnimation
from pathlib import Path
from .device_picker import DevicePicker
from .diagnostics import diagnostics


def equal(left, right):
    try:
        return float(left) == float(right)
    except (ValueError, TypeError):
        return str(left) == str(right)


class App:
    def __init__(self, root, demo=False, state=None, enable_tray=True):
        self.root, self.demo = root, demo
        self.storage = state if state is not None else SecureState(persistent=not demo)
        self.memory = ProgramMemory(self.storage)
        self.worker = Worker(memory=self.memory)
        self.tray = None
        self.closing = False
        if enable_tray and not demo:
            try:
                from .tray import SystemTray
                self.tray = SystemTray()
            except Exception as error:
                diagnostics.record("tray_start_failed", error)
        self.devices, self.selected = [], None
        self.busy, self.dirty = False, {}
        self.hits = []
        self.dialog = None
        self.auto_job = None
        self.auto_inflight = False
        self.auto_pending = False
        self.auto_failures = 0
        self.refresh_epoch = 0
        self.unit_image = unit_photo(root, 330)
        assets = Path(__file__).resolve().parent / "assets"
        root.iconbitmap(str(assets / "app.ico"))
        self.app_icon = tk.PhotoImage(master=root, file=str(assets / "app-icon.png"))
        root.iconphoto(True, self.app_icon)
        root.title("Room AC Control for hOn" + (" · Design preview" if demo else ""))
        root.geometry("560x840")
        root.minsize(540, 800)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TCheckbutton",background=BG,foreground=TEXT,font=("Segoe UI",10))
        style.map("TCheckbutton",background=[("active",BG)],foreground=[("disabled",MUTED)])
        style.configure("TButton", background=CARD, foreground=TEXT, borderwidth=0, padding=(12,10), font=("Segoe UI",10))
        style.map("TButton", background=[("disabled",CARD), ("active",HOVER)], foreground=[("disabled","#656d60")])
        style.configure("Accent.TButton", background=ACCENT, foreground=BG)
        style.map("Accent.TButton", background=[("disabled","#393d34"), ("active","#cbc6ad")])
        style.configure("Login.Accent.TButton", padding=(14,12), font=("Segoe UI",11,"bold"))
        style.configure("Login.TCheckbutton", background=CARD, foreground=MUTED, font=("Segoe UI",9))
        style.map("Login.TCheckbutton", background=[("active",CARD)], foreground=[("active",TEXT)])
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT, arrowcolor=ACCENT, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly",CARD)], foreground=[("readonly",TEXT)])
        style.configure("TEntry", fieldbackground=CARD, foreground=TEXT, padding=8)
        style.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT, arrowcolor=ACCENT, padding=5)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(14,9), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected","#30372c")], foreground=[("selected",TEXT)])
        style.configure("Vertical.TScrollbar", background="#343d2f", troughcolor=BG, arrowcolor=MUTED, borderwidth=0)
        root.option_add("*TCombobox*Listbox.background",CARD)
        root.option_add("*TCombobox*Listbox.foreground",TEXT)
        from .window_header import WindowHeader
        self.header = WindowHeader(root, "Room AC Control · hOn", self.close, self.minimize_window)
        self.content = ttk.Frame(root)
        self.content.pack(fill="both",expand=True)
        self.body = ttk.Frame(self.content, padding=(22,15,22,18))
        self.body.place(relx=.5,y=0,anchor="n",relheight=1,width=560)
        self.content.bind("<Configure>",lambda event:self.body.place_configure(width=min(560,event.width)))
        from .login_view import LoginView
        self.login_view = LoginView(self)
        self.login_frame = self.login_view.frame
        self.login_frame.pack(fill="x",pady=(5,0))
        self.panel=ttk.Frame(self.body)
        self.device_picker=DevicePicker(self.panel,self.select_device)
        self.device_picker.pack(fill="x",pady=(0,10))
        self.canvas=tk.Canvas(self.panel,bg=BG,highlightthickness=0,height=540)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>",lambda e:self.draw())
        self.canvas_hover = CanvasHover(self.canvas)
        self.airflow = AirflowAnimation(self.canvas)
        self.canvas.bind("<Button-1>",self.click)
        self.canvas.bind("<B1-Motion>",self.drag_temperature)
        self.canvas.bind("<Left>",lambda e:self.step_temp(-1) if not self.busy and self.selected else None)
        self.canvas.bind("<Right>",lambda e:self.step_temp(1) if not self.busy and self.selected else None)
        # Main selectors retain Tk variables for menu and keyboard support.
        self.mode,self.temp,self.fan=tk.StringVar(),tk.StringVar(),tk.StringVar()
        controls=ttk.Frame(self.panel)
        controls.pack(fill="x",pady=(6,12))
        self.apply_button=ttk.Button(controls,text="Apply changes",style="Accent.TButton",command=lambda:self.action("apply"))
        self.apply_button.pack(side="left",fill="x",expand=True,padx=(0,8))
        self.all_button=ttk.Button(controls,text="All functions",command=self.open_functions)
        self.all_button.pack(side="left",fill="x",expand=True)
        footer=ttk.Frame(self.panel)
        footer.pack(fill="x")
        self.connection=tk.StringVar()
        ttk.Label(footer,textvariable=self.connection,style="Muted.TLabel").pack(side="left")
        self.refresh_button=ttk.Button(footer,text="↻ Refresh",command=self.refresh)
        self.refresh_button.pack(side="right")
        self.logout_button=ttk.Button(footer,text="Sign out",command=self.logout)
        self.logout_button.pack(side="right",padx=(0,5))
        self.status=tk.StringVar(value="Sign in to connect to your air conditioner.")
        self.status_label=ttk.Label(self.body,textvariable=self.status,wraplength=500,style="Muted.TLabel")
        self.status_label.pack(fill="x",pady=(16,0))
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.root.report_callback_exception = self.callback_failed
        self.root.bind("<Unmap>",self.on_minimize,add="+")
        root.after(100,self.poll)
        if not demo:root.after(200,self.auto_sign_in)

    def poll(self):
        if self.closing:return
        try:
            while True:
                callback,value,error,operation=self.worker.results.get_nowait()
                if operation != "auto-refresh":
                    self.set_busy(False)
                if error:
                    if operation == "auto-refresh":
                        callback(error)
                    elif operation == "login":
                        callback(error)
                    else:
                        self.status.set(error)
                        messagebox.showerror("Room AC Control",error,parent=self.root)
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
        self.root.after(100,self.poll)

    def set_busy(self,value):
        self.busy=value
        state="disabled" if value else "normal"
        for widget in (self.email,self.password,self.login_button):
            widget.configure(state=state)
        available=self.selected is not None and not value
        for widget in (self.refresh_button,self.logout_button,self.all_button):
            widget.configure(state="normal" if available else "disabled")
        self.apply_button.configure(state="normal" if available and self.dirty else "disabled")
        self.device_picker.set_enabled(available)
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
        self.set_busy(True)
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
            self.set_busy(False)
            self.status.set(("Automatic sign-in failed. " if automatic else "")+error)
        self.worker.submit(self.worker.controller.connect(email,password),done,"login",on_error=failed)

    def connected(self,devices):
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
        self.mode.set(mode_label(device,pending))
        self.fan.set(next((label for label,value in device["fans"].items() if value==pending.get("windSpeed")),device["fan"]))
        self.temp.set(pending.get("tempSel",str(device["target"]) if device["target"] is not None else ""))
        state=device.get("connection","Unknown")
        label="Connected" if state=="CONNECTED" else ("Disconnected" if state=="DISCONNECTED" else "Connection unknown")
        self.connection.set(f"◇ {label} · {device['fetched']}" + (" · Auto" if not self.demo else ""))
        self.set_busy(self.busy if preserve_edits else False)
        if self.dialog and self.dialog.winfo_exists():
            self.functions_view.refresh_status()

    def select_device(self,event=None):
        if not self.busy:
            self.reset_auto()
            self.selected=self.devices[self.device_picker.current()]
            self.dirty={}
            self.refresh()

    def staged(self,key,value):
        if self.busy:return
        spec=self.selected.get("controls",{}).get(key)
        if spec and spec.get("reported") and equal(value,spec["value"]):
            self.dirty.pop(key,None)
        else:self.dirty[key]=str(value)
        if key in {"machMode","silentSleepStatus"}:self.mode.set(mode_label(self.selected,self.dirty))
        if key=="windSpeed":self.fan.set(next((label for label,v in self.selected["fans"].items() if v==str(value)),"Other"))
        if key=="tempSel":self.temp.set(str(value))
        self.status.set("Changes ready. Apply them, or use the power button to turn on." if self.dirty else "No pending changes.")
        self.set_busy(False)

    def current(self,key):
        if key in self.dirty:return self.dirty[key]
        spec=self.selected.get("controls",{}).get(key)
        return spec.get("value") if spec and spec.get("reported") else None

    def draw(self):
        if not self.selected:return
        c=self.canvas
        c.delete("all")
        self.hits=[]
        width=max(c.winfo_width(),480)
        s=width/520
        self.canvas_hover.reset(s,enabled=not self.busy)
        def hover(box,item,fill=CARD,outline=""):
            self.canvas_hover.add(box,item,{"fill":fill,"outline":outline}, {"fill":HOVER,"outline":ACCENT})
        text=lambda x,y,t,size=11,color=TEXT,anchor="w",bold=False:c.create_text(x,y,text=t,fill=color,anchor=anchor,font=("Segoe UI",size,"bold" if bold else "normal"))
        hit=lambda box,fn:self.hits.append((box,fn))
        text(8,22,"♧  Room",11,MUTED)
        text(95,22,degrees(self.selected["room"]),12,TEXT,bold=True)
        on=self.selected["power"]=="On"
        power=c.create_oval(469,1,513,45,fill=CARD,outline=ACCENT if on else "#394035",width=2)
        hover((469,1,513,45),power,outline=ACCENT if on else "#394035")
        c.create_arc(479,11,503,35,start=140,extent=260,style="arc",outline=ACCENT,width=2)
        c.create_line(491,8,491,22,fill=ACCENT,width=2)
        hit((469,1,513,45),lambda:self.action("off" if on else "on"))
        ac_art(c,260,95,photo=self.unit_image)
        text(260,201,self.selected["model"],9,MUTED,"center")
        value=self.temp.get()
        try:value=f"{float(value):g}"
        except ValueError:value="—"
        text(6,256,value,42,TEXT,bold=True)
        text(80 if len(value)<3 else 115,263,"°C",21,MUTED)
        eco=self.selected.get("controls",{}).get("ecoMode")
        eco_card=rounded(c,283,231,515,279,13,fill=CARD,outline="")
        if eco:hover((283,231,515,279),eco_card)
        icon(c,"leaf",309,255)
        text(330,255,"Eco Mode",11,TEXT if eco else MUTED,bold=True)
        eco_value=self.current("ecoMode")
        active=code(eco_value)=="1"
        rounded(c,445,245,498,266,10,fill=ACCENT if active else "#40473d",outline="")
        c.create_oval(475 if active else 447,247,495 if active else 467,264,fill=TEXT if eco else MUTED,outline="")
        if eco:hit((283,231,515,279),lambda:self.staged("ecoMode","0" if active else "1"))
        if not eco:text(400,287,"Unavailable",8,MUTED,"center")
        values=[float(v) for v in self.selected.get("temperatures",[])]
        for x,symbol in ((28,"−"),(490,"+")):
            step=c.create_oval(x-23,304,x+23,350,fill=CARD,outline="")
            if values:hover((x-23,304,x+23,350),step)
            text(x,327,symbol,22,ACCENT,"center")
            if values:hit((x-23,304,x+23,350),lambda direction=(-1 if x==28 else 1):self.step_temp(direction))
        slider=rounded(c,68,305,449,349,12,fill="#141713",outline="#252b22")
        if values:hover((68,305,449,349),slider,fill="#141713",outline="#252b22")
        if values:
            try:ratio=(float(self.temp.get())-min(values))/(max(values)-min(values)) if max(values)!=min(values) else 0
            except ValueError:ratio=0
            tx=79+max(0,min(1,ratio))*358
            rounded(c,69,306,max(89,tx+12),348,11,fill="#777560",outline="")
            rounded(c,tx-12,308,tx+12,346,7,fill="#d8d8c9",outline="")
            text(68,366,f"{min(values):g}°",9,MUTED)
            text(449,366,f"{max(values):g}°",9,MUTED,"e")
            hit((68,305,449,349),self.slider_from_event)
        mode_glyph=mode_icon(self.mode.get())
        cards=[("Mode",self.mode.get(),mode_glyph,lambda:self.choice_menu("machMode")),("Fan speed",self.fan.get(),"fan",lambda:self.choice_menu("windSpeed")),("Sleep",self.toggle_label("silentSleepStatus"),"moon",lambda:self.choice_menu("silentSleepStatus")),("Airflow",self.airflow_label(),"wind",self.airflow_menu)]
        for i,(label,value,glyph,fn) in enumerate(cards):
            x=6+i*130
            card=control_card(c,x,393,122,label,value,glyph)
            if value!="Unavailable":hover((x,393,x+122,494),card)
            hit((x,393,x+122,494),fn)
        text(8,521,("●  Changes pending" if self.dirty else "●  "+self.selected["power"]),9,ACCENT if self.dirty else GREEN)
        all_link=text(510,521,"All functions  ↗",10,MUTED,"e")
        self.canvas_hover.add((375,501,515,539),all_link,{"fill":MUTED},{"fill":TEXT})
        hit((375,501,515,539),self.open_functions)
        if s!=1:c.scale("all",0,0,s,s)
        self.canvas.configure(height=int(540*s))
        self.airflow.set_state(self.selected,260,144,275,47,s)
        self.canvas_hover.update()
        if self.busy:
            self.hits=[]

    def click(self,event):
        if self.busy:return
        self.canvas.focus_set()
        s=max(self.canvas.winfo_width(),480)/520
        x,y=event.x/s,event.y/s
        for (x1,y1,x2,y2),fn in self.hits:
            if x1<=x<=x2 and y1<=y<=y2:
                if fn==self.slider_from_event:fn(event)
                else:fn()
                break

    def slider_from_event(self,event):
        values=[float(v) for v in self.selected["temperatures"]]
        s=max(self.canvas.winfo_width(),480)/520
        ratio=max(0,min(1,(event.x/s-79)/358))
        self.staged("tempSel",min(values,key=lambda v:abs(v-(min(values)+ratio*(max(values)-min(values))))))

    def drag_temperature(self,event):
        s=max(self.canvas.winfo_width(),480)/520
        if not self.busy and self.selected and self.selected["temperatures"] and 305<=event.y/s<=349 and 68<=event.x/s<=449:
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
            self.connection.set("◇ Status unavailable · Retrying automatically")
            self.schedule_auto(min(60000,15000 * 2**min(self.auto_failures,2)))
        self.worker.submit(self.worker.controller.refresh(device_id),done,"auto-refresh",on_error=failed)

    def action(self,action,requested=None):
        if self.busy or not self.selected:return
        if self.demo:
            self.status.set("Design preview only. No command sent.");return
        if requested is None:requested={} if action=="off" else dict(self.dirty)
        if action=="on":requested=self.memory.mode_values(self.selected,requested)
        if action=="apply":action="configure"
        self.set_busy(True)
        self.status.set("Sending changes to the cloud service…")
        def done(text):
            self.dirty={}
            self.status.set(text)
            self.set_busy(False)
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

    def field(self,parent,spec,override=None,use_reported=False):
        row=ttk.Frame(parent,padding=(0,7))
        row.pack(fill="x")
        label=spec["label"]
        value=override if override is not None else (spec["value"] if not use_reported or spec.get("reported") else "")
        ttk.Label(row,text=label).pack(side="left")
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
        else:
            variable=tk.StringVar(value=f"{float(value):g}" if value!="" else "")
            widget=ttk.Spinbox(row,textvariable=variable,from_=spec["min"],to=spec["max"],increment=spec["step"],width=20)
            getter=lambda:variable.get() or None
        widget.pack(side="right")
        if use_reported and value=="":
            ttk.Label(parent,text="Current value not reported",style="Muted.TLabel",font=("Segoe UI",8)).pack(anchor="e")
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
            self.airflow.set_state(None,260,144,275,47)
            self.panel.pack_forget()
            self.login_frame.pack(fill="x",pady=(5,0),before=self.status_label)
            self.remember_account.set(False)
            self.status.set("Signed out.")
            self.set_busy(False)
        self.worker.submit(self.worker.controller.close(),done,"logout")

    def close(self):
        if self.closing:return
        self.closing=True
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
        self.status.set("An interface action failed. You can export diagnostics for troubleshooting.")

    def export_diagnostics(self):
        destination=filedialog.asksaveasfilename(parent=self.root, title="Save diagnostics",
                initialfile="room-ac-diagnostics.json", defaultextension=".json", filetypes=[("JSON report","*.json")])
        if destination:
            try:diagnostics.export(Path(destination))
            except OSError:self.status.set("Could not save the diagnostic report. Choose a writable folder.")
