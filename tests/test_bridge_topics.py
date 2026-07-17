# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

import unittest

from bridge.topics import MqttTopics


class MqttTopicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = MqttTopics(
            device_id="wifire_kamin",
            discovery_prefix="homeassistant",
        )

    def test_base_topics(self) -> None:
        self.assertEqual(
            self.topics.state,
            "wifire_kamin/wifire_kamin/state",
        )
        self.assertEqual(
            self.topics.availability,
            "wifire_kamin/wifire_kamin/availability",
        )
        self.assertEqual(
            self.topics.statistics,
            "wifire_kamin/wifire_kamin/statistics",
        )
        self.assertEqual(
            self.topics.period_statistics,
            "wifire_kamin/wifire_kamin/period_statistics",
        )
        self.assertEqual(
            self.topics.dashboard_curves,
            "wifire_kamin/wifire_kamin/dashboard_curves",
        )
        self.assertEqual(
            self.topics.live_curve,
            "wifire_kamin/wifire_kamin/live_curve",
        )
        self.assertEqual(
            self.topics.controller_diagnostics,
            "wifire_kamin/wifire_kamin/controller_diagnostics",
        )
        self.assertEqual(
            self.topics.heating_failures,
            "wifire_kamin/wifire_kamin/heating_failures",
        )
        self.assertEqual(
            self.topics.heating_failure_event,
            "wifire_kamin/wifire_kamin/heating_failure_event",
        )

    def test_discovery_topics(self) -> None:
        self.assertEqual(
            self.topics.home_assistant_status,
            "homeassistant/status",
        )
        self.assertEqual(
            self.topics.device_discovery,
            "homeassistant/device/wifire_kamin/config",
        )

    def test_archive_topics(self) -> None:
        self.assertEqual(
            self.topics.archive_state(3),
            "wifire_kamin/wifire_kamin/archive/3/state",
        )
        self.assertEqual(
            self.topics.archive_attributes(3),
            "wifire_kamin/wifire_kamin/archive/3/attributes",
        )

    def test_invalid_archive_number_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.topics.archive_state(0)


if __name__ == "__main__":
    unittest.main()
