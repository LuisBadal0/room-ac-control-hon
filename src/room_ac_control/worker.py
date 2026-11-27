"""Background event loop that runs hOn cloud operations off the Tk main thread."""

import asyncio
import queue
import threading

import aiohttp
from pyhon.exceptions import HonAuthenticationError, NoAuthenticationException

from .controller import ControlError, Controller
from .diagnostics import diagnostics, quiet_library_logs

# Added to a failed command, timer or schedule whose request may still have reached hOn.
UNKNOWN_OUTCOME = " The request outcome is unknown. Refresh and check hOn before retrying."

# Seconds one cloud operation may take. Signing in reads every AC, its timers and weather.
TIMEOUT = 90
TIMEOUTS = {"login": 180}
# Seconds an operation may wait for the ones before it to finish.
QUEUE_TIMEOUT = 120
BUSY = "An earlier cloud request is still running. Nothing was sent. Try again in a moment."

# Third-party authentication errors can include token-bearing URLs. Do not log them.
quiet_library_logs()


class Worker:
    def __init__(self, memory=None):
        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(
            lambda loop, context: diagnostics.record("background_task_failed", context.get("exception"))
        )
        self.results = queue.Queue()
        self.changes = queue.Queue()
        self.controller = Controller(on_change=self.changes.put, memory=memory)
        # Started by the first cloud operation, so an offline preview never runs it.
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.starting = threading.Lock()

    def start(self):
        with self.starting:
            if self.thread.ident is None and not self.loop.is_closed():
                self.thread.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coroutine, callback, operation, on_error=None):
        async def perform():
            # Operations run one at a time; one waiting behind a slow request gets a deadline too.
            try:
                await asyncio.wait_for(self.controller.lock.acquire(), timeout=QUEUE_TIMEOUT)
            except TimeoutError:
                coroutine.close()
                self.results.put((on_error, None, BUSY, operation))
                return
            try:
                try:
                    result = await asyncio.wait_for(coroutine, timeout=TIMEOUTS.get(operation, TIMEOUT))
                    self.results.put((callback, result, None, operation))
                except Exception as error:
                    diagnostics.record("cloud_operation_failed", error)
                    if isinstance(error, ControlError):
                        text = str(error)
                    elif isinstance(error, (HonAuthenticationError, NoAuthenticationException)):
                        text = "Cloud sign-in failed. Check your email and password. Social sign-in may require an hOn email/password account."
                    elif operation == "login" and isinstance(error, TimeoutError):
                        text = "Signing in took too long. Check internet access and try again."
                    elif isinstance(error, (aiohttp.ClientError, TimeoutError, OSError)):
                        text = "Could not reach the cloud service. Check internet access and try again."
                    else:
                        text = f"The cloud service returned an unexpected response ({type(error).__name__}). The community integration may need updating."
                    if operation in {"command", "timer", "schedule"} and not isinstance(error, ControlError):
                        text += UNKNOWN_OUTCOME
                    # Without an error handler the callback is None and the app shows the message.
                    self.results.put((on_error, None, text, operation))
            finally:
                self.controller.lock.release()

        if self.loop.is_closed():
            coroutine.close()  # The app is closing; nothing runs any more.
            return
        self.start()
        asyncio.run_coroutine_threadsafe(perform(), self.loop)

    def close(self):
        if self.loop.is_closed():
            return
        if self.thread.ident is None:
            self.loop.close()  # Nothing ever ran on it.
            return

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
        self.thread.join(timeout=1)
        if not self.thread.is_alive():
            self.loop.close()


def degrees(value):
    try:
        return f"{float(value):g} °C"
    except (ValueError, TypeError):
        return "Unknown"
