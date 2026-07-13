# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den WiFire-History-Manager."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from history.manager import (
    HistoryManager,
    create_default_history_manager,
)
from history.storage import HistoryStorage
from protocol.models import BurnRecord


class HistoryManagerTests(unittest.TestCase):
    def build_record(
        self,
        *,
        day: int = 22,
        temperatures: tuple[int, ...] = (22, 24, 30, 453, 205),
        incomplete: bool = False,
        archive_number: int = 1,
    ) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 4, day, 21, 23),
            temperatures_c=temperatures,
            source_archive_number=archive_number,
            active_or_incomplete=incomplete,
        )

    def test_new_record_is_imported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            result = manager.synchronize([self.build_record()])

            self.assertEqual(result.imported_count, 1)
            self.assertEqual(result.existing_count, 0)
            self.assertEqual(result.skipped_incomplete, 0)
            self.assertEqual(result.failed_records, 0)

    def test_duplicate_is_reported_as_existing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )
            record = self.build_record()

            first = manager.synchronize([record])
            second = manager.synchronize([record])

            self.assertEqual(first.imported_count, 1)
            self.assertEqual(second.imported_count, 0)
            self.assertEqual(second.existing_count, 1)

    def test_changed_archive_number_is_still_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            first = self.build_record(archive_number=1)
            second = self.build_record(archive_number=23)

            manager.synchronize([first])
            result = manager.synchronize([second])

            self.assertEqual(result.existing_count, 1)

    def test_incomplete_record_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            result = manager.synchronize(
                [self.build_record(incomplete=True)]
            )

            self.assertEqual(result.imported_count, 0)
            self.assertEqual(result.skipped_incomplete, 1)

    def test_multiple_records_are_imported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            result = manager.synchronize([
                self.build_record(day=22),
                self.build_record(
                    day=23,
                    temperatures=(25, 100, 300),
                    archive_number=2,
                ),
            ])

            self.assertEqual(result.imported_count, 2)
            self.assertEqual(result.processed_count, 2)

    def test_latest_record_returns_newest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            manager.synchronize([
                self.build_record(day=22),
                self.build_record(
                    day=23,
                    temperatures=(25, 100, 300),
                    archive_number=2,
                ),
            ])

            latest = manager.latest_record()

            self.assertIsNotNone(latest)
            self.assertEqual(
                latest["start"],
                "2026-04-23T21:23:00",
            )

    def test_empty_history_has_no_latest_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(
                HistoryStorage(Path(directory))
            )

            self.assertIsNone(manager.latest_record())

    def test_default_manager_uses_project_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            manager = create_default_history_manager(project_dir)

            self.assertEqual(
                manager.storage.directory,
                (project_dir / "data" / "history").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
