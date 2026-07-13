# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die zentrale fachliche Abbranddauer."""

from __future__ import annotations

from datetime import datetime
import unittest

from protocol.duration import (
    DurationValueError,
    calculate_duration_minutes,
    unwrap_phase_minutes,
)
from protocol.models import BurnRecord


class DurationTests(unittest.TestCase):
    def test_regular_stage_zero_is_duration(self) -> None:
        duration = calculate_duration_minutes(
            stage_90_minute=7,
            stage_75_minute=36,
            stage_50_minute=57,
            stage_25_minute=109,
            stage_0_minute=169,
        )

        self.assertEqual(duration, 169)

    def test_byte_overflow_is_unwrapped(self) -> None:
        duration = calculate_duration_minutes(
            stage_90_minute=11,
            stage_75_minute=79,
            stage_50_minute=122,
            stage_25_minute=201,
            stage_0_minute=5,
        )

        self.assertEqual(duration, 261)

    def test_missing_stage_zero_has_no_duration(self) -> None:
        duration = calculate_duration_minutes(
            stage_90_minute=10,
            stage_75_minute=40,
            stage_50_minute=70,
            stage_25_minute=90,
            stage_0_minute=None,
        )

        self.assertIsNone(duration)

    def test_invalid_phase_value_is_rejected(self) -> None:
        with self.assertRaises(DurationValueError):
            unwrap_phase_minutes((10, 40, 300))


class BurnRecordDurationTests(unittest.TestCase):
    def record(self, stage_zero: int | None) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 1, 1, 20, 0),
            temperatures_c=(24, 100, 400, 80),
            stage_90_minute=11,
            stage_75_minute=79,
            stage_50_minute=122,
            stage_25_minute=201,
            stage_0_minute=stage_zero,
        )

    def test_measurement_count_is_not_used_as_duration(self) -> None:
        record = self.record(5)

        self.assertEqual(record.measurement_count, 4)
        self.assertEqual(record.duration_minutes, 261)
        self.assertEqual(record.duration_source, "stage_0_unwrapped")

    def test_missing_duration_is_serialized_as_null(self) -> None:
        payload = self.record(None).to_history_dict()

        self.assertEqual(payload["measurement_count"], 4)
        self.assertIsNone(payload["duration_minutes"])
        self.assertIsNone(payload["duration_source"])


if __name__ == "__main__":
    unittest.main()
