# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Deterministische Statistiken aus der lokalen Abbrandhistorie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Iterable, Mapping

from protocol.duration import (
    DurationValueError,
    calculate_duration_minutes,
    unwrap_phase_minutes as _unwrap_phase_minutes,
)


__version__ = "1.2.0"

PHASE_FIELDS = (
    "stage_90_minute",
    "stage_75_minute",
    "stage_50_minute",
    "stage_25_minute",
    "stage_0_minute",
)


class HistoryStatisticsError(ValueError):
    """Ein Historiendatensatz kann nicht verlässlich ausgewertet werden."""


@dataclass(frozen=True, slots=True)
class HistoryStatistics:
    """Zusammenfassung ausgewählter lokal gespeicherter Abbrände."""

    source_record_count: int
    burn_count: int
    excluded_record_count: int
    duration_record_count: int
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
            "source_record_count": self.source_record_count,
            "burn_count": self.burn_count,
            "excluded_record_count": self.excluded_record_count,
            "duration_record_count": self.duration_record_count,
            "first_burn_start": _datetime_text(self.first_burn_start),
            "latest_burn_start": _datetime_text(self.latest_burn_start),
            "total_duration_minutes": self.total_duration_minutes,
            "average_duration_minutes": self.average_duration_minutes,
            "average_max_temperature_c": self.average_max_temperature_c,
            "highest_temperature_c": self.highest_temperature_c,
            "highest_temperature_start": _datetime_text(
                self.highest_temperature_start
            ),
            "average_start_temperature_c": (
                self.average_start_temperature_c
            ),
            "average_end_temperature_c": self.average_end_temperature_c,
        }


@dataclass(frozen=True, slots=True)
class _RecordMetrics:
    start: datetime
    duration_minutes: int | None
    max_temperature_c: int
    start_temperature_c: int
    end_temperature_c: int


def _datetime_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")


def _integer(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoryStatisticsError(
            f"Historienfeld '{field}' muss eine Ganzzahl sein."
        )
    return value


def _optional_phase(record: Mapping[str, object], field: str) -> int | None:
    value = record.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoryStatisticsError(
            f"Historienfeld '{field}' muss eine Ganzzahl oder null sein."
        )
    if not 0 <= value <= 255:
        raise HistoryStatisticsError(
            f"Historienfeld '{field}' muss zwischen 0 und 255 liegen."
        )
    return value


def unwrap_phase_minutes(
    stages: Iterable[int | None],
) -> tuple[int | None, ...]:
    """Kompatibilitätszugriff auf die zentrale Dauerlogik."""
    try:
        return _unwrap_phase_minutes(stages)
    except DurationValueError as error:
        raise HistoryStatisticsError(str(error)) from error


def calculate_burn_duration_minutes(
    record: Mapping[str, object],
) -> int | None:
    """Bestimmt die vollständige Dauer aus dem entrollten stage_0-Wert."""
    stages = tuple(_optional_phase(record, field) for field in PHASE_FIELDS)
    try:
        return calculate_duration_minutes(
            stage_90_minute=stages[0],
            stage_75_minute=stages[1],
            stage_50_minute=stages[2],
            stage_25_minute=stages[3],
            stage_0_minute=stages[4],
        )
    except DurationValueError as error:
        raise HistoryStatisticsError(str(error)) from error


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

    return _RecordMetrics(
        start=start,
        duration_minutes=calculate_burn_duration_minutes(record),
        max_temperature_c=_integer(record, "max_temperature_c"),
        start_temperature_c=_integer(record, "start_temperature_c"),
        end_temperature_c=_integer(record, "end_temperature_c"),
    )


def _mean(values: list[int]) -> float:
    return round(fmean(values), 1)


def calculate_history_statistics(
    records: Iterable[Mapping[str, object]],
    *,
    since: datetime | None = None,
) -> HistoryStatistics:
    """Berechnet Statistiken, optional ab einem inklusiven Zeitpunkt."""
    all_metrics = [_parse_record(record) for record in records]
    metrics = [
        item
        for item in all_metrics
        if since is None or item.start >= since
    ]
    source_count = len(all_metrics)
    excluded_count = source_count - len(metrics)

    if not metrics:
        return HistoryStatistics(
            source_record_count=source_count,
            burn_count=0,
            excluded_record_count=excluded_count,
            duration_record_count=0,
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

    highest_temperature = max(
        item.max_temperature_c for item in metrics
    )
    durations = [
        item.duration_minutes
        for item in metrics
        if item.duration_minutes is not None
    ]

    return HistoryStatistics(
        source_record_count=source_count,
        burn_count=len(metrics),
        excluded_record_count=excluded_count,
        duration_record_count=len(durations),
        first_burn_start=min(item.start for item in metrics),
        latest_burn_start=max(item.start for item in metrics),
        total_duration_minutes=sum(durations),
        average_duration_minutes=(
            _mean(durations) if durations else None
        ),
        average_max_temperature_c=_mean(
            [item.max_temperature_c for item in metrics]
        ),
        highest_temperature_c=highest_temperature,
        highest_temperature_start=min(
            item.start
            for item in metrics
            if item.max_temperature_c == highest_temperature
        ),
        average_start_temperature_c=_mean(
            [item.start_temperature_c for item in metrics]
        ),
        average_end_temperature_c=_mean(
            [item.end_temperature_c for item in metrics]
        ),
    )
