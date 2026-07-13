# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für stabile WiFire-Abbrand-IDs."""

from datetime import datetime
import unittest

from history.identifiers import (
    build_burn_id,
    build_canonical_burn_text,
)
from protocol.models import BurnRecord


class BurnIdentifierTests(unittest.TestCase):
    def build_record(
        self,
        *,
        archive_number: int | None = 1,
        temperatures: tuple[int, ...] = (22, 24, 30, 453, 205),
    ) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 4, 22, 21, 23),
            temperatures_c=temperatures,
            source_archive_number=archive_number,
        )

    def test_identical_records_have_identical_ids(self) -> None:
        first = self.build_record()
        second = self.build_record()

        self.assertEqual(
            build_burn_id(first),
            build_burn_id(second),
        )

    def test_archive_number_does_not_change_id(self) -> None:
        first = self.build_record(archive_number=1)
        second = self.build_record(archive_number=23)

        self.assertEqual(
            build_burn_id(first),
            build_burn_id(second),
        )

    def test_different_temperature_curve_changes_id(self) -> None:
        first = self.build_record()
        second = self.build_record(
            temperatures=(22, 24, 31, 453, 205),
        )

        self.assertNotEqual(
            build_burn_id(first),
            build_burn_id(second),
        )

    def test_canonical_text_is_stable(self) -> None:
        record = self.build_record()

        self.assertEqual(
            build_canonical_burn_text(record),
            "2026-04-22T21:23|5|22,24,30,453,205",
        )

    def test_missing_start_is_rejected(self) -> None:
        record = BurnRecord(
            start=None,
            temperatures_c=(22, 24),
        )

        with self.assertRaises(ValueError):
            build_burn_id(record)

    def test_missing_temperatures_are_rejected(self) -> None:
        record = BurnRecord(
            start=datetime(2026, 4, 22, 21, 23),
            temperatures_c=(),
        )

        with self.assertRaises(ValueError):
            build_burn_id(record)


if __name__ == "__main__":
    unittest.main()
