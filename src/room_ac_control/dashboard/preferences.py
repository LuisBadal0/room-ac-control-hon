"""Language, appearance, the Settings dropdown and update preferences."""

from .. import updates
from ..button_theme import configure_styles
from ..choice_widgets import ChoicePanel
from ..diagnostics import diagnostics
from ..i18n import (
    LANGUAGES,
    broadcast_language,
)
from ..theme import (
    THEMES,
    C,
    broadcast_theme,
    resolve_theme,
)
from .layout import (
    THEME_CHOICES,
)


class PreferencesMixin:
    def language_menu(self, parent=None):
        parent = parent or self.root
        options = [
            {"label": "System language", "value": "system", "glyph": "globe", "description": "Follow Windows language"}
        ]
        options.extend({"label": label, "value": value, "glyph": "globe"} for value, label in LANGUAGES.items())
        self.language_panel = ChoicePanel(parent, "Language", options, self.i18n.preference, self.set_language)

    def set_language(self, preference):
        self.i18n.set_language(preference)
        broadcast_language(self.root)
        if self.tray:
            try:
                self.tray.refresh_language()
            except Exception as error:
                diagnostics.record("tray_language_failed", error)
        try:
            self.storage.save_language(self.i18n.preference)
        except OSError:
            self.status.set("Language changed for this session, but the preference could not be saved.")

    def theme_menu(self, parent=None):
        parent = parent or self.root
        self.theme_panel = ChoicePanel(parent, "Appearance", THEME_CHOICES, self.theme_preference, self.set_theme)

    def set_theme(self, preference):
        self.theme_preference = preference if preference in THEMES else "system"
        self.apply_theme()
        try:
            self.storage.save_theme(self.theme_preference)
        except OSError:
            self.status.set("Appearance changed for this session, but the preference could not be saved.")

    def apply_theme(self):
        """Repaint every open window in place; edits, drafts and dialogs are kept."""
        mode = resolve_theme(self.theme_preference)
        if mode == C.mode:
            return False
        C.use(mode)
        configure_styles(self.root)
        broadcast_theme(self.root)
        return True

    def open_settings(self):
        if self.settings_panel:
            self.settings_panel.close()  # The button toggles the dropdown.
            return
        from ..settings_panel import SettingsPanel

        self.settings_button.set_pressed(True)
        SettingsPanel(self)

    # Signed app updates for the portable build.

    def auto_check_updates(self):
        self.update_job = None
        if self.closing:
            return
        if self.updater.enabled:
            self.updater.check(quiet=True)
        self.update_job = self.root.after(updates.CHECK_EVERY_MS, self.auto_check_updates)

    def set_auto_update(self, value):
        self.updater.enabled = bool(value)
        try:
            self.storage.save_auto_update(bool(value))
        except OSError:
            self.status.set("Update setting changed for this session, but the preference could not be saved.")
        if value and self.updater.state in {"idle", "current"}:
            self.updater.check(quiet=True)
        self.updater.notify()

    def updates_changed(self):
        if self.closing:
            return
        waiting = self.updater.release is not None and self.updater.state in {
            "available",
            "downloading",
            "verifying",
            "ready",
            "failed",
        }
        self.settings_button.set_badge(waiting)
        self.update_notice_bar.refresh()
        if self.updater.state == "ready":
            # The person clicked Update; the helper waits for this process to exit.
            try:
                applied = self.updater.apply()
            except OSError as error:
                diagnostics.record("update_failed", error)
                self.updater.state, self.updater.error = (
                    "failed",
                    "Could not start the update helper. Nothing was changed.",
                )
                self.updater.notify()
                return
            if applied:
                self.root.after(300, self.close)

    def open_updates(self, parent=None):
        if self.updates_view and self.updates_view.window.winfo_exists():
            self.updates_view.window.lift()
            return
        from ..updates_view import UpdatesView

        UpdatesView(self, parent or self.root)
