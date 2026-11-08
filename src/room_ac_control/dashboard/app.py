"""The dashboard window: sign-in, device state, refresh, commands and the tray."""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import __version__, updates
from ..airflow import AirflowAnimation
from ..button_theme import configure_styles
from ..canvas_hover import CanvasHover
from ..controller import mode_label
from ..device_picker import DevicePicker, PowerButton
from ..diagnostics import diagnostics
from ..i18n import (
    TranslatedVariable,
    Translator,
    localized_title,
    refresh_on_language,
    tr,
)
from ..inline_timers import InlineTimers
from ..program_memory import ProgramMemory
from ..secure_state import SecureState
from ..smooth import aa_text
from ..theme import (
    ASSETS,
    THEMES,
    C,
    font,
    icon,
    measure,
    paint,
    refresh_on_theme,
    resolve_theme,
    unit_photo,
)
from ..widgets import PillButton, Toast, UpdateNotice
from ..worker import Worker
from .canvas import CanvasMixin
from .controls import ControlsMixin
from .layout import (
    CANVAS_HEIGHT,
    FLOW,
    UNIT,
    WIDTH,
    WINDOW_SIZE,
    equal,
)
from .preferences import PreferencesMixin
from .schedule_actions import ScheduleActionsMixin


class App(PreferencesMixin, CanvasMixin, ControlsMixin, ScheduleActionsMixin):
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
        self.instance = None  # The single-instance lock, set by main().
        self.worker = Worker(memory=self.memory)
        self.tray = None
        self.closing = False
        if enable_tray and not demo:
            try:
                from ..tray import SystemTray

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
        localized_title(root, "Room AC Control for hOn" + (" · Design preview" if demo else ""))
        root.geometry("{}x{}".format(*WINDOW_SIZE))
        root.resizable(False, False)
        paint(root, bg="BG")
        configure_styles(root)
        from ..window_header import HeaderPillButton, WindowHeader

        self.header = WindowHeader(
            root, "Room AC Control", self.close, self.minimize_window, maximize=False, size=WINDOW_SIZE
        )
        # Appearance, language, updates and sign-out live in one Settings panel;
        # a dot marks a signed update waiting to install.
        self.settings_button = HeaderPillButton(self.header.frame, "gear", "Settings", self.open_settings)
        self.settings_button.pack(side="right", padx=(0, 6))
        location = None if demo else updates.install_location()
        self.updater = updates.Updater(__version__, location, enabled=self.storage.auto_update(), demo=demo)
        self.updater.listen(self.updates_changed)
        if location is not None:
            try:
                self.update_notice = updates.finish(location, __version__)
            except OSError as error:
                diagnostics.record("update_failed", error)
        self.content = ttk.Frame(root)
        self.content.pack(fill="both", expand=True)
        self.body = ttk.Frame(self.content, padding=(20, 0, 20, 20))
        self.body.pack(fill="both", expand=True)
        from ..login_view import LoginView

        self.login_view = LoginView(self)
        self.login_frame = self.login_view.frame
        self.login_frame.pack(fill="x", pady=(5, 0))
        self.panel = ttk.Frame(self.body)
        top = ttk.Frame(self.panel)
        top.pack(fill="x", pady=(0, 4))
        self.power_button = PowerButton(top, self.toggle_power)
        self.power_button.pack(side="right", padx=(8, 0))
        self.device_picker = DevicePicker(top, self.select_device)
        self.device_picker.pack(side="left", fill="x", expand=True)
        self.canvas = paint(tk.Canvas(self.panel, highlightthickness=0, height=CANVAS_HEIGHT), bg="BG")
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self.draw())
        refresh_on_language(self.canvas, self.draw)
        refresh_on_theme(self.canvas, self.draw)
        self.canvas_hover = CanvasHover(self.canvas)
        self.airflow = AirflowAnimation(self.canvas)
        self.inline_timers = InlineTimers(self)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<B1-Motion>", self.drag_temperature)
        self.canvas.bind("<ButtonRelease-1>", self.release_dial)
        self.canvas.bind("<MouseWheel>", self.wheel_temperature)
        for key, direction in (("<Left>", -1), ("<Right>", 1), ("<Down>", -1), ("<Up>", 1)):
            self.canvas.bind(
                key,
                lambda e, direction=direction: self.step_temp(direction) if not self.busy and self.selected else None,
            )
        # Main selectors retain Tk variables for menu and keyboard support.
        self.mode, self.temp, self.fan = tk.StringVar(), tk.StringVar(), tk.StringVar()
        # The action row: All functions and Refresh on the left; Discard and Apply, or
        # "In sync with the AC", on the right.
        controls = ttk.Frame(self.panel)
        controls.pack(side="bottom", fill="x")
        self.all_button = PillButton(
            controls, "All functions", self.open_functions, glyph="grid", hover_when=self.ac_on
        )
        self.all_button.pack(side="left")
        self.refresh_button = PillButton(controls, "", self.refresh, glyph="refresh", width=48, hover_when=self.ac_on)
        self.refresh_button.pack(side="left", padx=(8, 0))
        self.apply_button = PillButton(
            controls,
            "Apply",
            lambda: self.action("apply"),
            kind="accent",
            size=-14,
            tone=self.dial_accent,
            hover_when=self.ac_on,
        )
        self.discard_button = PillButton(controls, "Discard", self.discard, kind="ghost", hover_when=self.ac_on)
        self.sync_label = tk.Canvas(controls, height=48, highlightthickness=0)
        self.sync_label.bind("<Configure>", lambda event: self.draw_sync())
        refresh_on_theme(self.sync_label, self.draw_sync)
        refresh_on_language(self.sync_label, self.draw_sync)
        self.update_apply_label()
        # The connection line is shown under the room name.
        self.connection = tk.StringVar()
        self.connection.trace_add("write", lambda *args: self.paint_connection())
        self.status = tk.StringVar(value="Sign in to connect to your air conditioner.")
        self.status_display = TranslatedVariable(root, self.status)
        self.status_label = tk.Label(
            self.body,
            textvariable=self.status_display,
            font=font(9),
            anchor="w",
            justify="left",
            padx=12,
            pady=6,
            wraplength=480,
            bd=0,
        )
        paint(self.status_label, bg="SOFT", fg="ON_SOFT")
        self.status_label.pack(fill="x", pady=(8, 0))
        self.status_label.bind(
            "<Configure>", lambda event: self.status_label.configure(wraplength=max(1, event.width - 24))
        )
        # Signed in, messages appear briefly above the action row instead.
        self.toast = Toast(root)
        self.update_notice_bar = UpdateNotice(self)
        self.status.trace_add("write", lambda *args: self.status_changed())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self.callback_failed
        self.root.bind("<Unmap>", self.on_minimize, add="+")
        self.poll_job = root.after(100, self.poll)
        if not demo:
            root.after(200, self.auto_sign_in)
        if self.update_notice:
            self.status.set(self.update_notice)
        if self.updater.supported:
            self.update_job = root.after(updates.FIRST_CHECK_MS, self.auto_check_updates)

    def poll(self):
        if self.closing:
            return
        try:
            while True:
                callback, value, error, operation = self.worker.results.get_nowait()
                if operation != "auto-refresh":
                    self.set_busy(False)
                if error:
                    if operation in {"auto-refresh", "login", "timer", "schedule", "schedule-list"}:
                        callback(error)
                    else:
                        self.status.set(error)
                        messagebox.showerror("Room AC Control", tr(self.root, error), parent=self.root)
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
                    event = self.tray.events.get_nowait()
                    if event == "ready":
                        self.tray.ready = True
                        if self.root.state() == "iconic":
                            self.minimize_to_tray()
                    elif event == "restore":
                        self.restore_window()
                    elif event == "exit":
                        self.close()
                        return
            except queue.Empty:
                pass
        if self.instance and self.instance.show_requested():
            self.restore_window()
        self.updater.poll()
        # Follow Windows: notice an app-mode switch within about two seconds.
        self.theme_checks += 1
        if self.theme_checks >= 20:
            self.theme_checks = 0
            if self.theme_preference == "system":
                self.apply_theme()
        self.poll_job = self.root.after(100, self.poll)

    def update_apply_label(self):
        """Discard and Apply (with a count) while edits wait; otherwise "In sync with the AC"."""
        count = len(self.dirty)
        self.apply_button.set_badge(count if count else None)
        if count:
            self.sync_label.pack_forget()
            if not self.apply_button.winfo_manager():
                self.apply_button.pack(side="right")
                self.discard_button.pack(side="right", padx=(0, 4))
        else:
            self.apply_button.pack_forget()
            self.discard_button.pack_forget()
            if not self.sync_label.winfo_manager():
                self.sync_label.pack(side="right", fill="x", expand=True)

    def draw_sync(self):
        c = self.sync_label
        c.delete("all")
        c.configure(bg=C.BG)
        width = max(c.winfo_width(), 1)
        label = tr(c, "In sync with the AC")
        right = width - 4
        aa_text(c, right, 24, text=label, anchor="e", fill=C.MUTED, font=font(-12, "semibold"))
        icon(c, "check", right - measure(c, label, -12, "semibold") - 12, 24, C.MUTED, scale=0.6, bg=C.BG)

    QUIET = {
        "Changes ready. Apply them, or use the power button to turn on.",
        "No pending changes.",
        "Connected. Select changes, then apply.",
        "Design preview · No AC commands are sent.",
        "Status retrieved from the cloud service.",
        "Refreshing reported AC status…",
    }

    def status_changed(self):
        """Show a dashboard message as a toast; routine confirmations stay quiet."""
        message = self.status.get()
        if not self.panel.winfo_ismapped() or not message or message in self.QUIET:
            return
        bottom = self.content.winfo_y() + self.body.winfo_y() + self.panel.winfo_y() + self.panel.winfo_height() - 58
        self.toast.show(tr(self.root, message), bottom)

    def paint_connection(self):
        text = self.connection.get()
        self.device_picker.set_status(text, text.startswith("Connected"))

    def discard(self):
        """Drop staged edits and show the reported (or awaiting) values again."""
        if self.busy or not self.selected or not self.dirty:
            return
        self.dirty = {}
        self.show_device(self.selected)
        self.status.set("Changes discarded.")

    def set_busy(self, value):
        self.busy = value
        state = "disabled" if value else "normal"
        for widget in (self.email, self.password, self.login_button):
            widget.configure(state=state)
        available = self.selected is not None and not value
        for widget in (self.refresh_button, self.all_button, self.discard_button):
            widget.set_enabled(available)
        self.apply_button.set_enabled(available and bool(self.dirty))
        self.update_apply_label()
        self.device_picker.set_enabled(available)
        self.power_button.set_state(
            self.selected is not None and self.selected["power"] == "On",
            available,
            self.mode.get() if self.selected else None,
        )
        self.draw()

    def connect(self):
        if self.busy:
            return
        email, password = self.email.get().strip(), self.password.get()
        if not email or not password:
            self.status.set("Enter your cloud account email and password.")
            return
        self.password.delete(0, "end")
        self.sign_in(email, password)

    def auto_sign_in(self):
        if self.closing or self.busy or self.selected:
            return
        login = self.storage.credentials()
        if login:
            # Existing saved accounts retain their previously chosen auto sign-in.
            self.remember_account.set(True)
            self.email.delete(0, "end")
            self.email.insert(0, login[0])
            self.sign_in(*login, automatic=True)
        elif self.storage.load_error:
            self.status.set("Saved sign-in could not be decrypted. Sign in again to replace it.")

    def sign_in(self, email, password, automatic=False):
        if self.closing or self.busy:
            return
        self.set_busy(True)
        self.login_view.set_loading(True, automatic)
        self.status.set("Signing in with your saved account…" if automatic else "Connecting to the cloud service…")

        def done(devices):
            persistence_error = False
            try:
                if self.remember_account.get():
                    self.storage.save_credentials(email, password)
                else:
                    self.storage.forget_credentials()
            except OSError as error:
                diagnostics.record("credential_save_failed", error)
                persistence_error = True
            self.connected(devices)
            if persistence_error:
                self.status.set("Connected, but Windows could not save the encrypted sign-in.")

        def failed(error):
            self.login_view.set_loading(False)
            self.set_busy(False)
            self.status.set(("Automatic sign-in failed. " if automatic else "") + error)

        self.worker.submit(self.worker.controller.connect(email, password), done, "login", on_error=failed)

    def connected(self, devices):
        self.login_view.set_loading(False)
        if self.demo and not self.memory.account:
            self.memory.use_account("preview@example.test")
        self.reset_auto()
        self.devices = devices
        self.login_frame.pack_forget()
        self.panel.pack(fill="both", expand=True)
        self.status_label.pack_forget()
        self.device_picker.set_devices(devices)
        index = 0
        self.device_picker.current(index)
        self.show_device(devices[index])
        self.status.set(
            "Design preview · No AC commands are sent." if self.demo else "Connected. Select changes, then apply."
        )
        if self.update_notice:
            self.status.set(self.update_notice)
            self.update_notice = None
        self.schedule_auto()

    def show_device(self, device, preserve_edits=False):
        pending = dict(self.dirty) if preserve_edits else {}
        self.selected = device
        self.devices[self.device_picker.current()] = device
        self.dirty = pending
        self.pending_changes = dict(device.get("pending_changes", {}))
        displayed = {**self.pending_changes, **pending}
        self.mode.set(mode_label(device, displayed))
        fan_value = displayed.get("windSpeed", device.get("controls", {}).get("windSpeed", {}).get("value"))
        self.fan.set(next((label for label, value in device["fans"].items() if equal(value, fan_value)), device["fan"]))
        self.temp.set(displayed.get("tempSel", str(device["target"]) if device["target"] is not None else ""))
        state = device.get("connection", "Unknown")
        label = (
            "Connected"
            if state == "CONNECTED"
            else ("Disconnected" if state == "DISCONNECTED" else "Connection unknown")
        )
        self.connection.set(f"{label} · {device['fetched']}" + (" · Auto" if not self.demo else ""))
        if device.get("confirmation_expired"):
            self.status.set(
                "The cloud has not confirmed the changes. Showing reported status; check hOn before retrying."
            )
        self.set_busy(self.busy if preserve_edits else False)
        if self.dialog and self.dialog.winfo_exists():
            self.dialog_view.refresh_status()

    def select_device(self, event=None):
        if not self.busy:
            self.reset_auto()
            self.selected = self.devices[self.device_picker.current()]
            self.dirty = {}
            self.pending_changes = {}
            self.refresh()

    def staged(self, key, value):
        if self.busy:
            return
        spec = self.selected.get("controls", {}).get(key)
        if spec and spec.get("reported") and equal(value, self.pending_changes.get(key, spec["value"])):
            self.dirty.pop(key, None)
        else:
            self.dirty[key] = str(value)
        if key in {"machMode", "silentSleepStatus"}:
            self.mode.set(mode_label(self.selected, {**self.pending_changes, **self.dirty}))
        if key == "windSpeed":
            self.fan.set(next((label for label, v in self.selected["fans"].items() if equal(v, value)), "Other"))
        if key == "tempSel":
            self.temp.set(str(value))
        self.status.set(
            "Changes ready. Apply them, or use the power button to turn on." if self.dirty else "No pending changes."
        )
        self.set_busy(False)

    def current(self, key):
        if key in self.dirty:
            return self.dirty[key]
        if key in self.pending_changes:
            return self.pending_changes[key]
        spec = self.selected.get("controls", {}).get(key)
        return spec.get("value") if spec and spec.get("reported") else None

    def refresh(self):
        if self.busy or not self.selected:
            return
        if self.demo:
            self.show_device(self.selected)
            self.status.set("Preview refreshed. No network connection.")
            return
        self.set_busy(True)
        self.status.set("Refreshing reported AC status…")

        def done(device):
            self.show_device(device, preserve_edits=True)
            if not device.get("confirmation_expired"):
                self.status.set("Status retrieved from the cloud service.")
            self.schedule_auto()

        self.worker.submit(self.worker.controller.refresh(self.selected["id"]), done, "refresh")

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
            if not valid():
                return
            self.auto_inflight = False
            self.auto_failures = 0
            self.show_device(device, preserve_edits=True)
            self.schedule_auto(750 if self.auto_pending else 15000)

        def failed(error):
            if not valid():
                return
            self.auto_inflight = False
            self.auto_failures += 1
            self.connection.set("Status unavailable · Retrying automatically")
            self.schedule_auto(min(60000, 15000 * 2 ** min(self.auto_failures, 2)))

        self.worker.submit(self.worker.controller.refresh(device_id), done, "auto-refresh", on_error=failed)

    def action(self, action, requested=None):
        if self.busy or not self.selected:
            return
        if self.demo:
            self.status.set("Design preview only. No command sent.")
            return
        if requested is None:
            requested = {} if action == "off" else dict(self.dirty)
        if action == "on":
            requested = self.memory.mode_values(self.selected, requested)
        if action == "apply":
            action = "configure"
        # Results requested before this command must not overwrite its selection.
        self.refresh_epoch += 1
        self.auto_inflight = False
        self.set_busy(True)
        self.status.set("Sending changes to the cloud service…")

        def done(text):
            if action in {"on", "configure"}:
                self.pending_changes.update(
                    {key: str(value) for key, value in requested.items() if key in self.selected.get("controls", {})}
                )
            else:
                self.pending_changes = {}
            self.dirty = {}
            self.set_busy(False)
            device = {**self.selected, "pending_changes": dict(self.pending_changes)}
            device.pop("confirmation_expired", None)
            self.show_device(device, preserve_edits=True)
            self.status.set(text)
            # Allow the unit time to acknowledge; do not present optimistic state as confirmed.
            self.schedule_auto(12000)

        self.worker.submit(self.worker.controller.action(self.selected["id"], action, requested), done, "command")

    def logout(self):
        if self.busy:
            return
        if self.demo:
            return
        try:
            self.storage.forget_credentials()
        except OSError:
            self.status.set("Could not remove saved sign-in. Check access to the app's data folder.")
            return
        self.reset_auto()
        self.set_busy(True)

        def done(value):
            self.selected = None
            self.devices = []
            self.dirty = {}
            self.airflow.set_state(None, WIDTH / 2, *FLOW)
            self.toast.hide()
            self.panel.pack_forget()
            self.login_frame.pack(fill="x", pady=(5, 0))
            self.status_label.pack(fill="x", pady=(8, 0))
            self.remember_account.set(False)
            self.status.set("Signed out.")
            self.set_busy(False)

        self.worker.submit(self.worker.controller.close(), done, "logout")

    def close(self):
        if self.closing:
            return
        self.closing = True
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
            try:
                self.tray.close()
            except Exception as error:
                diagnostics.record("tray_close_failed", error)
        self.worker.close()
        if self.instance:
            self.instance.close()
        self.root.destroy()

    def on_minimize(self, event):
        if event.widget is self.root and not self.closing and self.root.state() == "iconic":
            self.root.after(50, self.minimize_to_tray)

    def minimize_window(self):
        if not self.closing:
            self.root.iconify()

    def minimize_to_tray(self):
        if not self.closing and self.tray and self.root.state() == "iconic" and self.tray.show():
            self.root.withdraw()

    def restore_window(self):
        if self.closing:
            return
        if self.tray:
            try:
                self.tray.hide()
            except Exception as error:
                diagnostics.record("tray_hide_failed", error)
        self.root.deiconify()
        self.root.lift()
        active = self.root.grab_current()
        if active and active.winfo_exists():
            active.deiconify()
            active.lift()
            active.focus_force()
        else:
            self.root.focus_force()

    def callback_failed(self, kind, error, traceback):
        diagnostics.record("ui_callback_failed", error)
        if self.login_view.loading:
            self.login_view.set_loading(False)
            self.set_busy(False)
        self.status.set("An interface action failed. You can export diagnostics for troubleshooting.")

    def export_diagnostics(self):
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr(self.root, "Save diagnostics"),
            initialfile="room-ac-diagnostics.json",
            defaultextension=".json",
            filetypes=[(tr(self.root, "JSON report"), "*.json")],
        )
        if destination:
            try:
                diagnostics.export(Path(destination))
            except OSError:
                self.status.set("Could not save the diagnostic report. Choose a writable folder.")
