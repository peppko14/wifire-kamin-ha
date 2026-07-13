# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die getrennte Historien-Diagnoseablage."""

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from history.diagnostics import (
    DIAGNOSTIC_SCHEMA_VERSION,
    HistoryDiagnosticError,
    HistoryDiagnosticStorage,
)
from protocol.models import BurnRecord
from protocol.quality import validate_burn_record


class HistoryDiagnosticStorageTests(unittest.TestCase):
    def incomplete_record(self) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 7, 13, 20, 0),
            temperatures_c=(24, 30, 45),
            source_archive_number=1,
            active_or_incomplete=True,
            raw="aacc3355",
        )

    def test_incomplete_record_is_stored_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryDiagnosticStorage(Path(directory))
            record = self.incomplete_record()

            path, created, diagnostic_id = storage.save(
                record,
                validate_burn_record(record),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(created)
            self.assertEqual(
                payload["schema_version"],
                DIAGNOSTIC_SCHEMA_VERSION,
            )
            self.assertEqual(payload["diagnostic_id"], diagnostic_id)
            self.assertEqual(payload["quality"]["status"], "invalid")
            self.assertEqual(payload["record"]["raw"], "aacc3355")

    def test_same_record_is_not_written_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryDiagnosticStorage(Path(directory))
            record = self.incomplete_record()
            report = validate_burn_record(record)

            first_path, first_created, first_id = storage.save(record, report)
            second_path, second_created, second_id = storage.save(record, report)

            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(first_path, second_path)
            self.assertEqual(first_id, second_id)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)

    def test_started_record_id_ignores_changing_measurements(self) -> None:
        storage = HistoryDiagnosticStorage(Path("diagnostics"))
        first = self.incomplete_record()
        second = BurnRecord(
            start=first.start,
            temperatures_c=(24, 30, 45, 60),
            source_archive_number=first.source_archive_number,
            active_or_incomplete=True,
            raw="different",
        )

        self.assertEqual(
            storage.build_diagnostic_id(first),
            storage.build_diagnostic_id(second),
        )

    def test_missing_start_uses_raw_data_for_identity(self) -> None:
        storage = HistoryDiagnosticStorage(Path("diagnostics"))
        first = BurnRecord(None, (), source_archive_number=1, raw="first")
        second = BurnRecord(None, (), source_archive_number=1, raw="second")

        self.assertNotEqual(
            storage.build_diagnostic_id(first),
            storage.build_diagnostic_id(second),
        )

    def test_success_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryDiagnosticStorage(Path(directory))
            record = self.incomplete_record()
            storage.save(record, validate_burn_record(record))

            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_invalid_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryDiagnosticStorage(Path(directory))
            path = Path(directory) / "broken.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(HistoryDiagnosticError):
                storage.load_file(path)

    def test_unsupported_schema_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryDiagnosticStorage(Path(directory))
            record = self.incomplete_record()
            path, _, _ = storage.save(record, validate_burn_record(record))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(HistoryDiagnosticError):
                storage.load_file(path)


if __name__ == "__main__":
    unittest.main()
