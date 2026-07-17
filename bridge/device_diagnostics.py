#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Seltene, retained veröffentlichte WiFire-Steuerungszeit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from bridge.logging_setup import log_warning
from protocol.device_diagnostics import (
    ControllerTime,
    DeviceDiagnosticsReadError,
)


Logger = Callable[[str], None]
Clock = Callable[[], datetime]


class ControllerDiagnosticsClientLike(Protocol):
    """Benötigte lesende Schnittstelle des Diagnoseclients."""

    def read_controller_time(self) -> ControllerTime:
        ...


class ControllerDiagnosticsPublisherLike(Protocol):
    """Benötigte retained MQTT-Veröffentlichung."""

    def publish_controller_diagnostics(
        self,
        payload: dict[str, object],
    ) -> None:
        ...


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


@dataclass(frozen=True, slots=True)
class ControllerDiagnosticsReporter:
    """Liest und veröffentlicht ausschließlich die Steuerungszeit."""

    client: ControllerDiagnosticsClientLike
    publisher: ControllerDiagnosticsPublisherLike
    clock: Clock = local_now
    logger: Logger = print

    def refresh(self) -> bool:
        """Aktualisiert die retained Steuerungszeit bei erfolgreichem Lesen."""
        try:
            controller_time = self.client.read_controller_time()
            self.publisher.publish_controller_diagnostics(
                build_controller_diagnostics_payload(
                    controller_time,
                    self.clock(),
                )
            )
        except (DeviceDiagnosticsReadError, OSError, ValueError) as error:
            log_warning(
                self.logger,
                "Steuerungszeit konnte nicht aktualisiert werden: "
                f"{error}",
            )
            return False

        self.logger("Steuerungszeit-Diagnose aktualisiert.")
        return True
