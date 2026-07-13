# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für das lesende Historien-Audit."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from history.audit import audit_history
from history.diagnostics import HistoryDiagnosticStorage
from history.storage import HistoryStorage
from protocol.models import BurnRecord
from protocol.quality import validate_burn_record


def record(year: int = 2026) -> BurnRecord:
    return BurnRecord(
        start=datetime(year, 4, 22, 21, 23),
        temperatures_c=tuple(range(20, 141)),
        source_archive_number=1,
        stage_0_minute=169,
    )


class HistoryAuditTests(unittest.TestCase):
    def test_empty_directories_are_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = audit_history(root / "history", root / "diagnostics")

            self.assertTrue(audit.storage_is_healthy)
            self.assertEqual(audit.regular_file_count, 0)
            self.assertEqual(audit.diagnostic_file_count, 0)

    def test_valid_and_warning_records_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = HistoryStorage(root / "history")
            storage.save(record())
            storage.save(record(2017))

            audit = audit_history(root / "history", root / "diagnostics")

            self.assertEqual(audit.valid_count, 1)
            self.assertEqual(audit.warning_count, 1)
            self.assertEqual(audit.schema_versions, (("2", 2),))
            self.assertEqual(
                audit.warning_codes,
                (("timestamp_uncertain", 1),),
            )

    def test_unreadable_history_file_marks_storage_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history"
            history.mkdir()
            (history / "broken.json").write_text("{broken", encoding="utf-8")

            audit = audit_history(history, root / "diagnostics")

            self.assertFalse(audit.storage_is_healthy)
            self.assertEqual(audit.regular_unreadable_count, 1)

    def test_diagnostic_reasons_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = HistoryDiagnosticStorage(root / "diagnostics")
            incomplete = BurnRecord(
                start=datetime(2026, 7, 13, 20, 0),
                temperatures_c=(24, 30, 45),
                source_archive_number=1,
                active_or_incomplete=True,
            )
            storage.save(incomplete, validate_burn_record(incomplete))

            audit = audit_history(root / "history", root / "diagnostics")

            self.assertEqual(audit.diagnostic_readable_count, 1)
            self.assertIn(("record_incomplete", 1), audit.diagnostic_codes)

    def test_payload_is_json_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = audit_history(root / "history", root / "diagnostics")

            self.assertEqual(audit.to_dict()["storage_is_healthy"], True)


if __name__ == "__main__":
    unittest.main()
