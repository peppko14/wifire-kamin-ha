# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zentrale Datenmodelle für Live- und Archivdaten."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from protocol.duration import (
    DURATION_SOURCE_STAGE_0,
    calculate_duration_minutes,
)


@dataclass(frozen=True, slots=True)
class LiveStatus:
    """Dekodierter Live-Status der FireControls-WiFire-Steuerung."""

    temperature_c: int
    flap_percent: int
    flap_moving: bool
    burn_hours: int
    burn_minutes: int
    burn_total_minutes: int
    door_open: bool
    fan_raw: int
    status_raw: int
    raw: str

    @property
    def burn_time(self) -> str:
        """Abbrenndauer im Format H:MM."""
        return f"{self.burn_hours}:{self.burn_minutes:02d}"

    @property
    def door_state(self) -> str:
        """Lesbarer Türzustand."""
        return "offen" if self.door_open else "geschlossen"

    def to_mqtt_dict(self) -> dict[str, object]:
        """Erzeugt die kompakte MQTT-Darstellung."""
        return {
            "temperature_c": self.temperature_c,
            "flap_percent": self.flap_percent,
            "flap_moving": self.flap_moving,
            "burn_time": self.burn_time,
            "burn_total_minutes": self.burn_total_minutes,
            "door_open": self.door_open,
            "door_state": self.door_state,
            "fan_raw": self.fan_raw,
        }


@dataclass(frozen=True, slots=True)
class BurnRecord:
    """Dekodierter, abgeschlossener oder unvollständiger Abbrand."""

    start: datetime | None
    temperatures_c: tuple[int, ...]
    source_archive_number: int | None = None
    stage_90_minute: int | None = None
    stage_75_minute: int | None = None
    stage_50_minute: int | None = None
    stage_25_minute: int | None = None
    stage_0_minute: int | None = None
    active_or_incomplete: bool = False
    raw: str | None = None

    @property
    def measurement_count(self) -> int:
        """Anzahl gespeicherter Temperaturmesspunkte."""
        return len(self.temperatures_c)

    @property
    def duration_minutes(self) -> int | None:
        """Dauer bis zur Klappenstellung 0 %, inklusive Byte-Überläufen."""
        return calculate_duration_minutes(
            stage_90_minute=self.stage_90_minute,
            stage_75_minute=self.stage_75_minute,
            stage_50_minute=self.stage_50_minute,
            stage_25_minute=self.stage_25_minute,
            stage_0_minute=self.stage_0_minute,
        )

    @property
    def duration_source(self) -> str | None:
        """Kennzeichnet die fachliche Quelle der berechneten Dauer."""
        if self.duration_minutes is None:
            return None
        return DURATION_SOURCE_STAGE_0

    @property
    def start_temperature_c(self) -> int | None:
        """Erste gemessene Temperatur."""
        if not self.temperatures_c:
            return None
        return self.temperatures_c[0]

    @property
    def end_temperature_c(self) -> int | None:
        """Letzte gemessene Temperatur."""
        if not self.temperatures_c:
            return None
        return self.temperatures_c[-1]

    @property
    def max_temperature_c(self) -> int | None:
        """Höchste gemessene Temperatur."""
        if not self.temperatures_c:
            return None
        return max(self.temperatures_c)

    @property
    def max_temperature_minute(self) -> int | None:
        """Minute des ersten Auftretens der Maximaltemperatur."""
        maximum = self.max_temperature_c
        if maximum is None:
            return None
        return self.temperatures_c.index(maximum)

    @property
    def is_complete(self) -> bool:
        """True, wenn der Datensatz als abgeschlossen gilt."""
        return (
            self.start is not None
            and bool(self.temperatures_c)
            and not self.active_or_incomplete
        )

    def to_history_dict(self) -> dict[str, object]:
        """Erzeugt eine serialisierbare Darstellung für die Historie."""
        return {
            "start": (
                self.start.isoformat(timespec="seconds")
                if self.start is not None
                else None
            ),
            "source_archive_number": self.source_archive_number,
            "measurement_count": self.measurement_count,
            "duration_minutes": self.duration_minutes,
            "duration_source": self.duration_source,
            "start_temperature_c": self.start_temperature_c,
            "end_temperature_c": self.end_temperature_c,
            "max_temperature_c": self.max_temperature_c,
            "max_temperature_minute": self.max_temperature_minute,
            "stage_90_minute": self.stage_90_minute,
            "stage_75_minute": self.stage_75_minute,
            "stage_50_minute": self.stage_50_minute,
            "stage_25_minute": self.stage_25_minute,
            "stage_0_minute": self.stage_0_minute,
            "temperatures_c": list(self.temperatures_c),
            "active_or_incomplete": self.active_or_incomplete,
        }
