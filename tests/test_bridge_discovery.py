# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

import unittest

from bridge.discovery import build_discovery_payload
from bridge.topics import MqttTopics


class FakeConfig:
    DEVICE_ID = "wifire_kamin"
    DEVICE_NAME = "WiFire-Kamin"
    MANUFACTURER = "FireControls"
    MODEL = "WiFire"
    ENABLE_FAN_ENTITY = False


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = MqttTopics(
            device_id=FakeConfig.DEVICE_ID,
            discovery_prefix="homeassistant",
        )

    def test_payload_contains_device_metadata(self) -> None:
        payload = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="WiFire-Kamin MQTT Bridge",
            app_version="0.6.0",
        )

        self.assertEqual(
            payload["device"]["name"],
            "WiFire-Kamin",
        )
        self.assertEqual(
            payload["device"]["model"],
            "WiFire",
        )

    def test_payload_contains_live_components(self) -> None:
        payload = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.6.0",
        )

        components = payload["components"]
        self.assertIn(
            "wifire_kamin_temperature",
            components,
        )
        self.assertIn(
            "wifire_kamin_door",
            components,
        )

    def test_payload_contains_three_archive_components(self) -> None:
        payload = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.6.0",
        )

        components = payload["components"]
        for number in (1, 2, 3):
            self.assertIn(
                f"wifire_kamin_archive_{number}",
                components,
            )

    def test_fan_component_is_optional(self) -> None:
        payload = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.6.0",
        )

        self.assertNotIn(
            "wifire_kamin_fan_raw",
            payload["components"],
        )


if __name__ == "__main__":
    unittest.main()
