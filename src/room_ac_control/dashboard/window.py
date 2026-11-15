"""The window and the notification-area icon: minimize, restore, close and failures."""

import queue
from pathlib import Path
from tkinter import filedialog

from ..diagnostics import diagnostics
from ..i18n import (
    tr,
)


class WindowMixin:
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
