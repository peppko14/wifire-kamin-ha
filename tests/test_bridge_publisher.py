# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.publisher."""

from __future__ import annotations

import json
import unittest
from typing import Any

from bridge.publisher import MqttPublisher
from bridge.topics import MqttTopics


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish(
        self,
        topic: str,
        payload: str | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )


class MqttPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.topics = MqttTopics(
            device_id="wifire_kamin",
            discovery_prefix="homeassistant",
        )
        self.publisher = MqttPublisher(
            self.client,
            self.topics,
        )

    def test_publish_availability_online(self) -> None:
        self.publisher.publish_availability(True)

        self.assertEqual(len(self.client.messages), 1)
        message = self.client.messages[0]

        self.assertEqual(
            message["topic"],
            "wifire_kamin/wifire_kamin/availability",
        )
        self.assertEqual(message["payload"], "online")
        self.assertEqual(message["qos"], 1)
        self.assertTrue(message["retain"])

    def test_publish_availability_offline(self) -> None:
        self.publisher.publish_availability(False)

        self.assertEqual(
            self.client.messages[0]["payload"],
            "offline",
        )

    def test_publish_state_uses_expected_payload(self) -> None:
        self.publisher.publish_state(
            {
                "temperature_c": 24,
                "flap_percent": 0,
                "flap_moving": False,
                "burn_time": "1:01",
                "burn_total_minutes": 61,
                "door_open": False,
                "door_state": "geschlossen",
                "fan_raw": 1,
            }
        )

        self.assertEqual(len(self.client.messages), 1)
        message = self.client.messages[0]

        self.assertEqual(
            message["topic"],
            "wifire_kamin/wifire_kamin/state",
        )
        self.assertEqual(message["qos"], 1)
        self.assertFalse(message["retain"])

        payload = json.loads(message["payload"])
        self.assertEqual(payload["temperature_c"], 24)
        self.assertEqual(payload["burn_total_minutes"], 61)
        self.assertEqual(payload["door_state"], "geschlossen")

    def test_publish_archive_sends_state_and_attributes(self) -> None:
        self.publisher.publish_archive(
            3,
            state="2026-04-11T02:21:00",
            attributes={
                "max_temperature_c": 620,
                "measurement_count": 121,
            },
        )

        self.assertEqual(len(self.client.messages), 2)

        state_message = self.client.messages[0]
        attributes_message = self.client.messages[1]

        self.assertEqual(
            state_message["topic"],
            "wifire_kamin/wifire_kamin/archive/3/state",
        )
        self.assertEqual(
            state_message["payload"],
            "2026-04-11T02:21:00",
        )
        self.assertTrue(state_message["retain"])

        self.assertEqual(
            attributes_message["topic"],
            "wifire_kamin/wifire_kamin/archive/3/attributes",
        )
        attributes = json.loads(attributes_message["payload"])
        self.assertEqual(attributes["max_temperature_c"], 620)
        self.assertEqual(attributes["measurement_count"], 121)
        self.assertTrue(attributes_message["retain"])


if __name__ == "__main__":
    unittest.main()
