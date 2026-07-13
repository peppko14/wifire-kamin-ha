# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Monatliche Kennzahlen aus der lokalen Abbrandhistorie."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from history.periods import CalendarMonth
from history.statistics import (
    HistoryStatistics,
    HistoryStatisticsError,
    calculate_history_statistics,
)


__version__ = "1.0.0"


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
