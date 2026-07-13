# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-Veröffentlichung für Live-, Availability- und Archivdaten."""

from __future__ import annotations

import json
from typing import Any, Protocol

from bridge.topics import MqttTopics


__version__ = "1.0.0"


class MqttPublisherClient(Protocol):
    """Minimale publish-Schnittstelle des verwendeten MQTT-Clients."""

    def publish(
        self,
        topic: str,
        payload: str | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> Any:
        ...


class MqttPublisher:
    """Kapselt alle MQTT-Veröffentlichungen der WiFire-Bridge."""

    def __init__(
        self,
        client: MqttPublisherClient,
        topics: MqttTopics,
    ) -> None:
        self.client = client
        self.topics = topics

    def publish_availability(self, online: bool) -> None:
        """Veröffentlicht den retained Verfügbarkeitsstatus."""
        self.client.publish(
            self.topics.availability,
            payload="online" if online else "offline",
            qos=1,
            retain=True,
        )

    def publish_state(self, data: dict[str, object]) -> None:
        """Veröffentlicht die aktuellen Live-Daten."""
        payload = {
            "temperature_c": data["temperature_c"],
            "flap_percent": data["flap_percent"],
            "flap_moving": data["flap_moving"],
            "burn_time": data["burn_time"],
            "burn_total_minutes": data["burn_total_minutes"],
            "door_open": data["door_open"],
            "door_state": data["door_state"],
            "fan_raw": data["fan_raw"],
        }

        self.client.publish(
            self.topics.state,
            payload=json.dumps(payload, ensure_ascii=False),
            qos=1,
            retain=False,
        )

    def publish_archive(
        self,
        number: int,
        *,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        """Veröffentlicht Zustand und Attribute eines Archivdatensatzes."""
        self.client.publish(
            self.topics.archive_state(number),
            payload=state,
            qos=1,
            retain=True,
        )
        self.client.publish(
            self.topics.archive_attributes(number),
            payload=json.dumps(
                attributes,
                ensure_ascii=False,
            ),
            qos=1,
            retain=True,
        )
