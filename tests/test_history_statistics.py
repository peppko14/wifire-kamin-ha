# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die Statistik der lokalen Abbrandhistorie."""

from __future__ import annotations

from datetime import datetime
import unittest

from history.statistics import (
    HistoryStatisticsError,
    calculate_burn_duration_minutes,
    calculate_history_statistics,
    unwrap_phase_minutes,
)


def record(
    start: str,
    *,
    maximum: int,
    start_temperature: int,
    end_temperature: int,
    stages: tuple[int | None, ...] = (10, 40, 70, 90, 120),
) -> dict[str, object]:
    return {
        "start": start,
        "max_temperature_c": maximum,
        "start_temperature_c": start_temperature,
        "end_temperature_c": end_temperature,
        "stage_90_minute": stages[0],
        "stage_75_minute": stages[1],
        "stage_50_minute": stages[2],
        "stage_25_minute": stages[3],
        "stage_0_minute": stages[4],
    }


class PhaseDurationTests(unittest.TestCase):
    def test_regular_phase_values_need_no_unwrapping(self) -> None:
        self.assertEqual(
            unwrap_phase_minutes((7, 36, 57, 109, 169)),
            (7, 36, 57, 109, 169),
        )

    def test_single_byte_overflow_is_unwrapped(self) -> None:
        self.assertEqual(
            unwrap_phase_minutes((11, 79, 122, 201, 5)),
            (11, 79, 122, 201, 261),
        )

    def test_multiple_late_overflows_are_unwrapped(self) -> None:
        self.assertEqual(
            unwrap_phase_minutes((7, 27, 199, 19, 79)),
            (7, 27, 199, 275, 335),
        )

    def test_missing_intermediate_phase_is_supported(self) -> None:
        self.assertEqual(
            unwrap_phase_minutes((None, 44, 123, None, 69)),
            (None, 44, 123, None, 325),
        )

    def test_missing_final_phase_has_no_known_duration(self) -> None:
        data = record(
            "2026-01-01T20:00:00",
            maximum=400,
            start_temperature=24,
            end_temperature=80,
            stages=(10, 40, 70, 90, None),
        )
        self.assertIsNone(calculate_burn_duration_minutes(data))


class HistoryStatisticsTests(unittest.TestCase):
    def test_empty_history_has_neutral_statistics(self) -> None:
        statistics = calculate_history_statistics([])

        self.assertEqual(statistics.source_record_count, 0)
        self.assertEqual(statistics.burn_count, 0)
        self.assertEqual(statistics.total_duration_minutes, 0)
        self.assertIsNone(statistics.average_duration_minutes)

    def test_statistics_use_unwrapped_burn_duration(self) -> None:
        statistics = calculate_history_statistics([
            record(
                "2026-01-01T20:00:00",
                maximum=400,
                start_temperature=24,
                end_temperature=80,
                stages=(7, 36, 57, 109, 169),
            ),
            record(
                "2026-01-03T21:00:00",
                maximum=500,
                start_temperature=28,
                end_temperature=100,
                stages=(11, 79, 122, 201, 5),
            ),
        ])

        self.assertEqual(statistics.burn_count, 2)
        self.assertEqual(statistics.duration_record_count, 2)
        self.assertEqual(statistics.total_duration_minutes, 430)
        self.assertEqual(statistics.average_duration_minutes, 215.0)
        self.assertEqual(statistics.average_max_temperature_c, 450.0)
        self.assertEqual(statistics.highest_temperature_c, 500)

    def test_since_filter_is_inclusive_and_transparent(self) -> None:
        statistics = calculate_history_statistics(
            [
                record(
                    "2017-04-24T01:52:00",
                    maximum=352,
                    start_temperature=20,
                    end_temperature=100,
                ),
                record(
                    "2026-01-01T00:00:00",
                    maximum=500,
                    start_temperature=24,
                    end_temperature=90,
                ),
            ],
            since=datetime(2026, 1, 1),
        )

        self.assertEqual(statistics.source_record_count, 2)
        self.assertEqual(statistics.burn_count, 1)
        self.assertEqual(statistics.excluded_record_count, 1)
        self.assertEqual(
            statistics.first_burn_start,
            datetime(2026, 1, 1),
        )

    def test_missing_duration_is_excluded_only_from_duration_metrics(self) -> None:
        statistics = calculate_history_statistics([
            record(
                "2026-01-01T20:00:00",
                maximum=400,
                start_temperature=24,
                end_temperature=80,
                stages=(10, 40, 70, 90, None),
            )
        ])

        self.assertEqual(statistics.burn_count, 1)
        self.assertEqual(statistics.duration_record_count, 0)
        self.assertEqual(statistics.total_duration_minutes, 0)
        self.assertIsNone(statistics.average_duration_minutes)
        self.assertEqual(statistics.highest_temperature_c, 400)

    def test_result_does_not_depend_on_input_order(self) -> None:
        first = record(
            "2026-01-01T20:00:00",
            maximum=500,
            start_temperature=24,
            end_temperature=80,
        )
        second = record(
            "2026-01-03T21:00:00",
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
                maximum=400,
                start_temperature=24,
                end_temperature=80,
            )
        ])

        payload = statistics.to_dict()

        self.assertEqual(payload["source_record_count"], 1)
        self.assertEqual(payload["burn_count"], 1)
        self.assertEqual(payload["first_burn_start"], "2026-01-01T20:00:00")

    def test_missing_required_temperature_is_rejected(self) -> None:
        invalid = record(
            "2026-01-01T20:00:00",
            maximum=400,
            start_temperature=24,
            end_temperature=80,
        )
        del invalid["max_temperature_c"]

        with self.assertRaises(HistoryStatisticsError):
            calculate_history_statistics([invalid])

    def test_invalid_phase_value_is_rejected(self) -> None:
        invalid = record(
            "2026-01-01T20:00:00",
            maximum=400,
            start_temperature=24,
            end_temperature=80,
        )
        invalid["stage_0_minute"] = 300

        with self.assertRaises(HistoryStatisticsError):
            calculate_history_statistics([invalid])


if __name__ == "__main__":
    unittest.main()
