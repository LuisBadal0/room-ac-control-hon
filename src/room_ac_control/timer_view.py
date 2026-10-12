"""Theme-matched on/off timer editor, with explicit PC scheduling requirements."""
import tkinter as tk
from tkinter import ttk

from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, icon
from .window_header import WindowHeader
from .diagnostics import diagnostics


class TimerView:
    def __init__(self, app):
        self.app = app
        self.account, self.device = app.memory.account, app.selected["id"]
        self.window = tk.Toplevel(app.root)
        app.dialog, app.dialog_view = self.window, self
        self.window.title("Room AC Control · On / off timers")
        self.window.geometry("560x740")
        self.window.resizable(False, False)
        self.window.configure(bg=BG)
        self.window.transient(app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        self.header = WindowHeader(self.window, "Room AC Control · Timers", self.close, maximize=False)
        body = tk.Frame(self.window, bg=BG, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="On / off timers", bg=BG, fg=TEXT,
                 font=("Segoe UI", 23, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text=app.selected["name"], bg=BG, fg=MUTED,
                 font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(4, 20))
        entries = app.timers.get(self.account, self.device)
        self.fields, self.saved_labels = {}, {}
        for action, title in (("on", "Turn on"), ("off", "Turn off")):
            entry = entries[action]
            card = tk.Frame(body, bg=CARD, padx=18, pady=14)
            card.pack(fill="x", pady=(0, 12))
            heading = tk.Frame(card, bg=CARD)
            heading.pack(fill="x")
            glyph = tk.Canvas(heading, width=30, height=30, bg=CARD, highlightthickness=0)
            glyph.pack(side="left", padx=(0, 10))
            icon(glyph, "clock", 15, 15)
            tk.Label(heading, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(side="left")
            enabled = tk.BooleanVar(value=entry["enabled"])
            supported = app.selected.get("can_" + action, app.demo)
            toggle = tk.Checkbutton(heading, text="Enabled", variable=enabled, bg=CARD, fg=TEXT,
                                   selectcolor=BG, activebackground=HOVER, activeforeground=TEXT,
                                   font=("Segoe UI", 10), cursor="hand2",
                                   state="normal" if supported else "disabled")
            toggle.pack(side="right")
            time_row = tk.Frame(card, bg=CARD)
            time_row.pack(fill="x", pady=(10, 8))
            value = tk.StringVar(value=entry["time"])
            editor = tk.Entry(time_row, textvariable=value, bg=BG, fg=TEXT, insertbackground=TEXT,
                              relief="flat", width=6, font=("Segoe UI", 27),
                              highlightthickness=1, highlightbackground="#394035", highlightcolor=ACCENT)
            editor.pack(side="left")
            tk.Label(time_row, text="24-hour time\nPC local time", bg=CARD, fg=MUTED,
                     justify="left", font=("Segoe UI", 9)).pack(side="left", padx=14)
            repeat = tk.StringVar(value=entry["repeat"])
            repeat_row = tk.Frame(card, bg=CARD)
            repeat_row.pack(fill="x")
            buttons = {}
            for key, label in (("daily", "Every day"), ("once", "Once")):
                button = tk.Button(repeat_row, text=label, command=lambda key=key, repeat=repeat: repeat.set(key),
                                   bg=BG, fg=MUTED, activebackground=HOVER, activeforeground=TEXT,
                                   relief="flat", padx=16, pady=6, font=("Segoe UI", 10), cursor="hand2")
                button.pack(side="left", padx=(0, 8))
                button.bind("<Enter>", lambda event: event.widget.configure(bg=HOVER))
                buttons[key] = button
            def draw_repeat(*args, variable=repeat, buttons=buttons):
                for key, button in buttons.items():
                    button.configure(bg=ACCENT if variable.get() == key else BG,
                                     fg=BG if variable.get() == key else MUTED)
            for button in buttons.values():
                button.bind("<Leave>", draw_repeat)
            repeat.trace_add("write", draw_repeat)
            draw_repeat()
            info = tk.StringVar()
            tk.Label(card, textvariable=info, bg=CARD, fg=MUTED, anchor="w",
                     font=("Segoe UI", 9), wraplength=460).pack(fill="x", pady=(10, 0))
            self.saved_labels[action] = info
            self.fields[action] = {"enabled": enabled, "time": value, "repeat": repeat, "supported": supported}
        tk.Label(body, text="Keep the PC awake, online and signed in. Timers run while the app is open, including in the system tray. Missed times are skipped.",
                 bg=BG, fg=MUTED, wraplength=500, justify="left", font=("Segoe UI", 10)).pack(fill="x", pady=(0, 14))
        self.note = tk.StringVar(value="Turn on uses the unit’s current mode and its remembered settings.")
        tk.Label(body, textvariable=self.note, bg=BG, fg=ACCENT, wraplength=500,
                 justify="left", font=("Segoe UI", 10)).pack(fill="x", pady=(0, 12))
        footer = ttk.Frame(body)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Save timers", style="Accent.TButton", command=self.save).pack(side="left", expand=True, fill="x", padx=(0, 8))
        ttk.Button(footer, text="Disable all", command=self.disable).pack(side="left", padx=(0, 8))
        ttk.Button(footer, text="Close", command=self.close).pack(side="right")
        self.refresh_status()
        self.window.update_idletasks()
        x = max(0, app.root.winfo_rootx() + (app.root.winfo_width() - self.window.winfo_width()) // 2)
        y = max(0, app.root.winfo_rooty() + (app.root.winfo_height() - self.window.winfo_height()) // 2)
        self.window.geometry(f"+{x}+{y}")

    def refresh_status(self):
        entries = self.app.timers.get(self.account, self.device)
        outcomes = {"sending": "Command being sent", "accepted": "Cloud accepted the command",
                    "failed": "Command failed or outcome unknown; check AC status", "missed": "Missed time skipped"}
        for action, entry in entries.items():
            text = ("Next: " + entry["next"].replace("T", " ")[:16]) if entry["enabled"] else "Timer disabled"
            if entry.get("last_result") in outcomes:
                text += " · " + outcomes[entry["last_result"]]
            if not self.fields[action]["supported"]:
                text = "This AC does not expose this power command."
            self.saved_labels[action].set(text)

    def save(self):
        settings = {action: {key: fields[key].get() for key in ("enabled", "time", "repeat")} for action, fields in self.fields.items()}
        for action, fields in self.fields.items():
            if not fields["supported"]:
                settings[action]["enabled"] = False
        try:
            self.app.timers.save(self.account, self.device, settings)
        except ValueError as error:
            self.note.set(str(error))
            return
        except OSError as error:
            diagnostics.record("state_save_failed", error)
            self.note.set("Timers could not be saved. Check access to the app’s data folder.")
            return
        self.note.set("Timers saved on this PC. Saving does not send an AC command.")
        self.app.status.set("On / off timers saved. Keep the app open and the PC awake.")
        self.refresh_status()

    def disable(self):
        for fields in self.fields.values():
            fields["enabled"].set(False)
        self.save()

    def close(self):
        self.app.dialog = None
        self.app.dialog_view = None
        self.window.destroy()
