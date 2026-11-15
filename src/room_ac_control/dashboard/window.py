"""The window and the notification-area icon: minimize, restore, close and failures."""

import queue
from pathlib import Path
from tkinter import filedialog

from ..diagnostics import diagnostics
from ..i18n import (
    tr,
)


class WindowMixin:
    def notify_changes(self, device):
        """Announce what the AC reports while the window waits in the notification area."""
        import time

        from ..notifier import changes, text

        previous = self.last_seen.get(device["id"])
        self.last_seen[device["id"]] = device
        hidden = self.root.state() == "withdrawn"
        if not (self.notifications and self.tray and hidden and previous):
            return
        own = time.monotonic() < self.own_change_until.get(device["id"], 0)
        for notification in changes(previous, device, own_power_change=own):
            self.tray.notify(*text(self.i18n, notification))

    def tray_presets(self):
        """The top presets from Everyday use, as (key, label) for the tray menu."""
        from ..functions_view.model import everyday_layout, preset_key, section_items

        items = [dict(item, section="everyday") for item in section_items(self.selected, "everyday")]
        modes = {preset_key(option) for option in self.mode_options()}
        top = everyday_layout(items, modes, self.memory.top_presets(self.selected["id"]))[1]
        return {preset_key(item): item for item in top}

    def update_tray(self):
        """Give the tray menu the selected AC's name, reading, power, Eco and top presets."""
        if not self.tray:
            return
        if not self.selected:
            self.tray.set_state({})
            return
        from ..controller import code, mode_label

        device = self.selected
        parts = [device["name"]]
        try:
            parts.append(self.i18n.number(f"{float(device['room']):.1f}") + "°")
        except (TypeError, ValueError):
            pass
        parts.append(tr(self.root, mode_label(device) if device["power"] == "On" else "Off"))
        eco = device.get("controls", {}).get("ecoMode")
        presets = self.tray_presets()
        self.tray.set_state(
            {
                "summary": " · ".join(parts),
                "power": device["power"],
                "eco": (code(eco["value"]) == "1") if eco and eco.get("reported") else None,
                "presets": [(key, tr(self.root, item["label"])) for key, item in presets.items()],
                "busy": self.busy,
            }
        )

    def tray_action(self, event):
        """A quick action chosen in the tray menu: the same commands as the window sends."""
        if self.busy or not self.selected:
            return
        kind = event[0]
        if kind == "power":
            # Turning on uses the mode's remembered settings, not edits staged in the window.
            self.action("off", {}) if self.selected["power"] == "On" else self.action("on", {})
        elif kind == "eco" and self.selected["power"] == "On":
            from ..controller import code

            eco = self.selected.get("controls", {}).get("ecoMode")
            if eco:
                self.action("apply", {"ecoMode": "0" if code(eco["value"]) == "1" else "1"})
        elif kind == "preset":
            from ..functions_view.preset_sheet import preset_request

            item = self.tray_presets().get(event[1])
            if item:
                self.action(*preset_request(self, item))

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

    def handle_tray_events(self):
        """Act on notification-area menu choices; True once the app is closing."""
        if not self.tray:
            return False
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
                    return True
                elif isinstance(event, tuple):
                    self.tray_action(event)
                elif event in {"power", "eco"}:
                    self.tray_action((event,))
        except queue.Empty:
            pass
        return False

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
