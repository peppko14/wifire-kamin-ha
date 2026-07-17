# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die fachliche Qualität historischer Abbrände."""

from dataclasses import replace
from datetime import datetime
import unittest

from protocol.models import BurnRecord
from protocol.quality import QualitySeverity, validate_burn_record


class BurnQualityTests(unittest.TestCase):
    def valid_record(self) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 4, 22, 21, 23),
            temperatures_c=tuple(range(20, 141)),
            source_archive_number=1,
            stage_90_minute=7,
            stage_75_minute=36,
            stage_50_minute=57,
            stage_25_minute=109,
            stage_0_minute=169,
        )

    def codes(self, record: BurnRecord) -> set[str]:
        return {
            issue.code
            for issue in validate_burn_record(record).issues
        }

    def test_plausible_complete_record_is_valid(self) -> None:
        report = validate_burn_record(self.valid_record())

        self.assertTrue(report.is_valid)
        self.assertEqual(report.status, "valid")
        self.assertEqual(report.issues, ())

    def test_old_timestamp_is_uncertain_but_valid(self) -> None:
        record = replace(
            self.valid_record(),
            start=datetime(2017, 4, 24, 1, 52),
        )
        report = validate_burn_record(record)

        self.assertTrue(report.is_valid)
        self.assertEqual(report.status, "warning")
        self.assertEqual(self.codes(record), {"timestamp_uncertain"})
        self.assertEqual(len(report.warnings), 1)
        self.assertIn(
            "ohne belegte Zeitsynchronisation",
            report.warnings[0].message,
        )

    def test_missing_start_is_invalid(self) -> None:
        report = validate_burn_record(
            replace(self.valid_record(), start=None)
        )

        self.assertFalse(report.is_valid)
        self.assertIn("start_missing", self.codes(replace(
            self.valid_record(), start=None
        )))

    def test_incomplete_record_is_invalid(self) -> None:
        record = replace(self.valid_record(), active_or_incomplete=True)

        self.assertIn("record_incomplete", self.codes(record))
        self.assertFalse(validate_burn_record(record).is_valid)

    def test_single_measurement_is_invalid(self) -> None:
        record = replace(self.valid_record(), temperatures_c=(20,))

        self.assertIn("measurement_count_too_low", self.codes(record))

    def test_unexpected_measurement_count_is_warning(self) -> None:
        record = replace(self.valid_record(), temperatures_c=(20, 30))
        report = validate_burn_record(record)

        self.assertTrue(report.is_valid)
        self.assertIn("measurement_count_unexpected", self.codes(record))

    def test_temperature_above_limit_is_invalid(self) -> None:
        values = list(self.valid_record().temperatures_c)
        values[10] = 1201
        record = replace(self.valid_record(), temperatures_c=tuple(values))

        self.assertIn("temperature_out_of_range", self.codes(record))
        self.assertFalse(validate_burn_record(record).is_valid)

    def test_temperature_below_limit_is_invalid(self) -> None:
        values = list(self.valid_record().temperatures_c)
        values[10] = -41
        record = replace(self.valid_record(), temperatures_c=tuple(values))

        self.assertIn("temperature_out_of_range", self.codes(record))

    def test_zero_archive_number_is_rejected(self) -> None:
        record = replace(self.valid_record(), source_archive_number=0)

        self.assertIn("archive_number_invalid", self.codes(record))

    def test_archive_number_above_known_ring_buffer_is_valid(self) -> None:
        record = replace(self.valid_record(), source_archive_number=24)

        self.assertTrue(validate_burn_record(record).is_valid)
        self.assertNotIn("archive_number_invalid", self.codes(record))

    def test_invalid_phase_value_is_rejected(self) -> None:
        record = replace(self.valid_record(), stage_50_minute=256)

        self.assertIn("phase_value_invalid", self.codes(record))

    def test_missing_final_phase_warns_about_unknown_duration(self) -> None:
        record = replace(self.valid_record(), stage_0_minute=None)
        report = validate_burn_record(record)

        self.assertTrue(report.is_valid)
        self.assertIn("duration_unknown", self.codes(record))

    def test_report_is_serializable(self) -> None:
        record = replace(
            self.valid_record(),
            start=datetime(2017, 4, 24, 1, 52),
        )
        payload = validate_burn_record(record).to_dict()

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(
            payload["issues"][0]["severity"],
            QualitySeverity.WARNING.value,
        )


if __name__ == "__main__":
    unittest.main()
