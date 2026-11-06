"""The Updates window: installed version, signed update status and the automatic-check setting."""
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

from . import __version__
from .i18n import tr, localized, localized_title, refresh_on_language
from .theme import C, font, icon, paint, rounded, refresh_on_theme

SIZE = (480, 410)


def update_message(updater):
    """Headline and detail for the current state, in English (translated when drawn)."""
    release = updater.release
    version = release["version"] if release else ""
    if updater.demo:
        return "Updates are off in the preview", "The offline preview never checks for or installs updates."
    if not updater.supported:
        return ("Updates are not available here",
                "This copy runs from source. Update it with git, or use the portable release.")
    state = updater.state
    if state == "checking":
        return "Checking for updates…", "This only reads the latest signed release information."
    if state == "current":
        return "You have the latest version.", "Room AC Control checks again later if automatic checks are on."
    if state == "available":
        return ("Version {version} is available.".format(version=version),
                "Click Update to download and install it. Room AC Control restarts when it is ready.")
    if state == "downloading":
        return ("Downloading version {version}… {value}%".format(version=version, value=int(updater.progress*100)),
                "You can keep using the app while it downloads.")
    if state == "verifying":
        return "Checking the new version…", "Its signature and offline checks must pass before anything changes."
    if state == "ready":
        return "Restarting to finish the update…", "Room AC Control opens again in a few seconds."
    if state == "failed":
        return "The update did not finish", updater.error or ""
    return "Check for a newer version.", "Room AC Control looks for signed releases on GitHub."


def primary_label(updater):
    state = updater.state
    if state in {"available", "downloading", "verifying", "ready"} or (state == "failed" and updater.release):
        return "Update"
    return "Check now"


def primary_enabled(updater):
    return updater.supported and not updater.busy and updater.state != "ready"


def run_primary(app, parent):
    """Check for a release, or install the one found after confirming unsaved edits."""
    updater = app.updater
    if updater.release and updater.state in {"available", "failed"}:
        if app.dirty and not messagebox.askokcancel(
                "Room AC Control", tr(parent, "Room AC Control restarts to finish the update. Changes you have not applied are discarded."),
                parent=parent):
            return
        updater.install()
    else:
        updater.check()


class UpdatesView:
    def __init__(self, app, parent=None):
        self.app, self.updater = app, app.updater
        parent = parent or app.root
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        app.updates_view = self
        localized_title(self.window, "Room AC Control · Updates")
        self.window.geometry("{}x{}".format(*SIZE))
        self.window.resizable(False, False)
        paint(self.window, bg="BG")
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        from .window_header import WindowHeader
        self.header = WindowHeader(self.window, "Room AC Control · Updates", self.close, maximize=False,
                                   size=SIZE, owner=parent.winfo_toplevel())
        body = ttk.Frame(self.window, padding=(24, 4, 24, 20))
        body.pack(fill="both", expand=True)
        localized(ttk.Label(body, text="Updates", font=font(21, "black"))).pack(anchor="w")
        self.installed = ttk.Label(body, style="Muted.TLabel")
        self.installed.pack(anchor="w", pady=(2, 14))
        refresh_on_language(self.installed, self.paint_installed)
        self.paint_installed()
        self.card = paint(tk.Canvas(body, height=128, highlightthickness=0), bg="BG")
        self.card.pack(fill="x")
        self.card.bind("<Configure>", lambda event: self.draw())
        refresh_on_language(self.card, self.draw)
        refresh_on_theme(self.card, self.draw)
        self.automatic = tk.BooleanVar(self.window, value=self.updater.enabled)
        self.toggle = localized(ttk.Checkbutton(body, text="Check for updates automatically", variable=self.automatic,
                                                command=lambda: app.set_auto_update(self.automatic.get())))
        self.toggle.pack(anchor="w", pady=(16, 6))
        localized(ttk.Label(body, text="Updates are signed by Room AC Control and checked before they are installed. "
                                       "Your sign-in and settings are kept.", style="Muted.TLabel",
                            wraplength=SIZE[0]-48, justify="left")).pack(anchor="w")
        footer = ttk.Frame(body)
        footer.pack(side="bottom", fill="x")
        self.primary = ttk.Button(footer, style="Accent.TButton", command=self.primary_action, cursor="hand2")
        self.primary.pack(side="left", expand=True, fill="x", padx=(0, 10))
        localized(ttk.Button(footer, text="Close", command=self.close)).pack(side="right")
        localized(ttk.Button(footer, text="Diagnostics", style="Ghost.TButton",
                             command=app.export_diagnostics)).pack(side="right", padx=(0, 6))
        self.notes = localized(ttk.Button(footer, text="What's new", style="Ghost.TButton", command=self.open_notes))
        refresh_on_language(self.primary, self.refresh)
        self.unlisten = self.updater.listen(self.refresh)
        self.refresh()

    def paint_installed(self):
        self.installed.configure(text=tr(self.installed, "Installed version {version}".format(version=__version__)))

    def message(self):
        return update_message(self.updater)

    def draw(self):
        c = self.card
        c.delete("all")
        width = max(c.winfo_width(), SIZE[0]-48)
        failed = self.updater.state == "failed"
        rounded(c, 1, 1, width-1, 127, 14, fill=C.CARD, outline=C.EDGE)
        circle = C.DANGER_BG if failed else C.SOFT
        c.create_oval(18, 18, 58, 58, fill=circle, outline="")
        icon(c, "alert" if failed else "update", 38, 38, C.DANGER_TEXT if failed else C.ON_SOFT, scale=.8, bg=circle)
        headline, detail = self.message()
        c.create_text(74, 28, text=tr(c, headline), anchor="w", fill=C.TEXT, font=font(12, "bold"), width=width-92)
        c.create_text(74, 52, text=tr(c, detail), anchor="nw", fill=C.MUTED, font=font(9), width=width-92)
        if self.updater.state in {"downloading", "verifying"}:
            rounded(c, 74, 108, width-18, 114, 3, fill=C.SURFACE, outline="")
            done = 1.0 if self.updater.state == "verifying" else max(.02, self.updater.progress)
            rounded(c, 74, 108, 74+(width-92)*done, 114, 3, fill=C.BRAND, outline="")

    def refresh(self):
        if not self.window.winfo_exists():
            return
        updater = self.updater
        self.automatic.set(updater.enabled)
        self.toggle.state(["!disabled"] if updater.supported else ["disabled"])
        self.primary.configure(text=tr(self.primary, primary_label(updater)))
        self.primary.state(["!disabled"] if primary_enabled(updater) else ["disabled"])
        if updater.release:
            self.notes.pack(side="right", padx=(0, 6))
        else:
            self.notes.pack_forget()
        self.draw()

    def primary_action(self):
        run_primary(self.app, self.window)

    def open_notes(self):
        if self.updater.release:
            webbrowser.open(self.updater.release["notes"])

    def close(self):
        self.unlisten()
        self.app.updates_view = None
        if self.window.winfo_exists():
            self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
