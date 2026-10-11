"""Windows desktop controller for Haier air conditioners paired with the cloud service."""
import asyncio
import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import aiohttp
from pyhon.exceptions import HonAuthenticationError, NoAuthenticationException

from .controller import Controller, ControlError

# Third-party authentication errors can include token-bearing URLs. Do not log them.
logging.disable(logging.CRITICAL)


class Worker:
    def __init__(self, memory=None):
        self.loop = asyncio.new_event_loop()
        self.results = queue.Queue()
        self.changes = queue.Queue()
        self.controller = Controller(on_change=self.changes.put,memory=memory)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coroutine, callback, operation, on_error=None):
        async def perform():
            async with self.controller.lock:
                try:
                    result = await asyncio.wait_for(coroutine, timeout=90)
                    self.results.put((callback, result, None, operation))
                except Exception as error:
                    if isinstance(error, ControlError):
                        text = str(error)
                    elif isinstance(error, (HonAuthenticationError, NoAuthenticationException)):
                        text = "Cloud sign-in failed. Check your email and password. Social sign-in may require an cloud account email/password account."
                    elif isinstance(error, (aiohttp.ClientError, TimeoutError, OSError)):
                        text = "Could not reach the cloud service. Check internet access and try again."
                    else:
                        text = f"The cloud service returned an unexpected response ({type(error).__name__}). The community integration may need updating."
                    if operation == "command" and not isinstance(error, ControlError):
                        text += " The command outcome is unknown. Refresh and check the AC before retrying."
                    self.results.put((on_error or callback, None, text, operation))
        asyncio.run_coroutine_threadsafe(perform(), self.loop)

    def close(self):
        async def finish():
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()
            await self.controller.close()
        try:
            asyncio.run_coroutine_threadsafe(finish(), self.loop).result(timeout=3)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


def degrees(value):
    try:
        return f"{float(value):g} °C"
    except (ValueError, TypeError):
        return "Unknown"
