#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Seltene, retained veröffentlichte WiFire-Gerätediagnose."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from bridge.logging_setup import log_warning
from protocol.device_diagnostics import (
    AlarmList,
    ControllerTime,
    DeviceDiagnosticsReadError,
)


Logger = Callable[[str], None]
Sleeper = Callable[[int | float], None]
Clock = Callable[[], datetime]
RunningCheck = Callable[[], bool]


class DeviceDiagnosticsClientLike(Protocol):
    """Benötigte lesende Schnittstelle des Diagnoseclients."""

    def read_controller_time(self) -> ControllerTime:
        ...

    def read_alarms(self) -> AlarmList:
        ...


class DeviceDiagnosticsPublisherLike(Protocol):
    """Benötigte retained MQTT-Veröffentlichungen."""

    def publish_controller_diagnostics(
        self,
        payload: dict[str, object],
    ) -> None:
        ...

    def publish_heating_failures(
        self,
        payload: dict[str, object],
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class DeviceDiagnosticsRefreshResult:
    """Ergebnis einer unabhängig behandelten Diagnoseaktualisierung."""

    controller_time_published: bool
    heating_failures_published: bool


def local_now() -> datetime:
    """Liefert die lokale Raspberry-Zeit mit UTC-Versatz."""
    return datetime.now().astimezone()


def build_controller_diagnostics_payload(
    controller_time: ControllerTime,
    observed_at: datetime,
) -> dict[str, object]:
    """Erzeugt einen stabilen retained Payload der Steuerungsuhr."""
    local_observed_at = (
        observed_at
        if observed_at.tzinfo is not None
        else observed_at.astimezone()
    )
    controller_with_zone = controller_time.value.replace(
        tzinfo=local_observed_at.tzinfo
    )
    offset_minutes = round(
        (
            controller_with_zone - local_observed_at
        ).total_seconds()
        / 60,
        1,
    )
    return {
        "schema_version": 1,
        "observed_at": local_observed_at.isoformat(timespec="seconds"),
        "controller_time": controller_with_zone.isoformat(
            timespec="minutes"
        ),
        "offset_minutes": offset_minutes,
        "month_flags": controller_time.month_flags,
    }


def build_heating_failures_payload(
    alarms: AlarmList,
    observed_at: datetime,
) -> dict[str, object]:
    """Erzeugt einen Payload ohne unbekannte oder rohe Telegrammbytes."""
    entries = [
        {
            "occurred_on": (
                entry.occurred_on.isoformat()
                if entry.occurred_on is not None
                else None
            ),
            "code": entry.code,
            "label": entry.label,
        }
        for entry in alarms.entries
    ]
    latest_date = next(
        (
            entry["occurred_on"]
            for entry in entries
            if entry["occurred_on"] is not None
        ),
        None,
    )
    return {
        "schema_version": 1,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "count": len(entries),
        "latest_date": latest_date,
        "entries": entries,
    }


@dataclass(frozen=True, slots=True)
class DeviceDiagnosticsReporter:
    """Liest zwei Endpunkte selten und veröffentlicht sie unabhängig."""

    client: DeviceDiagnosticsClientLike
    publisher: DeviceDiagnosticsPublisherLike
    request_delay_seconds: int | float = 2
    sleeper: Sleeper = time.sleep
    clock: Clock = local_now
    is_running: RunningCheck = lambda: True
    logger: Logger = print

    def __post_init__(self) -> None:
        if (
            isinstance(self.request_delay_seconds, bool)
            or not isinstance(self.request_delay_seconds, (int, float))
            or self.request_delay_seconds < 0
        ):
            raise ValueError(
                "request_delay_seconds darf nicht negativ sein."
            )

    def refresh(self) -> DeviceDiagnosticsRefreshResult:
        """Aktualisiert Uhr und Heizfehler mit getrennter Fehlerbehandlung."""
        controller_published = False
        alarms_published = False

        if not self.is_running():
            return DeviceDiagnosticsRefreshResult(False, False)

        try:
            controller_time = self.client.read_controller_time()
            self.publisher.publish_controller_diagnostics(
                build_controller_diagnostics_payload(
                    controller_time,
                    self.clock(),
                )
            )
            controller_published = True
        except (DeviceDiagnosticsReadError, OSError, ValueError) as error:
            log_warning(
                self.logger,
                "Steuerungszeit konnte nicht aktualisiert werden: "
                f"{error}",
            )

        if self.request_delay_seconds:
            self.sleeper(self.request_delay_seconds)

        if not self.is_running():
            return DeviceDiagnosticsRefreshResult(
                controller_time_published=controller_published,
                heating_failures_published=False,
            )

        try:
            alarms = self.client.read_alarms()
            self.publisher.publish_heating_failures(
                build_heating_failures_payload(
                    alarms,
                    self.clock(),
                )
            )
            alarms_published = True
        except (DeviceDiagnosticsReadError, OSError, ValueError) as error:
            log_warning(
                self.logger,
                "Heizfehler konnten nicht aktualisiert werden: "
                f"{error}",
            )

        self.logger(
            "Gerätediagnose aktualisiert: "
            f"Steuerungszeit={'ja' if controller_published else 'nein'}, "
            f"Heizfehler={'ja' if alarms_published else 'nein'}."
        )
        return DeviceDiagnosticsRefreshResult(
            controller_time_published=controller_published,
            heating_failures_published=alarms_published,
        )
