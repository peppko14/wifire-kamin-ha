#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Adaptive Abfrageintervalle der WiFire-Kamin-Bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


__version__ = "1.0.0"


NORMAL_UPDATE_INTERVAL = 60
ACTIVE_FIRE_UPDATE_INTERVAL = 10
ERROR_RETRY_INTERVAL = 300
ACTIVE_FIRE_TEMPERATURE_C = 40


@dataclass(frozen=True, slots=True)
class PollingSettings:
    """Konfiguriert die adaptive Live-Abfrage."""

    normal_update_interval: int = NORMAL_UPDATE_INTERVAL
    active_fire_update_interval: int = (
        ACTIVE_FIRE_UPDATE_INTERVAL
    )
    error_retry_interval: int = ERROR_RETRY_INTERVAL
    active_fire_temperature_c: int = (
        ACTIVE_FIRE_TEMPERATURE_C
    )

    @classmethod
    def from_config(
        cls,
        config_module: object,
    ) -> "PollingSettings":
        """Lädt optionale Werte aus dem Konfigurationsmodul."""
        return cls(
            normal_update_interval=getattr(
                config_module,
                "NORMAL_UPDATE_INTERVAL",
                NORMAL_UPDATE_INTERVAL,
            ),
            active_fire_update_interval=getattr(
                config_module,
                "ACTIVE_FIRE_UPDATE_INTERVAL",
                ACTIVE_FIRE_UPDATE_INTERVAL,
            ),
            error_retry_interval=getattr(
                config_module,
                "ERROR_RETRY_INTERVAL",
                ERROR_RETRY_INTERVAL,
            ),
            active_fire_temperature_c=getattr(
                config_module,
                "ACTIVE_FIRE_TEMPERATURE_C",
                ACTIVE_FIRE_TEMPERATURE_C,
            ),
        )


def get_next_poll_interval(
    current_state: Mapping[str, Any] | None,
    read_failed: bool,
    settings: PollingSettings,
) -> tuple[int, str]:
    """Bestimmt das nächste Live-Abfrageintervall."""
    if read_failed or current_state is None:
        return settings.error_retry_interval, "Lesefehler"

    if (
        current_state["temperature_c"]
        >= settings.active_fire_temperature_c
    ):
        return (
            settings.active_fire_update_interval,
            "aktiver Abbrand",
        )

    return settings.normal_update_interval, "Normalbetrieb"
