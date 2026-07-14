# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Monatliche Kennzahlen aus der lokalen Abbrandhistorie."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from history.periods import CalendarMonth, HeatingSeason
from history.statistics import (
    HistoryStatistics,
    HistoryStatisticsError,
    calculate_history_statistics,
)




@dataclass(frozen=True, slots=True)
class MonthlyStatistics:
    """Statistische Zusammenfassung eines Kalendermonats."""

    month: CalendarMonth
    statistics: HistoryStatistics

    def to_dict(self) -> dict[str, object]:
        """Erzeugt eine flache, serialisierbare Darstellung."""
        return {
            "period": self.month.key,
            "period_start": self.month.start.isoformat(timespec="seconds"),
            "period_end_exclusive": self.month.end_exclusive.isoformat(
                timespec="seconds"
            ),
            **self.statistics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HeatingSeasonStatistics:
    """Statistische Zusammenfassung einer Heizsaison."""

    season: HeatingSeason
    statistics: HistoryStatistics

    def to_dict(self) -> dict[str, object]:
        """Erzeugt eine flache, serialisierbare Darstellung."""
        return {
            "period": self.season.key,
            "label": self.season.label,
            "period_start": self.season.start.isoformat(timespec="seconds"),
            "period_end_exclusive": self.season.end_exclusive.isoformat(
                timespec="seconds"
            ),
            **self.statistics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CurrentPeriodStatistics:
    """Momentaufnahme des aktuellen Monats und dreier Heizsaisons."""

    month: MonthlyStatistics
    seasons: tuple[
        HeatingSeasonStatistics,
        HeatingSeasonStatistics,
        HeatingSeasonStatistics,
    ]

    def __post_init__(self) -> None:
        if len(self.seasons) != 3:
            raise ValueError("Es müssen genau drei Heizsaisons vorliegen.")

    @property
    def season(self) -> HeatingSeasonStatistics:
        """Aktuelle Heizsaison als bequemer Kompatibilitätszugriff."""
        return self.seasons[0]

    def to_dict(self) -> dict[str, object]:
        """Erzeugt die gemeinsame MQTT-Darstellung."""
        return {
            "current_month": self.month.to_dict(),
            "heating_seasons": [item.to_dict() for item in self.seasons],
        }


def _record_start(record: Mapping[str, object]) -> datetime:
    value = record.get("start")
    if not isinstance(value, str):
        raise HistoryStatisticsError(
            "Historienfeld 'start' muss ein ISO-Zeitstempel sein."
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise HistoryStatisticsError(
            "Historienfeld 'start' enthält keinen ISO-Zeitstempel."
        ) from error


def calculate_monthly_statistics(
    records: Iterable[Mapping[str, object]],
    *,
    since: datetime | None = None,
) -> tuple[MonthlyStatistics, ...]:
    """Gruppiert gültige Abbrände chronologisch nach Kalendermonat."""
    groups: dict[CalendarMonth, list[Mapping[str, object]]] = defaultdict(list)

    for record in records:
        start = _record_start(record)
        if since is not None and start < since:
            continue
        groups[CalendarMonth.from_datetime(start)].append(record)

    return tuple(
        MonthlyStatistics(
            month=month,
            statistics=calculate_history_statistics(groups[month]),
        )
        for month in sorted(groups)
    )


def calculate_heating_season_statistics(
    records: Iterable[Mapping[str, object]],
    *,
    since: datetime | None = None,
) -> tuple[HeatingSeasonStatistics, ...]:
    """Gruppiert gültige Abbrände chronologisch nach Heizsaison."""
    groups: dict[HeatingSeason, list[Mapping[str, object]]] = defaultdict(list)

    for record in records:
        start = _record_start(record)
        if since is not None and start < since:
            continue
        groups[HeatingSeason.from_datetime(start)].append(record)

    return tuple(
        HeatingSeasonStatistics(
            season=season,
            statistics=calculate_history_statistics(groups[season]),
        )
        for season in sorted(groups)
    )


def calculate_current_period_statistics(
    records: Iterable[Mapping[str, object]],
    *,
    at: datetime,
    since: datetime | None = None,
) -> CurrentPeriodStatistics:
    """Berechnet feste Momentaufnahmen für die Perioden eines Zeitpunkts."""
    materialized = list(records)
    current_month = CalendarMonth.from_datetime(at)
    current_season = HeatingSeason.from_datetime(at)
    target_seasons = tuple(
        HeatingSeason(current_season.start_year - offset)
        for offset in range(3)
    )

    monthly = {
        item.month: item
        for item in calculate_monthly_statistics(materialized, since=since)
    }
    seasons = {
        item.season: item
        for item in calculate_heating_season_statistics(
            materialized,
            since=since,
        )
    }

    season_values = tuple(
        seasons.get(
            season,
            HeatingSeasonStatistics(
                season=season,
                statistics=calculate_history_statistics([]),
            ),
        )
        for season in target_seasons
    )

    return CurrentPeriodStatistics(
        month=monthly.get(
            current_month,
            MonthlyStatistics(
                month=current_month,
                statistics=calculate_history_statistics([]),
            ),
        ),
        seasons=(
            season_values[0],
            season_values[1],
            season_values[2],
        ),
    )
