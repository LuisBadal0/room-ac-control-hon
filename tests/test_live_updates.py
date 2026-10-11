"""Cloud events trigger refresh signals without mutating or commanding the AC."""
import unittest
from types import SimpleNamespace

from room_ac_control.live_updates import CloudUpdates


class FakeClient:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.subscriptions = []

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def subscribe(self, packet): self.subscriptions.append(packet)


class NotificationTests(unittest.TestCase):
    def make_listener(self):
        client, events = FakeClient(), []
        devices = [SimpleNamespace(unique_id="office", info={"topics": {"subscribe": ["office/status", "office/connected"]}}),
                   SimpleNamespace(unique_id="bedroom", info={"topics": {"subscribe": ["bedroom/status"]}})]
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
