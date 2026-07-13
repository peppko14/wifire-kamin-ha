#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.statistics."""

from __future__ import annotations

from datetime import datetime
import unittest

from bridge.statistics import (
    HistoryStatisticsReporter,
    parse_statistics_since,
)
from history.statistics import HistoryStatistics
from history.period_statistics import CurrentPeriodStatistics


def record(start: str, maximum: int) -> dict[str, object]:
    return {
        "start": start,
        "max_temperature_c": maximum,
        "start_temperature_c": 24,
        "end_temperature_c": 100,
        "stage_90_minute": 10,
        "stage_75_minute": 40,
        "stage_50_minute": 80,
        "stage_25_minute": 120,
        "stage_0_minute": 180,
    }


class FakeHistoryProvider:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.calls = 0

    def list_history(self) -> list[dict[str, object]]:
        self.calls += 1
        return self.records


class FakePublisher:
    def __init__(self) -> None:
        self.statistics: list[HistoryStatistics] = []
        self.period_statistics: list[CurrentPeriodStatistics] = []

    def publish_statistics(self, statistics: HistoryStatistics) -> None:
        self.statistics.append(statistics)

    def publish_period_statistics(
        self,
        statistics: CurrentPeriodStatistics,
    ) -> None:
        self.period_statistics.append(statistics)


class StatisticsSinceTests(unittest.TestCase):
    def test_none_and_empty_string_disable_filter(self) -> None:
        self.assertIsNone(parse_statistics_since(None))
        self.assertIsNone(parse_statistics_since(""))

    def test_iso_date_is_inclusive_midnight(self) -> None:
        self.assertEqual(
            parse_statistics_since("2026-01-01"),
            datetime(2026, 1, 1),
        )

    def test_invalid_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_statistics_since("kein-datum")


class HistoryStatisticsReporterTests(unittest.TestCase):
    def test_refresh_loads_filters_and_publishes_statistics(self) -> None:
        provider = FakeHistoryProvider([
            record("2017-04-24T01:52:00", 352),
            record("2026-04-22T21:23:00", 453),
        ])
        publisher = FakePublisher()
        messages: list[str] = []
        reporter = HistoryStatisticsReporter(
            history_provider=provider,
            publisher=publisher,
            since=datetime(2026, 1, 1),
            logger=messages.append,
            now=lambda: datetime(2026, 4, 30),
        )

        statistics = reporter.refresh()

        self.assertEqual(provider.calls, 1)
        self.assertEqual(statistics.source_record_count, 2)
        self.assertEqual(statistics.burn_count, 1)
        self.assertEqual(statistics.excluded_record_count, 1)
        self.assertEqual(publisher.statistics, [statistics])
        self.assertEqual(len(publisher.period_statistics), 1)
        periods = publisher.period_statistics[0]
        self.assertEqual(periods.month.month.key, "2026-04")
        self.assertEqual(periods.month.statistics.burn_count, 1)
        self.assertEqual(periods.season.season.label, "2025/2026")
        self.assertEqual(periods.season.statistics.burn_count, 1)
        self.assertEqual(
            [item.season.label for item in periods.seasons],
            ["2025/2026", "2024/2025", "2023/2024"],
        )
        self.assertTrue(any("1 Abbrände" in message for message in messages))

    def test_empty_history_is_published_as_neutral_statistics(self) -> None:
        publisher = FakePublisher()
        reporter = HistoryStatisticsReporter(
            history_provider=FakeHistoryProvider([]),
            publisher=publisher,
            logger=lambda message: None,
            now=lambda: datetime(2026, 7, 13),
        )

        statistics = reporter.refresh()

        self.assertEqual(statistics.burn_count, 0)
        self.assertEqual(publisher.statistics, [statistics])
        periods = publisher.period_statistics[0]
        self.assertEqual(periods.month.month.key, "2026-07")
        self.assertEqual(periods.month.statistics.burn_count, 0)
        self.assertEqual(periods.season.season.label, "2026/2027")
        self.assertEqual(periods.season.statistics.burn_count, 0)
        self.assertEqual(
            [item.season.label for item in periods.seasons],
            ["2026/2027", "2025/2026", "2024/2025"],
        )


if __name__ == "__main__":
    unittest.main()
