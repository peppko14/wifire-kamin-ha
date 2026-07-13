# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die lokale Historienablage."""

from datetime import datetime
from pathlib import Path
import json
import tempfile
import unittest

from history.storage import (
    HISTORY_SCHEMA_VERSION,
    HistoryStorage,
    HistoryStorageError,
)
from protocol.models import BurnRecord


class HistoryStorageTests(unittest.TestCase):
    def build_record(
        self,
        *,
        archive_number: int | None = 1,
        incomplete: bool = False,
    ) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 4, 22, 21, 23),
            temperatures_c=(22, 24, 30, 453, 205),
            source_archive_number=archive_number,
            stage_90_minute=7,
            stage_75_minute=36,
            stage_50_minute=57,
            stage_25_minute=109,
            stage_0_minute=169,
            active_or_incomplete=incomplete,
        )

    def test_save_creates_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            path, created = storage.save(self.build_record())

            self.assertTrue(created)
            self.assertTrue(path.exists())

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                data["schema_version"],
                HISTORY_SCHEMA_VERSION,
            )
            self.assertEqual(data["max_temperature_c"], 453)
            self.assertEqual(len(data["burn_id"]), 64)

    def test_duplicate_is_not_written_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            first_path, first_created = storage.save(
                self.build_record(archive_number=1)
            )
            second_path, second_created = storage.save(
                self.build_record(archive_number=23)
            )

            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(first_path, second_path)
            self.assertEqual(
                len(list(Path(directory).glob("*.json"))),
                1,
            )

    def test_incomplete_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))

            with self.assertRaises(ValueError):
                storage.save(
                    self.build_record(incomplete=True)
                )

    def test_list_records_sorts_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))

            older = self.build_record()
            newer = BurnRecord(
                start=datetime(2026, 4, 23, 10, 0),
                temperatures_c=(25, 100, 300),
                source_archive_number=2,
            )

            storage.save(older)
            storage.save(newer)

            records = storage.list_records()

            self.assertEqual(
                records[0]["start"],
                "2026-04-23T10:00:00",
            )
            self.assertEqual(
                records[1]["start"],
                "2026-04-22T21:23:00",
            )

    def test_invalid_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            broken = Path(directory) / "broken.json"
            broken.write_text("{broken", encoding="utf-8")

            with self.assertRaises(HistoryStorageError):
                storage.load_file(broken)

    def test_temporary_file_is_not_left_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            storage.save(self.build_record())

            self.assertEqual(
                list(Path(directory).glob("*.tmp")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
