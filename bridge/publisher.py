# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-Veröffentlichung für Live-, Availability- und Archivdaten."""

from __future__ import annotations

import json
from typing import Any, Protocol

from bridge.dashboard import DashboardCurveSnapshot
from bridge.live_curve import (
    LiveCurveSession,
    build_live_curve_mqtt_payload,
)
from bridge.topics import MqttTopics
from history.period_statistics import CurrentPeriodStatistics
from history.statistics import HistoryStatistics
from protocol.models import LiveStatus




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

    def publish_state(self, data: LiveStatus) -> None:
        """Veröffentlicht die aktuellen Live-Daten."""
        self.client.publish(
            self.topics.state,
            payload=json.dumps(
                data.to_mqtt_dict(),
                ensure_ascii=False,
            ),
            qos=1,
            retain=False,
        )

    def publish_live_curve(
        self,
        session: LiveCurveSession | None,
    ) -> None:
        """Veröffentlicht die begrenzte laufende Brennkurve nicht retained."""
        self.client.publish(
            self.topics.live_curve,
            payload=json.dumps(
                build_live_curve_mqtt_payload(session),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
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

    def publish_statistics(self, statistics: HistoryStatistics) -> None:
        """Veröffentlicht die lokale Historienstatistik retained."""
        self.client.publish(
            self.topics.statistics,
            payload=json.dumps(
                statistics.to_dict(),
                ensure_ascii=False,
            ),
            qos=1,
            retain=True,
        )

    def publish_period_statistics(
        self,
        statistics: CurrentPeriodStatistics,
    ) -> None:
        """Veröffentlicht aktuelle Monats- und Saisonwerte retained."""
        self.client.publish(
            self.topics.period_statistics,
            payload=json.dumps(
                statistics.to_dict(),
                ensure_ascii=False,
            ),
            qos=1,
            retain=True,
        )

    def publish_dashboard_snapshot(
        self,
        snapshot: DashboardCurveSnapshot,
    ) -> None:
        """Veröffentlicht den kompakten Kurvenvergleich retained."""
        self.client.publish(
            self.topics.dashboard_curves,
            payload=snapshot.to_json(),
            qos=1,
            retain=True,
        )
