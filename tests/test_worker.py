"""The background worker reports each cloud operation's result or a safe message."""

import unittest

import aiohttp
from pyhon.exceptions import HonAuthenticationError

from room_ac_control.controller import ControlError
from room_ac_control.worker import Worker, degrees


async def returns(value):
    return value


async def fails(error):
    raise error


class WorkerTests(unittest.TestCase):
    def setUp(self):
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
