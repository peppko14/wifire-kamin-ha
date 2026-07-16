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


class FakeFanConfig(FakeConfig):
    ENABLE_FAN_ENTITY = True


class SlowPollingConfig(FakeConfig):
    NORMAL_UPDATE_INTERVAL = 120


class ExplicitExpiryConfig(FakeConfig):
    LIVE_EXPIRE_AFTER = 45


class DisabledExpiryConfig(FakeConfig):
    LIVE_EXPIRE_AFTER = None


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = MqttTopics(
            device_id=FakeConfig.DEVICE_ID,
            discovery_prefix="homeassistant",
        )

    def build_payload(
        self,
        config: type[FakeConfig] = FakeConfig,
    ) -> dict[str, object]:
        return build_discovery_payload(
            config,
            self.topics,
            app_name="WiFire-Kamin MQTT Bridge",
            app_version="0.12.2",
        )

    def test_payload_contains_device_metadata(self) -> None:
        payload = self.build_payload()

        self.assertEqual(payload["device"]["name"], "WiFire-Kamin")
        self.assertEqual(payload["device"]["model"], "WiFire")

    def test_payload_contains_live_components(self) -> None:
        components = self.build_payload()["components"]

        self.assertIn("wifire_kamin_temperature", components)
        self.assertIn("wifire_kamin_door", components)

    def test_live_components_use_bridge_availability(self) -> None:
        components = self.build_payload()["components"]
        live_component_ids = {
            "wifire_kamin_temperature",
            "wifire_kamin_flap",
            "wifire_kamin_burn_time",
            "wifire_kamin_burn_minutes",
            "wifire_kamin_door",
            "wifire_kamin_flap_moving",
        }

        for component_id in live_component_ids:
            component = components[component_id]
            self.assertEqual(
                component["availability_topic"],
                self.topics.availability,
            )
            self.assertEqual(component["payload_available"], "online")
            self.assertEqual(component["payload_not_available"], "offline")

    def test_fan_component_is_optional(self) -> None:
        components = self.build_payload()["components"]

        self.assertNotIn("wifire_kamin_fan_raw", components)

    def test_optional_fan_uses_bridge_availability(self) -> None:
        components = self.build_payload(FakeFanConfig)["components"]
        component = components["wifire_kamin_fan_raw"]

        self.assertEqual(
            component["availability_topic"],
            self.topics.availability,
        )
        self.assertEqual(component["payload_available"], "online")
        self.assertEqual(component["payload_not_available"], "offline")

    def test_live_components_expire_after_default_interval(self) -> None:
        components = self.build_payload()["components"]
        live_component_ids = {
            "wifire_kamin_temperature",
            "wifire_kamin_flap",
            "wifire_kamin_burn_time",
            "wifire_kamin_burn_minutes",
            "wifire_kamin_door",
            "wifire_kamin_flap_moving",
        }

        for component_id in live_component_ids:
            self.assertEqual(components[component_id]["expire_after"], 180)

    def test_optional_fan_uses_same_expire_after(self) -> None:
        components = self.build_payload(FakeFanConfig)["components"]

        self.assertEqual(
            components["wifire_kamin_fan_raw"]["expire_after"],
            180,
        )

    def test_default_expiry_follows_normal_polling_interval(self) -> None:
        components = self.build_payload(SlowPollingConfig)["components"]

        self.assertEqual(
            components["wifire_kamin_temperature"]["expire_after"],
            360,
        )

    def test_explicit_expiry_and_disable_are_supported(self) -> None:
        explicit_components = self.build_payload(ExplicitExpiryConfig)[
            "components"
        ]
        disabled_components = self.build_payload(DisabledExpiryConfig)[
            "components"
        ]

        self.assertEqual(
            explicit_components["wifire_kamin_temperature"][
                "expire_after"
            ],
            45,
        )
        self.assertNotIn(
            "expire_after",
            disabled_components["wifire_kamin_temperature"],
        )

    def test_invalid_expiry_is_rejected(self) -> None:
        for invalid_value in (True, 0, -1, "180"):
            invalid_config = type(
                "InvalidExpiryConfig",
                (FakeConfig,),
                {"LIVE_EXPIRE_AFTER": invalid_value},
            )

            with self.subTest(value=invalid_value):
                with self.assertRaises(ValueError):
                    self.build_payload(invalid_config)

    def test_payload_has_no_global_availability(self) -> None:
        payload = self.build_payload()

        self.assertNotIn("availability_topic", payload)
        self.assertNotIn("payload_available", payload)
        self.assertNotIn("payload_not_available", payload)

    def test_all_components_have_stable_default_entity_id(self) -> None:
        components = self.build_payload()["components"]

        for component_id, component in components.items():
            self.assertEqual(
                component["default_entity_id"],
                f"{component['platform']}.{component_id}",
            )

    def test_payload_contains_three_archive_components(self) -> None:
        components = self.build_payload()["components"]

        for number in (1, 2, 3):
            self.assertIn(f"wifire_kamin_archive_{number}", components)

    def test_retained_history_components_ignore_bridge_availability(
        self,
    ) -> None:
        components = self.build_payload()["components"]
        persistent_component_ids = {
            component_id
            for component_id in components
            if component_id.startswith("wifire_kamin_archive_")
            or component_id.startswith("wifire_kamin_statistics_")
            or component_id.startswith("wifire_kamin_period_")
            or component_id == "wifire_kamin_dashboard_curves"
        }

        self.assertTrue(persistent_component_ids)
        for component_id in persistent_component_ids:
            component = components[component_id]
            self.assertNotIn("availability_topic", component)
            self.assertNotIn("payload_available", component)
            self.assertNotIn("payload_not_available", component)
            self.assertNotIn("expire_after", component)

    def test_payload_contains_dashboard_curve_component(self) -> None:
        components = self.build_payload()["components"]

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
        components = self.build_payload()["components"]
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
        components = self.build_payload()["components"]

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
        components = self.build_payload()["components"]
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
        components = self.build_payload()["components"]

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
        components = self.build_payload()["components"]

        for number, index in ((1, 0), (2, 1), (3, 2)):
            template = components[
                f"wifire_kamin_period_season_{number}_burn_count"
            ]["value_template"]
            self.assertIn(f"heating_seasons[{index}]", template)


if __name__ == "__main__":
    unittest.main()
