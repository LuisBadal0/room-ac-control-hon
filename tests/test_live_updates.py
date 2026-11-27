"""Cloud events trigger refresh signals without mutating or commanding the AC."""

import asyncio
import unittest
from types import SimpleNamespace

from room_ac_control.live_updates import CloudUpdates


class FakeClient:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.subscriptions = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def subscribe(self, packet):
        self.subscriptions.append(packet)


class NotificationTests(unittest.TestCase):
    def make_listener(self):
        client, events = FakeClient(), []
        devices = [
            SimpleNamespace(unique_id="office", info={"topics": {"subscribe": ["office/status", "office/connected"]}}),
            SimpleNamespace(unique_id="bedroom", info={"topics": {"subscribe": ["bedroom/status"]}}),
        ]
        listener = CloudUpdates("test-token", "test-signature", devices, events.append, factory=lambda **kwargs: client)
        return listener, client, events

    def test_subscriptions_and_event_routing(self):
        listener, client, events = self.make_listener()
        listener.start()
        listener.connected(None)
        self.assertTrue(client.started)
        self.assertEqual(len(client.subscriptions), 3)
        events.clear()
        listener.published(SimpleNamespace(publish_packet=SimpleNamespace(topic="office/status")))
        self.assertEqual(events, ["office"])
        listener.published(SimpleNamespace(publish_packet=SimpleNamespace(topic="unknown/status")))
        self.assertEqual(events, ["office"])

    def test_close_ignores_late_messages_and_reconnects(self):
        listener, client, events = self.make_listener()
        listener.close()
        listener.published(SimpleNamespace(publish_packet=SimpleNamespace(topic="office/status")))
        listener.connected(None)
        self.assertTrue(client.stopped)
        self.assertEqual(events, [])
        self.assertEqual(client.subscriptions, [])


class TokenRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_token_request_does_not_hold_up_commands(self):
        from unittest.mock import patch

        from room_ac_control import controller as controller_module

        started = asyncio.Event()
        controller = controller_module.Controller(on_change=lambda device_id: None)

        class FakeAPI:
            auth = SimpleNamespace(id_token="fixture-token")

            async def load_aws_token(self):
                # A command arriving now must not wait for hOn to answer.
                self.locked = controller.lock.locked()
                return "fixture-signature"

        class Listener:
            closed = False

            def __init__(self, token, signature, devices, changed):
                self.args = (token, signature, devices)

            def start(self):
                started.set()

            def close(self):
                self.closed = True

        api = controller.api = FakeAPI()
        with patch.object(controller_module, "CloudUpdates", Listener):
            task = asyncio.create_task(controller.watch_updates())
            await asyncio.wait_for(started.wait(), timeout=5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(api.locked)
