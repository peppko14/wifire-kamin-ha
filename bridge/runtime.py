#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Ablaufsteuerung der WiFire-Kamin-Bridge."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from bridge.polling import (
    PollingSettings,
    get_next_poll_interval,
)
from protocol.models import LiveStatus


__version__ = "2.0.0"


RunningCheck = Callable[[], bool]
Sleeper = Callable[[int | float], None]
Clock = Callable[[], float]
Logger = Callable[[str], None]
StateCallback = Callable[[LiveStatus], None]


class LivePollerLike(Protocol):
    def poll(self) -> LiveStatus:
        ...


class PublisherLike(Protocol):
    def publish_availability(self, online: bool) -> None:
        ...

    def publish_state(self, data: LiveStatus) -> None:
        ...


class ArchiveSynchronizerLike(Protocol):
    def synchronize(self) -> None:
        ...


class ScheduleLike(Protocol):
    def is_due(self, now: float) -> bool:
        ...

    def mark_updated(self, now: float) -> None:
        ...


@dataclass(slots=True)
class BridgeRuntime:
    """Führt Live-Abfrage, Archivabgleich und Wartezeit aus."""

    live_poller: LivePollerLike
    publisher: PublisherLike
    archive_synchronizer: ArchiveSynchronizerLike
    archive_schedule: ScheduleLike
    polling_settings: PollingSettings
    sleeper: Sleeper
    is_running: RunningCheck
    offline_after_failures: int
    on_state: StateCallback
    monotonic: Clock = time.monotonic
    logger: Logger = print
    latest_state: LiveStatus | None = field(
        default=None,
        init=False,
    )
    consecutive_failures: int = field(
        default=0,
        init=False,
    )
    availability_online: bool = field(
        default=True,
        init=False,
    )

    def run(self) -> None:
        """Führt Zyklen aus, solange die Bridge aktiv ist."""
        while self.is_running():
            self.run_cycle()

    def run_cycle(self) -> tuple[int, str]:
        """Führt genau einen vollständigen Bridge-Zyklus aus."""
        read_failed = False

        try:
            data = self.live_poller.poll()

            self.latest_state = data
            self.on_state(data)
            self.consecutive_failures = 0

            if not self.availability_online:
                self.publisher.publish_availability(True)
                self.availability_online = True

            self.publisher.publish_state(data)

            self.logger(
                f"{data.temperature_c} °C | "
                f"{data.flap_percent} % | "
                f"{data.burn_time} | "
                f"Tür {data.door_state}"
            )

        except (OSError, ValueError) as error:
            read_failed = True
            self.consecutive_failures += 1

            self.logger(
                f"Lesefehler {self.consecutive_failures}/"
                f"{self.offline_after_failures}: {error}"
            )

            if (
                self.consecutive_failures
                >= self.offline_after_failures
                and self.availability_online
            ):
                self.publisher.publish_availability(False)
                self.availability_online = False

                self.logger(
                    "WiFire-Kamin wird als offline gemeldet."
                )

        now = self.monotonic()

        if self.archive_schedule.is_due(now):
            self.archive_synchronizer.synchronize()
            self.archive_schedule.mark_updated(
                self.monotonic()
            )

        next_interval, interval_reason = (
            get_next_poll_interval(
                self.latest_state,
                read_failed,
                self.polling_settings,
            )
        )

        self.logger(
            f"Nächste Abfrage in {next_interval} Sekunden "
            f"({interval_reason})."
        )

        self.sleeper(next_interval)
        return next_interval, interval_reason
