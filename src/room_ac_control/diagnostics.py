"""Bounded, opt-in export of diagnostics without exception text or account data."""
from collections import deque
from datetime import datetime, timezone
import json
import logging
import threading

from . import __version__

EVENTS = {"cloud_operation_failed", "notification_failed", "subscription_failed",
          "notification_close_failed", "tray_start_failed", "tray_show_failed",
          "tray_hide_failed", "tray_close_failed", "worker_shutdown_failed",
          "background_task_failed", "ui_callback_failed", "state_load_failed",
          "state_save_failed", "credential_save_failed"}
ERROR_TYPES = {"TimeoutError", "OSError", "PermissionError", "FileNotFoundError",
               "ConnectionError", "RuntimeError", "ValueError", "TypeError",
               "HonAuthenticationError", "NoAuthenticationException", "ControlError"}


class Diagnostics:
    def __init__(self, limit=100):
        self.events = deque(maxlen=limit)
        self.lock = threading.Lock()

    def record(self, event, error=None):
        if event not in EVENTS:
            raise ValueError("Unknown diagnostic event")
        kind = type(error).__name__ if error is not None else "UnknownError"
        with self.lock:
            self.events.append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "event": event, "error": kind if kind in ERROR_TYPES else "UnexpectedError"})

    def report(self):
        with self.lock:
            return {"version": __version__, "events": [dict(event) for event in self.events]}

    def export(self, path):
        path.write_text(json.dumps(self.report(), indent=2)+"\n", encoding="utf-8")


diagnostics = Diagnostics()


def quiet_library_logs():
    """Suppress potentially sensitive library output without disabling all logging."""
    for name in ("pyhon", "aiohttp", "awscrt", "awsiot", "pystray"):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL+1)
