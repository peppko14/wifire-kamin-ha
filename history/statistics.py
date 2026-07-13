# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Deterministische Statistiken aus der lokalen Abbrandhistorie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Iterable, Mapping


__version__ = "1.0.0"


class HistoryStatisticsError(ValueError):
    """Ein Historiendatensatz kann nicht verlässlich ausgewertet werden."""


@dataclass(frozen=True, slots=True)
class HistoryStatistics:
    """Zusammenfassung aller lokal gespeicherten Abbrände."""

    burn_count: int
    first_burn_start: datetime | None
    latest_burn_start: datetime | None
    total_duration_minutes: int
    average_duration_minutes: float | None
    average_max_temperature_c: float | None
    highest_temperature_c: int | None
    highest_temperature_start: datetime | None
    average_start_temperature_c: float | None
    average_end_temperature_c: float | None

    def to_dict(self) -> dict[str, object]:
        """Erzeugt eine serialisierbare Darstellung der Statistik."""
        return {
            "burn_count": self.burn_count,
            "first_burn_start": (
                self.first_burn_start.isoformat(timespec="seconds")
                if self.first_burn_start is not None
                else None
            ),
            "latest_burn_start": (
                self.latest_burn_start.isoformat(timespec="seconds")
                if self.latest_burn_start is not None
                else None
            ),
            "total_duration_minutes": self.total_duration_minutes,
            "average_duration_minutes": self.average_duration_minutes,
            "average_max_temperature_c": self.average_max_temperature_c,
            "highest_temperature_c": self.highest_temperature_c,
            "highest_temperature_start": (
                self.highest_temperature_start.isoformat(timespec="seconds")
                if self.highest_temperature_start is not None
                else None
            ),
            "average_start_temperature_c": (
                self.average_start_temperature_c
            ),
            "average_end_temperature_c": self.average_end_temperature_c,
        }


@dataclass(frozen=True, slots=True)
class _RecordMetrics:
    start: datetime
    duration_minutes: int
    max_temperature_c: int
    start_temperature_c: int
    end_temperature_c: int


def _integer(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoryStatisticsError(
            f"Historienfeld '{field}' muss eine Ganzzahl sein."
        )
    return value


def _parse_record(record: Mapping[str, object]) -> _RecordMetrics:
    start_value = record.get("start")
    if not isinstance(start_value, str):
        raise HistoryStatisticsError(
            "Historienfeld 'start' muss ein ISO-Zeitstempel sein."
        )

    try:
        start = datetime.fromisoformat(start_value)
    except ValueError as error:
        raise HistoryStatisticsError(
            "Historienfeld 'start' enthält keinen ISO-Zeitstempel."
        ) from error

    duration = _integer(record, "duration_minutes")
    maximum = _integer(record, "max_temperature_c")
    start_temperature = _integer(record, "start_temperature_c")
    end_temperature = _integer(record, "end_temperature_c")

    if duration < 0:
        raise HistoryStatisticsError(
            "Historienfeld 'duration_minutes' darf nicht negativ sein."
        )

    return _RecordMetrics(
        start=start,
        duration_minutes=duration,
        max_temperature_c=maximum,
        start_temperature_c=start_temperature,
        end_temperature_c=end_temperature,
    )


def _mean(values: list[int]) -> float:
    return round(fmean(values), 1)


def calculate_history_statistics(
    records: Iterable[Mapping[str, object]],
) -> HistoryStatistics:
    """Berechnet eine reihenfolgeunabhängige Historienstatistik."""
    metrics = [_parse_record(record) for record in records]

    if not metrics:
        return HistoryStatistics(
            burn_count=0,
            first_burn_start=None,
            latest_burn_start=None,
            total_duration_minutes=0,
            average_duration_minutes=None,
            average_max_temperature_c=None,
            highest_temperature_c=None,
            highest_temperature_start=None,
            average_start_temperature_c=None,
            average_end_temperature_c=None,
        )

    first_start = min(item.start for item in metrics)
    latest_start = max(item.start for item in metrics)
    highest_temperature = max(
        item.max_temperature_c for item in metrics
    )
    highest_start = min(
        item.start
        for item in metrics
        if item.max_temperature_c == highest_temperature
    )
    durations = [item.duration_minutes for item in metrics]

    return HistoryStatistics(
        burn_count=len(metrics),
        first_burn_start=first_start,
        latest_burn_start=latest_start,
        total_duration_minutes=sum(durations),
        average_duration_minutes=_mean(durations),
        average_max_temperature_c=_mean(
            [item.max_temperature_c for item in metrics]
        ),
        highest_temperature_c=highest_temperature,
        highest_temperature_start=highest_start,
        average_start_temperature_c=_mean(
            [item.start_temperature_c for item in metrics]
        ),
        average_end_temperature_c=_mean(
            [item.end_temperature_c for item in metrics]
        ),
    )
