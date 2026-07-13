# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den Adapter des bestehenden Archivdecoders."""

from datetime import datetime
import unittest

from protocol.adapters import archive_record_to_burn_record
from protocol.models import BurnRecord


class FakeArchiveRecord:
    def __init__(self) -> None:
        self.archive_number = 7
        self.timestamp = datetime(2026, 4, 7, 23, 18)
        self.stage_90_minute = 2
        self.stage_75_minute = 41
        self.stage_50_minute = 51
        self.stage_25_minute = 104
        self.stage_0_minute = 164
        self.temperatures = [48, 69, 119, 620, 272]
        self.active_or_incomplete = False
        self.raw = "aacc3355"


class ArchiveAdapterTests(unittest.TestCase):
    def test_adapter_returns_burn_record(self) -> None:
        result = archive_record_to_burn_record(
            FakeArchiveRecord()
        )

        self.assertIsInstance(result, BurnRecord)

    def test_adapter_maps_core_fields(self) -> None:
        result = archive_record_to_burn_record(
            FakeArchiveRecord()
        )

        self.assertEqual(
            result.start,
            datetime(2026, 4, 7, 23, 18),
        )
        self.assertEqual(result.source_archive_number, 7)
        self.assertEqual(
            result.temperatures_c,
            (48, 69, 119, 620, 272),
        )

    def test_adapter_maps_stage_minutes(self) -> None:
        result = archive_record_to_burn_record(
            FakeArchiveRecord()
        )

        self.assertEqual(result.stage_90_minute, 2)
        self.assertEqual(result.stage_75_minute, 41)
        self.assertEqual(result.stage_50_minute, 51)
        self.assertEqual(result.stage_25_minute, 104)
        self.assertEqual(result.stage_0_minute, 164)

    def test_adapter_preserves_status_and_raw_data(self) -> None:
        result = archive_record_to_burn_record(
            FakeArchiveRecord()
        )

        self.assertFalse(result.active_or_incomplete)
        self.assertEqual(result.raw, "aacc3355")

    def test_converted_record_exposes_calculated_values(self) -> None:
        result = archive_record_to_burn_record(
            FakeArchiveRecord()
        )

        self.assertEqual(result.max_temperature_c, 620)
        self.assertEqual(result.max_temperature_minute, 3)
        self.assertTrue(result.is_complete)


if __name__ == "__main__":
    unittest.main()
