"""Cloud status notifications. MQTT callbacks only signal; REST fetches actual state."""
import secrets

from awscrt import mqtt5
from awsiot import mqtt5_client_builder
from pyhon import const


class CloudUpdates:
    def __init__(self, token, signature, devices, changed, factory=None):
        self.closed = False
        self.changed = changed
        self.topics = {}
        for device in devices:
            for topic in device.info.get("topics", {}).get("subscribe", []):
                self.topics.setdefault(topic, set()).add(device.unique_id)
        factory = factory or mqtt5_client_builder.websockets_with_custom_authorizer
        self.client = factory(
            endpoint=const.AWS_ENDPOINT,
            auth_authorizer_name=const.AWS_AUTHORIZER,
            auth_authorizer_signature=signature,
            auth_token_key_name="token",
            auth_token_value=token,
            client_id=f"room_ac_pc_{secrets.token_hex(8)}",
            on_lifecycle_connection_success=self.connected,
            on_publish_received=self.published,
        )

    def start(self):
        if self.topics:
            self.client.start()

    def connected(self, event):
        if self.closed:
            return
        for topic in self.topics:
            try:
                # Asynchronous subscription; never block an AWS callback thread.
                self.client.subscribe(mqtt5.SubscribePacket([mqtt5.Subscription(topic)]))
            except Exception:
                pass  # Periodic REST refresh continues if notifications are unavailable.
        for device_id in set().union(*self.topics.values()) if self.topics else ():
            self.changed(device_id)

    def published(self, event):
        if self.closed or not event or not event.publish_packet:
            return
        for device_id in self.topics.get(event.publish_packet.topic, ()):
            self.changed(device_id)

    def close(self):
        self.closed = True
        self.client.stop()
