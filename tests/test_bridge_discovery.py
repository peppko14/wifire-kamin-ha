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

    def test_payload_contains_dashboard_curve_component(self) -> None:
        components = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.12.0",
        )["components"]

        component = components["wifire_kamin_dashboard_curves"]
        self.assertEqual(
            component["state_topic"],
            "wifire_kamin/wifire_kamin/dashboard_curves",
        )
        self.assertEqual(
            component["json_attributes_topic"],
            "wifire_kamin/wifire_kamin/dashboard_curves",
        )
        self.assertEqual(component["device_class"], "timestamp")
        self.assertEqual(component["entity_category"], "diagnostic")

    def test_payload_contains_six_statistics_components(self) -> None:
        payload = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.7.0",
        )
        components = payload["components"]
        expected = {
            "wifire_kamin_statistics_burn_count",
            "wifire_kamin_statistics_latest_burn",
            "wifire_kamin_statistics_total_duration",
            "wifire_kamin_statistics_average_duration",
            "wifire_kamin_statistics_average_max_temperature",
            "wifire_kamin_statistics_highest_temperature",
        }

        self.assertTrue(expected.issubset(components))
        for component_id in expected:
            self.assertEqual(
                components[component_id]["state_topic"],
                "wifire_kamin/wifire_kamin/statistics",
            )

    def test_statistics_components_have_expected_device_classes(self) -> None:
        components = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.7.0",
        )["components"]

        self.assertEqual(
            components["wifire_kamin_statistics_latest_burn"][
                "device_class"
            ],
            "timestamp",
        )
        self.assertEqual(
            components["wifire_kamin_statistics_average_duration"][
                "device_class"
            ],
            "duration",
        )
        self.assertEqual(
            components[
                "wifire_kamin_statistics_average_max_temperature"
            ]["device_class"],
            "temperature",
        )

    def test_payload_contains_month_and_three_season_components(self) -> None:
        components = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.8.0",
        )["components"]
        expected_month = {
            "wifire_kamin_period_month_period",
            "wifire_kamin_period_month_burn_count",
            "wifire_kamin_period_month_total_duration",
            "wifire_kamin_period_month_average_max_temperature",
        }
        season_metrics = {
            "period",
            "burn_count",
            "total_duration",
            "average_duration",
            "average_max_temperature",
            "highest_temperature",
        }
        expected_seasons = {
            f"wifire_kamin_period_season_{number}_{metric}"
            for number in (1, 2, 3)
            for metric in season_metrics
        }
        expected = expected_month | expected_seasons

        self.assertTrue(expected.issubset(components))
        self.assertEqual(len(expected), 22)
        for component_id in expected:
            self.assertEqual(
                components[component_id]["state_topic"],
                "wifire_kamin/wifire_kamin/period_statistics",
            )

    def test_period_duration_and_temperature_classes_are_defined(self) -> None:
        components = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.8.0",
        )["components"]

        self.assertEqual(
            components["wifire_kamin_period_month_total_duration"][
                "device_class"
            ],
            "duration",
        )
        self.assertEqual(
            components[
                "wifire_kamin_period_season_1_average_max_temperature"
            ]["device_class"],
            "temperature",
        )

    def test_three_seasons_use_fixed_payload_indexes(self) -> None:
        components = build_discovery_payload(
            FakeConfig,
            self.topics,
            app_name="Bridge",
            app_version="0.8.0",
        )["components"]

        for number, index in ((1, 0), (2, 1), (3, 2)):
            template = components[
                f"wifire_kamin_period_season_{number}_burn_count"
            ]["value_template"]
            self.assertIn(f"heating_seasons[{index}]", template)


if __name__ == "__main__":
    unittest.main()
