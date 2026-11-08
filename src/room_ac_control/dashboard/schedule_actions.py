"""All functions, End at timers and repeating schedules, saved through the worker."""

from datetime import UTC
from tkinter import messagebox

from ..choice_widgets import ChoicePanel
from ..i18n import (
    tr,
)


class ScheduleActionsMixin:
    def open_functions(self):
        if self.busy or not self.selected:
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        from ..functions_view import FunctionsView

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

            self.worker.submit(
                self.worker.controller.change_timer(device_id, action, due, item.get("expected"), requested),
                done,
                "timer",
                on_error=failed,
            )
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
        from ..schedules_view import SchedulesView

        SchedulesView(self, parent)

    def preview_rows(self):
        from ..schedules import schedule_rows

        return schedule_rows({"scheduledPrograms": self.preview_records.get(self.selected["id"], [])})

    def load_routine_history(self, done, failed):
        """Maintenance routine starts from hOn's recent command history ({routine: datetime})."""
        if self.demo:
            from datetime import datetime, timedelta

            done({"selfCleaningStatus": datetime.now(UTC) - timedelta(days=12, hours=3)})
            return
        device_id = self.selected["id"]
        self.worker.submit(self.worker.controller.routine_history(device_id), done, "routine-history", on_error=failed)

    def load_schedules(self, done, failed):
        if self.demo:
            done(self.preview_rows())
            return
        device_id = self.selected["id"]
        self.worker.submit(self.worker.controller.schedule_list(device_id), done, "schedule-list", on_error=failed)

    def confirm_conflict(self, found, parent):
        from ..schedules import clock_text, day_labels

        item = found[0]
        days = ", ".join(tr(self.root, label) for label in day_labels(item["days"]))
        message = f"This overlaps another schedule at {clock_text(item['time'])} on {days}. Save anyway?"
        return messagebox.askyesno("Room AC Control", tr(self.root, message), parent=parent)

    def save_schedule(
        self, ident, start, end, days, requested, done, failed, parent=None, cancelled=None, allow_conflict=False
    ):
        """Create or edit a repeating schedule, asking before saving over an overlap."""
        parent = parent or self.root
        if self.demo:
            from ..controller import ControlError
            from ..schedules import conflicts, preview_record

            rows = self.preview_rows()
            found = conflicts(rows, start, end, days, ignore=ident)
            if found and not allow_conflict and not self.confirm_conflict(found, parent):
                if cancelled:
                    cancelled()
                return
            records = self.preview_records.setdefault(self.selected["id"], [])
            try:
                record = preview_record(ident or f"preview-{len(records) + 1}", start, end, days, requested)
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
                    self.save_schedule(
                        ident, start, end, days, requested, done, failed, parent, cancelled, allow_conflict=True
                    )
                elif cancelled:
                    cancelled()
                return
            if self.selected and self.selected["id"] == device_id:
                self.show_device(result["snapshot"], preserve_edits=True)
            done(result["rows"])

        self.worker.submit(
            self.worker.controller.change_schedule(
                device_id,
                "save",
                ident=ident,
                start=start,
                end=end,
                days=days,
                requested=requested,
                allow_conflict=allow_conflict,
            ),
            finished,
            "schedule",
            on_error=failed,
        )

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

        self.worker.submit(
            self.worker.controller.change_schedule(device_id, operation, **options),
            finished,
            "schedule",
            on_error=failed,
        )

    def timer_repeat_menu(self, card):
        """Once, every day, weekdays, weekend or chosen days for a Start at / End at card."""
        from ..schedules import EVERY_DAY, WEEKDAYS, WEEKEND

        presets = {"every": EVERY_DAY, "weekdays": WEEKDAYS, "weekend": WEEKEND}
        current = (
            next((key for key, days in presets.items() if days == card.repeat), "custom") if card.repeat else "once"
        )
        options = [
            {"label": "Once", "value": "once", "glyph": "clock", "description": "Runs one time, then clears"},
            {"label": "Every day", "value": "every", "glyph": "clock", "description": "Saved as a repeating schedule"},
            {"label": "Weekdays", "value": "weekdays", "glyph": "clock", "description": "Monday to Friday"},
            {"label": "Weekend", "value": "weekend", "glyph": "clock", "description": "Saturday and Sunday"},
            {"label": "Choose days…", "value": "custom", "glyph": "clock", "description": "Pick days of the week"},
        ]

        def chosen(value):
            if value == "custom":
                from ..schedules_view import DayPicker

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
            self.status.set(
                "Offline timer preview only. No schedule or AC command was sent."
                if self.demo
                else "Repeating schedule saved in hOn. Manage it in Schedules."
            )
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
        self.save_schedule(
            None,
            start,
            end,
            days,
            requested,
            saved,
            failed,
            cancelled=lambda: self.status.set("Not saved. Adjust the time or days."),
        )
