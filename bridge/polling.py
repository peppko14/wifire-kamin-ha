#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Adaptive Abfrageintervalle der WiFire-Kamin-Bridge."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from protocol.models import LiveStatus




NORMAL_UPDATE_INTERVAL = 60
ACTIVE_FIRE_UPDATE_INTERVAL = 10
ERROR_RETRY_INTERVAL = 300
ACTIVE_FIRE_TEMPERATURE_C = 40
LIVE_RETRY_COUNT = 2
LIVE_RETRY_DELAY = 2


LiveReader = Callable[[], str]
LiveDecoder = Callable[[str], LiveStatus]
Sleeper = Callable[[int | float], None]
RunningCheck = Callable[[], bool]
Logger = Callable[[str], None]


def _sleep(seconds: int | float) -> None:
    time.sleep(seconds)


@dataclass(frozen=True, slots=True)
class LivePoller:
    """Liest einen Live-Datensatz mit begrenzten Wiederholungen."""

    reader: LiveReader
    decoder: LiveDecoder
    retry_count: int = LIVE_RETRY_COUNT
    retry_delay_seconds: int | float = LIVE_RETRY_DELAY
    sleeper: Sleeper = _sleep
    is_running: RunningCheck = lambda: True
    logger: Logger = print

    def __post_init__(self) -> None:
        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or self.retry_count < 1
        ):
            raise ValueError("retry_count muss mindestens 1 sein.")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or self.retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds muss nichtnegativ sein."
            )

    def poll(self) -> LiveStatus:
        """Gibt den dekodierten Live-Zustand zurück."""
        for attempt in range(1, self.retry_count + 1):
            try:
                return self.decoder(self.reader())
            except (OSError, ValueError) as error:
                if attempt >= self.retry_count or not self.is_running():
                    raise

                self.logger(
                    f"Live-Abfrage Versuch {attempt}/"
                    f"{self.retry_count} fehlgeschlagen: {error}; "
                    "neuer Versuch "
                    f"in {self.retry_delay_seconds} Sekunden."
                )
                self.sleeper(self.retry_delay_seconds)

                if not self.is_running():
                    raise

        raise RuntimeError("Live-Abfrage endete ohne Ergebnis.")


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
    live_retry_count: int = LIVE_RETRY_COUNT
    live_retry_delay_seconds: int | float = LIVE_RETRY_DELAY

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
            live_retry_count=getattr(
                config_module,
                "LIVE_RETRY_COUNT",
                LIVE_RETRY_COUNT,
            ),
            live_retry_delay_seconds=getattr(
                config_module,
                "LIVE_RETRY_DELAY",
                LIVE_RETRY_DELAY,
            ),
        )


def get_next_poll_interval(
    current_state: LiveStatus | None,
    read_failed: bool,
    settings: PollingSettings,
) -> tuple[int, str]:
    """Bestimmt das nächste Live-Abfrageintervall."""
    if read_failed or current_state is None:
        return settings.error_retry_interval, "Lesefehler"

    if (
        current_state.temperature_c
        >= settings.active_fire_temperature_c
    ):
        return (
            settings.active_fire_update_interval,
            "aktiver Abbrand",
        )

    return settings.normal_update_interval, "Normalbetrieb"
