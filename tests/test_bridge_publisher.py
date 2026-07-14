# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.publisher."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from typing import Any

from bridge.publisher import MqttPublisher
from bridge.dashboard import build_dashboard_snapshot
from bridge.topics import MqttTopics
from history.curve_analysis import analyze_curves
from history.curves import BurnCurve, CurvePoint
from history.identifiers import build_burn_id
from history.period_statistics import calculate_current_period_statistics
from history.statistics import HistoryStatistics
from protocol.models import BurnRecord


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

    def test_publish_statistics_uses_retained_json_payload(self) -> None:
        self.publisher.publish_statistics(
            HistoryStatistics(
                source_record_count=22,
                burn_count=16,
                excluded_record_count=6,
                duration_record_count=16,
                first_burn_start=datetime(2026, 2, 16, 15, 2),
                latest_burn_start=datetime(2026, 4, 22, 21, 23),
                total_duration_minutes=3298,
                average_duration_minutes=206.1,
                average_max_temperature_c=515.1,
                highest_temperature_c=665,
                highest_temperature_start=datetime(2026, 3, 26, 22, 23),
                average_start_temperature_c=38.8,
                average_end_temperature_c=281.5,
            )
        )

        self.assertEqual(len(self.client.messages), 1)
        message = self.client.messages[0]
        self.assertEqual(
            message["topic"],
            "wifire_kamin/wifire_kamin/statistics",
        )
        self.assertEqual(message["qos"], 1)
        self.assertTrue(message["retain"])

        payload = json.loads(message["payload"])
        self.assertEqual(payload["burn_count"], 16)
        self.assertEqual(payload["total_duration_minutes"], 3298)
        self.assertEqual(payload["highest_temperature_c"], 665)

    def test_publish_period_statistics_uses_retained_json_payload(self) -> None:
        periods = calculate_current_period_statistics(
            [],
            at=datetime(2026, 7, 13),
        )

        self.publisher.publish_period_statistics(periods)

        message = self.client.messages[0]
        self.assertEqual(
            message["topic"],
            "wifire_kamin/wifire_kamin/period_statistics",
        )
        self.assertEqual(message["qos"], 1)
        self.assertTrue(message["retain"])
        payload = json.loads(message["payload"])
        self.assertEqual(payload["current_month"]["period"], "2026-07")
        self.assertEqual(
            [item["label"] for item in payload["heating_seasons"]],
            ["2026/2027", "2025/2026", "2024/2025"],
        )
        self.assertEqual(payload["current_month"]["burn_count"], 0)

    def test_publish_dashboard_snapshot_uses_retained_compact_json(self) -> None:
        temperatures = (20, 100, 453)
        start = datetime(2026, 4, 22, 21, 23)
        burn_id = build_burn_id(
            BurnRecord(start=start, temperatures_c=temperatures)
        )
        curve = BurnCurve(
            burn_id=burn_id,
            start=start,
            points=tuple(
                CurvePoint(index, temperature)
                for index, temperature in enumerate(temperatures)
            ),
            quality_status="valid",
        )
        snapshot = build_dashboard_snapshot(analyze_curves((curve,)))

        self.publisher.publish_dashboard_snapshot(snapshot)

        message = self.client.messages[0]
        self.assertEqual(
            message["topic"],
            "wifire_kamin/wifire_kamin/dashboard_curves",
        )
        self.assertEqual(message["qos"], 1)
        self.assertTrue(message["retain"])
        payload = json.loads(message["payload"])
        self.assertEqual(payload["source_curve_count"], 1)
        self.assertEqual(
            tuple(payload["series"]),
            ("average", "representative", "hottest"),
        )


if __name__ == "__main__":
    unittest.main()
