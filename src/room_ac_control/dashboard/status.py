"""Reported status: manual and automatic refresh, and sending commands."""

import time


class StatusMixin:
    def discard(self):
        """Drop staged edits and show the reported (or awaiting) values again."""
        if self.busy or not self.selected or not self.dirty:
            return
        self.dirty = {}
        self.show_device(self.selected)
        self.status.set("Changes discarded.")

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
        # The AC turning on or off in the next minutes is this command, not news.
        self.own_change_until[self.selected["id"]] = time.monotonic() + 180
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
