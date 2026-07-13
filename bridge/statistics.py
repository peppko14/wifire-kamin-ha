#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Verbindet lokale Abbrandstatistiken mit der MQTT-Veröffentlichung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping, Protocol

from history.statistics import (
    HistoryStatistics,
    calculate_history_statistics,
)


__version__ = "1.0.0"


Logger = Callable[[str], None]


class HistoryProviderLike(Protocol):
    def list_history(self) -> list[dict[str, object]]:
        ...


class StatisticsPublisherLike(Protocol):
    def publish_statistics(self, statistics: HistoryStatistics) -> None:
        ...


def parse_statistics_since(value: object) -> datetime | None:
    """Liest den optionalen inklusiven Statistikfilter aus der Konfiguration."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(
            "STATISTICS_SINCE muss None oder ein ISO-Datum sein."
        )

    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "STATISTICS_SINCE erwartet YYYY-MM-DD oder einen "
            "ISO-Zeitstempel."
        ) from error


@dataclass(frozen=True, slots=True)
class HistoryStatisticsReporter:
    """Berechnet und veröffentlicht die aktuelle lokale Historienstatistik."""

    history_provider: HistoryProviderLike
    publisher: StatisticsPublisherLike
    since: datetime | None = None
    logger: Logger = print

    def refresh(self) -> HistoryStatistics:
        """Liest die Historie neu ein und veröffentlicht eine Momentaufnahme."""
        records: list[Mapping[str, object]] = self.history_provider.list_history()
        statistics = calculate_history_statistics(
            records,
            since=self.since,
        )
        self.publisher.publish_statistics(statistics)
        self.logger(
            "Historienstatistik veröffentlicht: "
            f"{statistics.burn_count} Abbrände berücksichtigt, "
            f"{statistics.excluded_record_count} ausgefiltert."
        )
        return statistics
