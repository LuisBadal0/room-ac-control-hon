"""The dashboard window: sign-in, device state, refresh, commands and the tray."""

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .. import __version__, updates
from ..ac_model import turbo_conflicts
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
from ..room_history import RoomHistory
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
    UNIT,
    WINDOW_SIZE,
    equal,
)
from .preferences import PreferencesMixin
from .schedule_actions import ScheduleActionsMixin
from .session import SessionMixin
from .status import StatusMixin
from .window import WindowMixin


class App(SessionMixin, StatusMixin, WindowMixin, PreferencesMixin, CanvasMixin, ControlsMixin, ScheduleActionsMixin):
    def __init__(self, root, demo=False, state=None, enable_tray=True, language=None, theme=None):
        self.root, self.demo = root, demo
        self.storage = state if state is not None else SecureState(persistent=not demo)
        self.i18n = root.i18n = Translator(self.storage.language() if language is None else language)
        self.theme_preference = self.storage.theme() if theme is None else (theme if theme in THEMES else "system")
        C.use(resolve_theme(self.theme_preference))
        self.theme_checks = 0
        self.memory = ProgramMemory(self.storage, RoomHistory(persistent=not demo))
        self.preview_timers = {}
        self.preview_records = {}  # Fictional schedules for the offline preview.
        self.schedules_view = None
        self.updates_view = None
        self.update_job = None
        self.update_notice = None
        self.instance = None  # The single-instance lock, set by main().
        self.worker = Worker(memory=self.memory)
        self.tray = None
        self.tray_menu = None  # The open notification-area menu, if any.
        self.closing = False
        # Windows notifications from the tray: the last snapshot seen per AC, and until when
        # power changes come from this app's own command.
        self.notifications = self.storage.notifications()
        self.last_seen = {}
        self.own_change_until = {}
        if enable_tray and not demo:
            try:
                from ..tray import SystemTray

                self.tray = SystemTray(self.i18n)
            except Exception as error:
                diagnostics.record("tray_start_failed", error)
        self.devices, self.selected = [], None
        self.busy, self.dirty = False, {}
        self.turbo_staged: dict[str, dict[str, str]] = {}
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
        # The multi-size .ico, not a single large photo: Windows shrinks one big
        # image crudely, which blurs the taskbar and title-bar icons.
        root.iconbitmap(default=str(ASSETS / "app.ico"))
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
        self.status.trace_add("write", lambda *args: self.login_view.draw_card())
        # Before sign-in, messages show inside the sign-in card (login_view).
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

    # Loads that run beside a command. Their results must not unlock the controls.
    BACKGROUND = {"auto-refresh", "routine-history", "schedule-list", "energy"}

    def poll(self):
        if self.closing:
            return
        try:
            self.handle_events()
        finally:
            # Keep polling whatever happened: one failing callback must not stop cloud
            # results, the tray, a second start and update progress from being handled.
            if not self.closing:
                self.poll_job = self.root.after(100, self.poll)

    def show_error(self, text):
        self.status.set(text)
        messagebox.showerror("Room AC Control", tr(self.root, text), parent=self.root)

    def handle_events(self):
        try:
            while True:
                callback, value, error, operation = self.worker.results.get_nowait()
                if operation not in self.BACKGROUND:
                    self.set_busy(False)
                if not error:
                    callback(value)
                elif callback is not None:
                    callback(error)  # The operation has its own error handler.
                else:
                    self.show_error(error)
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
        if self.handle_tray_events():
            return
        if self.instance and self.instance.show_requested():
            self.restore_window()
        self.updater.poll()
        # Follow Windows: notice an app-mode switch within about two seconds.
        self.theme_checks += 1
        if self.theme_checks >= 20:
            self.theme_checks = 0
            if self.theme_preference == "system":
                self.apply_theme()

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

    def set_busy(self, value):
        self.busy = value
        self.login_view.set_enabled(not value)
        available = self.selected is not None and not value
        for widget in (self.refresh_button, self.all_button, self.discard_button):
            widget.set_enabled(available)
        self.apply_button.set_enabled(available and bool(self.dirty))
        self.update_apply_label()
        self.device_picker.set_enabled(available)
        self.update_tray()
        self.power_button.set_state(
            self.selected is not None and self.selected["power"] == "On",
            available,
            self.mode.get() if self.selected else None,
        )
        self.draw()

    def show_device(self, device, preserve_edits=False):
        self.notify_changes(device)
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
        """Stage one setting the user chose."""
        self.stage_patch({key: value}, cause=key)

    def stage_patch(self, patch, cause=None):
        """Stage settings chosen together, such as a mode with its remembered settings.

        Turbo's rule follows only `cause`, the setting the user picked. Settings restored
        from a mode's memory are staged as saved, so a mode never turns Turbo off by itself.
        """
        if self.busy or not patch:
            return
        if not self.dirty:
            self.turbo_staged.clear()  # A new draft: nothing staged earlier can be undone.
        before = self.current(cause) if cause in patch else None
        for key, value in patch.items():
            self.stage_value(key, value)
        notice = None
        if cause in patch and not (cause == "windSpeed" and equal(before, patch[cause])):
            conflicts, notice = turbo_conflicts(cause, patch[cause], self.current, self.selected.get("controls", {}))
            for name, off in conflicts.items():
                self.stage_value(name, off)
            if conflicts:
                self.turbo_staged.setdefault(cause, {}).update(conflicts)
        self.status.set(
            notice
            or (
                "Changes ready. Apply them, or use the power button to turn on."
                if self.dirty
                else "No pending changes."
            )
        )
        self.set_busy(False)

    def stage_value(self, key, value):
        spec = self.selected.get("controls", {}).get(key)
        if spec and spec.get("reported") and equal(value, self.pending_changes.get(key, spec["value"])):
            if self.dirty.pop(key, None) is not None:
                # Back to what the AC reports: undo the switches Turbo's rule turned off for it.
                for name, off in self.turbo_staged.pop(key, {}).items():
                    if self.dirty.get(name) == off:
                        self.dirty.pop(name)
                        self.show_staged(name, self.current(name))
        else:
            self.dirty[key] = str(value)
        self.show_staged(key, value)

    def show_staged(self, key, value):
        if key in {"machMode", "silentSleepStatus"}:
            self.mode.set(mode_label(self.selected, {**self.pending_changes, **self.dirty}))
        if key == "windSpeed":
            self.fan.set(next((label for label, v in self.selected["fans"].items() if equal(v, value)), "Other"))
        if key == "tempSel":
            self.temp.set(str(value))

    def current(self, key):
        if key in self.dirty:
            return self.dirty[key]
        if key in self.pending_changes:
            return self.pending_changes[key]
        spec = self.selected.get("controls", {}).get(key)
        return spec.get("value") if spec and spec.get("reported") else None
