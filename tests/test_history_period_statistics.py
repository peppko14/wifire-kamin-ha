# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für monatliche Historienstatistiken."""

from __future__ import annotations

from datetime import datetime
import unittest

from history.period_statistics import calculate_monthly_statistics
from history.statistics import HistoryStatisticsError


def record(start: str, maximum: int, duration: int = 120) -> dict[str, object]:
    return {
        "start": start,
        "max_temperature_c": maximum,
        "start_temperature_c": 24,
        "end_temperature_c": 80,
        "stage_90_minute": 10,
        "stage_75_minute": 40,
        "stage_50_minute": 70,
        "stage_25_minute": 90,
        "stage_0_minute": duration,
    }


class MonthlyStatisticsTests(unittest.TestCase):
    def test_empty_history_has_no_months(self) -> None:
        self.assertEqual(calculate_monthly_statistics([]), ())

    def test_records_are_grouped_and_sorted_by_month(self) -> None:
        result = calculate_monthly_statistics([
            record("2026-03-02T20:00:00", 500),
            record("2026-02-20T21:00:00", 400),
            record("2026-03-10T19:00:00", 600),
        ])

        self.assertEqual([item.month.key for item in result], ["2026-02", "2026-03"])
        self.assertEqual(result[0].statistics.burn_count, 1)
        self.assertEqual(result[1].statistics.burn_count, 2)
        self.assertEqual(result[1].statistics.highest_temperature_c, 600)

    def test_monthly_duration_uses_existing_duration_logic(self) -> None:
        result = calculate_monthly_statistics([
            record("2026-03-02T20:00:00", 500, duration=120),
            record("2026-03-10T19:00:00", 600, duration=180),
        ])

        statistics = result[0].statistics
        self.assertEqual(statistics.total_duration_minutes, 300)
        self.assertEqual(statistics.average_duration_minutes, 150.0)

    def test_since_filter_is_inclusive(self) -> None:
        result = calculate_monthly_statistics(
            [
                record("2026-02-28T23:59:59", 400),
                record("2026-03-01T00:00:00", 500),
            ],
            since=datetime(2026, 3, 1),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].month.key, "2026-03")

    def test_serialized_result_contains_period_and_statistics(self) -> None:
        result = calculate_monthly_statistics([
            record("2026-03-02T20:00:00", 500)
        ])[0].to_dict()

        self.assertEqual(result["period"], "2026-03")
        self.assertEqual(result["period_start"], "2026-03-01T00:00:00")
        self.assertEqual(result["burn_count"], 1)

    def test_invalid_start_is_rejected(self) -> None:
        invalid = record("not-a-date", 500)

        with self.assertRaises(HistoryStatisticsError):
            calculate_monthly_statistics([invalid])


if __name__ == "__main__":
    unittest.main()
