"""Signing in, the connected dashboard and signing out."""

from ..diagnostics import diagnostics
from .layout import (
    FLOW,
    WIDTH,
)


class SessionMixin:
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
        if self.demo:
            from ..demo import seed_history

            seed_history(self.memory, devices)
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
