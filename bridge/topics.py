# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zentrale MQTT-Topics der WiFire-Kamin-Bridge."""

from __future__ import annotations

from dataclasses import dataclass




@dataclass(frozen=True, slots=True)
class MqttTopics:
    """Erzeugt alle MQTT-Topics aus Geräte-ID und Discovery-Präfix."""

    device_id: str
    discovery_prefix: str = "homeassistant"

    @property
    def base(self) -> str:
        return f"wifire_kamin/{self.device_id}"

    @property
    def state(self) -> str:
        return f"{self.base}/state"

    @property
    def availability(self) -> str:
        return f"{self.base}/availability"

    @property
    def statistics(self) -> str:
        return f"{self.base}/statistics"

    @property
    def period_statistics(self) -> str:
        return f"{self.base}/period_statistics"

    @property
    def dashboard_curves(self) -> str:
        return f"{self.base}/dashboard_curves"

    @property
    def live_curve(self) -> str:
        return f"{self.base}/live_curve"

    @property
    def home_assistant_status(self) -> str:
        return f"{self.discovery_prefix}/status"

    @property
    def device_discovery(self) -> str:
        return (
            f"{self.discovery_prefix}/device/"
            f"{self.device_id}/config"
        )

    def archive_state(self, number: int) -> str:
        self._validate_archive_number(number)
        return f"{self.base}/archive/{number}/state"

    def archive_attributes(self, number: int) -> str:
        self._validate_archive_number(number)
        return f"{self.base}/archive/{number}/attributes"

    @staticmethod
    def _validate_archive_number(number: int) -> None:
        if number < 1:
            raise ValueError(
                "Archivnummer muss mindestens 1 sein."
            )
