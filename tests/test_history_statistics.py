# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die Statistik der lokalen Abbrandhistorie."""

from __future__ import annotations

from datetime import datetime
import unittest

from history.statistics import (
    HistoryStatisticsError,
    calculate_history_statistics,
)


def record(
    start: str,
    *,
    duration: int,
    maximum: int,
    start_temperature: int,
    end_temperature: int,
) -> dict[str, object]:
    return {
        "start": start,
        "duration_minutes": duration,
        "max_temperature_c": maximum,
        "start_temperature_c": start_temperature,
        "end_temperature_c": end_temperature,
    }


class HistoryStatisticsTests(unittest.TestCase):
    def test_empty_history_has_neutral_statistics(self) -> None:
        statistics = calculate_history_statistics([])

        self.assertEqual(statistics.burn_count, 0)
        self.assertEqual(statistics.total_duration_minutes, 0)
        self.assertIsNone(statistics.average_duration_minutes)
        self.assertIsNone(statistics.highest_temperature_c)

    def test_statistics_are_calculated_from_all_records(self) -> None:
        statistics = calculate_history_statistics([
            record(
                "2026-01-01T20:00:00",
                duration=100,
                maximum=400,
                start_temperature=24,
                end_temperature=80,
            ),
            record(
                "2026-01-03T21:00:00",
                duration=140,
                maximum=500,
                start_temperature=28,
                end_temperature=100,
            ),
        ])

        self.assertEqual(statistics.burn_count, 2)
        self.assertEqual(statistics.total_duration_minutes, 240)
        self.assertEqual(statistics.average_duration_minutes, 120.0)
        self.assertEqual(statistics.average_max_temperature_c, 450.0)
        self.assertEqual(statistics.highest_temperature_c, 500)
        self.assertEqual(statistics.average_start_temperature_c, 26.0)
        self.assertEqual(statistics.average_end_temperature_c, 90.0)
        self.assertEqual(
            statistics.first_burn_start,
            datetime(2026, 1, 1, 20, 0),
        )
        self.assertEqual(
            statistics.latest_burn_start,
            datetime(2026, 1, 3, 21, 0),
        )

    def test_result_does_not_depend_on_input_order(self) -> None:
        first = record(
            "2026-01-01T20:00:00",
            duration=100,
            maximum=500,
            start_temperature=24,
            end_temperature=80,
        )
        second = record(
            "2026-01-03T21:00:00",
            duration=140,
            maximum=500,
            start_temperature=28,
            end_temperature=100,
        )

        forward = calculate_history_statistics([first, second])
        backward = calculate_history_statistics([second, first])

        self.assertEqual(forward, backward)
        self.assertEqual(
            forward.highest_temperature_start,
            datetime(2026, 1, 1, 20, 0),
        )

    def test_statistics_are_serializable(self) -> None:
        statistics = calculate_history_statistics([
            record(
                "2026-01-01T20:00:00",
                duration=100,
                maximum=400,
                start_temperature=24,
                end_temperature=80,
            )
        ])

        payload = statistics.to_dict()

        self.assertEqual(payload["burn_count"], 1)
        self.assertEqual(payload["first_burn_start"], "2026-01-01T20:00:00")
        self.assertEqual(
            payload["highest_temperature_start"],
            "2026-01-01T20:00:00",
        )

    def test_missing_required_field_is_rejected(self) -> None:
        with self.assertRaises(HistoryStatisticsError):
            calculate_history_statistics([
                {"start": "2026-01-01T20:00:00"}
            ])

    def test_invalid_timestamp_is_rejected(self) -> None:
        invalid = record(
            "kein-zeitstempel",
            duration=100,
            maximum=400,
            start_temperature=24,
            end_temperature=80,
        )

        with self.assertRaises(HistoryStatisticsError):
            calculate_history_statistics([invalid])

    def test_negative_duration_is_rejected(self) -> None:
        invalid = record(
            "2026-01-01T20:00:00",
            duration=-1,
            maximum=400,
            start_temperature=24,
            end_temperature=80,
        )

        with self.assertRaises(HistoryStatisticsError):
            calculate_history_statistics([invalid])


if __name__ == "__main__":
    unittest.main()
