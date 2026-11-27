"""The background worker reports each cloud operation's result or a safe message."""

import asyncio
import gc
import unittest
from unittest.mock import patch

import aiohttp
from pyhon.exceptions import HonAuthenticationError

from room_ac_control import worker as worker_module
from room_ac_control.controller import ControlError
from room_ac_control.worker import BUSY, Worker, degrees


async def returns(value):
    return value


async def fails(error):
    raise error


class WorkerTests(unittest.TestCase):
    def setUp(self):
        # Free Tk objects left by earlier UI tests here, on the main thread. Collected later on
        # the worker's thread, they make Tcl abort the whole run ("deleted by the wrong thread").
        gc.collect()
        self.worker = Worker()
        self.addCleanup(self.worker.close)

    def result(self, coroutine, operation="refresh", on_error=None):
        self.worker.submit(coroutine, self.done, operation, on_error=on_error)
        return self.worker.results.get(timeout=10)

    def done(self, value):
        """Stands in for a result callback; the worker only passes it back."""

    def failed(self, error):
        """Stands in for an operation's own error handler."""

    def test_a_result_is_returned_with_its_callback(self):
        self.assertEqual(self.result(returns({"id": "fixture"})), (self.done, {"id": "fixture"}, None, "refresh"))

    def test_an_error_goes_to_the_operations_own_handler(self):
        callback, value, error, operation = self.result(fails(ControlError("Fixture message.")), on_error=self.failed)
        self.assertEqual((callback, value, error, operation), (self.failed, None, "Fixture message.", "refresh"))

    def test_an_error_without_a_handler_has_no_callback(self):
        # The app then shows the message itself; the result callback must not receive it.
        callback, value, error, _ = self.result(fails(ControlError("Fixture message.")))
        self.assertIsNone(callback)
        self.assertIsNone(value)
        self.assertEqual(error, "Fixture message.")

    def test_messages_do_not_repeat_exception_text(self):
        secret = "token=secret-test-token"
        cases = (
            (HonAuthenticationError(secret), "Cloud sign-in failed."),
            (aiohttp.ClientError(secret), "Could not reach the cloud service."),
            (TimeoutError(secret), "Could not reach the cloud service."),
            (KeyError(secret), "unexpected response (KeyError)"),
        )
        for raised, expected in cases:
            error = self.result(fails(raised))[2]
            self.assertIn(expected, error)
            self.assertNotIn(secret, error)

    def test_an_unconfirmed_change_says_its_outcome_is_unknown(self):
        for operation in ("command", "timer", "schedule"):
            self.assertIn("outcome is unknown", self.result(fails(TimeoutError()), operation)[2])
            # The app refused the request itself, so nothing was sent.
            self.assertNotIn("outcome is unknown", self.result(fails(ControlError("Refused.")), operation)[2])
        self.assertNotIn("outcome is unknown", self.result(fails(TimeoutError()), "refresh")[2])

    def test_a_worker_that_never_ran_closes_without_waiting(self):
        worker = Worker()
        self.assertIsNone(worker.thread.ident)  # An offline preview never starts the thread.
        worker.close()
        self.assertTrue(worker.loop.is_closed())
        worker.close()  # Closing twice is harmless.

    def test_closing_stops_the_thread_and_closes_its_loop(self):
        self.result(returns(1))
        self.worker.close()
        self.assertFalse(self.worker.thread.is_alive())
        self.assertTrue(self.worker.loop.is_closed())
        coroutine = returns(2)
        self.worker.submit(coroutine, self.done, "refresh")  # Ignored once closed.
        self.assertIsNone(coroutine.cr_frame)  # Closed, so it never warns "never awaited".
        self.assertTrue(self.worker.results.empty())

    def test_an_operation_stuck_behind_a_slow_one_gives_up_without_running(self):
        ran = []

        async def slow():
            await asyncio.sleep(0.5)
            return "slow"

        async def later():
            ran.append("later")

        with patch.object(worker_module, "QUEUE_TIMEOUT", 0.05):
            self.worker.submit(slow(), self.done, "refresh")
            self.worker.submit(later(), self.done, "command", on_error=self.failed)
            first = self.worker.results.get(timeout=10)
            second = self.worker.results.get(timeout=10)
        self.assertEqual(first, (self.failed, None, BUSY, "command"))  # It never waited for its turn.
        self.assertEqual(second[1], "slow")
        self.assertEqual(ran, [])
        self.assertEqual(self.result(returns("next")), (self.done, "next", None, "refresh"))  # The lock is free.

    def test_a_slow_sign_in_says_so(self):
        error = self.result(fails(TimeoutError()), "login")[2]
        self.assertIn("Signing in took too long", error)
        self.assertGreater(worker_module.TIMEOUTS["login"], worker_module.TIMEOUT)

    def test_operations_run_one_at_a_time_in_order(self):
        for number in range(5):
            self.worker.submit(returns(number), self.done, "refresh")
        self.assertEqual([self.worker.results.get(timeout=10)[1] for _ in range(5)], [0, 1, 2, 3, 4])


class DegreesTests(unittest.TestCase):
    def test_temperatures_are_shown_without_trailing_zeros(self):
        self.assertEqual(degrees("23.0"), "23 °C")
        self.assertEqual(degrees(23.5), "23.5 °C")
        self.assertEqual(degrees(None), "Unknown")


if __name__ == "__main__":
    unittest.main()
