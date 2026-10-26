"""Background event loop that runs hOn cloud operations off the Tk main thread."""
import asyncio
import queue
import threading

import aiohttp
from pyhon.exceptions import HonAuthenticationError, NoAuthenticationException

from .controller import Controller, ControlError
from .diagnostics import diagnostics, quiet_library_logs

# Third-party authentication errors can include token-bearing URLs. Do not log them.
quiet_library_logs()


class Worker:
    def __init__(self, memory=None):
        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(lambda loop, context: diagnostics.record("background_task_failed", context.get("exception")))
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
                    diagnostics.record("cloud_operation_failed", error)
                    if isinstance(error, ControlError):
                        text = str(error)
                    elif isinstance(error, (HonAuthenticationError, NoAuthenticationException)):
                        text = "Cloud sign-in failed. Check your email and password. Social sign-in may require an hOn email/password account."
                    elif isinstance(error, (aiohttp.ClientError, TimeoutError, OSError)):
                        text = "Could not reach the cloud service. Check internet access and try again."
                    else:
                        text = f"The cloud service returned an unexpected response ({type(error).__name__}). The community integration may need updating."
                    if operation in {"command", "timer"} and not isinstance(error, ControlError):
                        text += " The request outcome is unknown. Refresh and check hOn before retrying."
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
        except Exception as error:
            diagnostics.record("worker_shutdown_failed", error)
        self.loop.call_soon_threadsafe(self.loop.stop)


def degrees(value):
    try:
        return f"{float(value):g} °C"
    except (ValueError, TypeError):
        return "Unknown"
