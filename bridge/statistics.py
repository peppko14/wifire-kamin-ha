#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Verbindet lokale Abbrandstatistiken mit der MQTT-Veröffentlichung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from bridge.logging_setup import log_warning
from history.period_statistics import (
    CurrentPeriodStatistics,
    calculate_current_period_statistics,
)
from history.statistics import (
    HistoryStatistics,
    calculate_history_statistics,
)
from history.storage import HistoryReadResult




Logger = Callable[[str], None]


class HistoryProviderLike(Protocol):
    def read_history(self) -> HistoryReadResult:
        ...


class StatisticsPublisherLike(Protocol):
    def publish_statistics(self, statistics: HistoryStatistics) -> None:
        ...

    def publish_period_statistics(
        self,
        statistics: CurrentPeriodStatistics,
    ) -> None:
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
    now: Callable[[], datetime] = datetime.now

    def refresh(self) -> HistoryStatistics | None:
        """Liest die Historie neu ein und veröffentlicht eine Momentaufnahme."""
        result = self.history_provider.read_history()
        for issue in result.issues:
            log_warning(
                self.logger,
                "Historien-Datei für Statistik übersprungen: "
                f"{issue.path.name}: {issue.message}"
            )

        if not result.records and result.issues:
            log_warning(
                self.logger,
                "Historienstatistik nicht veröffentlicht: keine lesbare "
                "Historien-Datei; retained Werte bleiben unverändert."
            )
            return None

        records = list(result.records)
        statistics = calculate_history_statistics(
            records,
            since=self.since,
        )
        self.publisher.publish_statistics(statistics)
        periods = calculate_current_period_statistics(
            records,
            at=self.now(),
            since=self.since,
        )
        self.publisher.publish_period_statistics(periods)
        self.logger(
            "Historienstatistik veröffentlicht: "
            f"{statistics.burn_count} Abbrände berücksichtigt, "
            f"{statistics.excluded_record_count} ausgefiltert; "
            f"Monat {periods.month.month.key}, "
            "Heizsaisons "
            f"{', '.join(item.season.label for item in periods.seasons)}."
        )
        return statistics
