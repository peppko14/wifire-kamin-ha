# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die MQTT-unabhängige Ringpuffer-Synchronisation."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from history.manager import HistorySyncResult
from history.sync import (
    ArchiveSyncSettings,
    synchronize_archives,
)
from protocol.models import BurnRecord
from protocol.archive import ArchiveReadCancelled


def result(
    *,
    imported: tuple[str, ...] = (),
    existing: tuple[str, ...] = (),
    incomplete: int = 0,
    failed: int = 0,
) -> HistorySyncResult:
    return HistorySyncResult(imported, existing, incomplete, failed)


class FakeManager:
    def __init__(self, results: list[HistorySyncResult]) -> None:
        self.results = list(results)
        self.records: list[BurnRecord] = []

    def synchronize(self, records: list[BurnRecord]) -> HistorySyncResult:
        self.records.extend(records)
        return self.results.pop(0)


def burn(number: int, *, incomplete: bool = False) -> BurnRecord:
    return BurnRecord(
        start=datetime(2026, 4, number, 20, 0),
        temperatures_c=(20, 100, 300),
        source_archive_number=number,
        active_or_incomplete=incomplete,
    )


def empty_archive(number: int) -> SimpleNamespace:
    return SimpleNamespace(
        archive_number=number,
        timestamp=None,
        stage_90_minute=None,
        stage_75_minute=None,
        stage_50_minute=None,
        stage_25_minute=None,
        stage_0_minute=None,
        temperatures=[],
        active_or_incomplete=True,
        raw="aacc3355",
    )


def archive_record(number: int) -> SimpleNamespace:
    return SimpleNamespace(
        archive_number=number,
        timestamp=datetime(2026, 4, number, 20, 0),
        stage_90_minute=5,
        stage_75_minute=30,
        stage_50_minute=60,
        stage_25_minute=120,
        stage_0_minute=180,
        temperatures=[20, 100, 300],
        active_or_incomplete=False,
        raw="aacc3355",
    )


class ArchiveSyncTests(unittest.TestCase):
    def settings(
        self,
        *,
        first: int = 1,
        last: int = 3,
        max_read_errors: int = 3,
    ) -> ArchiveSyncSettings:
        return ArchiveSyncSettings(
            live_url="http://192.168.0.1/direct/00",
            first_archive=first,
            last_archive=last,
            archive_delay_seconds=10,
            max_consecutive_read_errors=max_read_errors,
        )

    def test_settings_reject_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            ArchiveSyncSettings(
                live_url="http://192.168.0.1/direct/00",
                first_archive=23,
                last_archive=1,
            ).validate()

    def test_settings_reject_archive_delay_below_ten_seconds(self) -> None:
        with self.assertRaises(ValueError):
            ArchiveSyncSettings(
                live_url="http://192.168.0.1/direct/00",
                archive_delay_seconds=9.9,
            ).validate()

    def test_default_reader_uses_shared_archive_client(self) -> None:
        manager = FakeManager([result(existing=("id-1",))])

        def running() -> bool:
            return True

        def sleeper(seconds: float) -> None:
            pass

        def logger(message: str) -> None:
            pass

        with patch("history.sync.ArchiveClient") as client_type:
            client_type.return_value.read_raw.return_value = "1"

            synchronize_archives(
                manager,  # type: ignore[arg-type]
                self.settings(last=1),
                decoder=lambda raw: archive_record(int(raw)),
                record_adapter=lambda record: burn(record.archive_number),
                sleeper=sleeper,
                logger=logger,
                is_running=running,
            )

        client_type.assert_called_once_with(
            live_url="http://192.168.0.1/direct/00",
            request_timeout=15,
            retry_count=3,
            retry_delay_seconds=10.0,
            sleeper=sleeper,
            logger=logger,
            is_running=running,
        )
        client_type.return_value.read_raw.assert_called_once_with(1)

    def test_new_records_are_saved_immediately_and_scan_continues(self) -> None:
        manager = FakeManager([
            result(imported=("id-1",)),
            result(imported=("id-2",)),
        ])
        calls: list[int] = []
        sleeps: list[float] = []

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=2),
            raw_reader=lambda number: calls.append(number) or str(number),
            decoder=lambda raw: archive_record(int(raw)),
            record_adapter=lambda record: burn(record.archive_number),
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(manager.records), 2)
        self.assertEqual(sync.sync_result.imported_count, 2)
        self.assertEqual(sleeps, [10])

    def test_existing_record_stops_scan_without_another_delay(self) -> None:
        manager = FakeManager([
            result(imported=("id-1",)),
            result(existing=("id-2",)),
        ])
        calls: list[int] = []
        sleeps: list[float] = []

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=3),
            raw_reader=lambda number: calls.append(number) or str(number),
            decoder=lambda raw: archive_record(int(raw)),
            record_adapter=lambda record: burn(record.archive_number),
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        self.assertEqual(calls, [1, 2])
        self.assertEqual(sleeps, [10])
        self.assertTrue(sync.stopped_on_existing)
        self.assertEqual(sync.archives_examined, 2)

    def test_incomplete_record_is_logged_and_scan_continues(self) -> None:
        manager = FakeManager([
            result(incomplete=1),
            result(existing=("id-2",)),
        ])
        messages: list[str] = []

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=2),
            raw_reader=lambda number: str(number),
            decoder=lambda raw: archive_record(int(raw)),
            record_adapter=lambda record: burn(
                record.archive_number,
                incomplete=True,
            ),
            sleeper=lambda seconds: None,
            logger=messages.append,
        )

        self.assertEqual(sync.sync_result.skipped_incomplete, 1)
        self.assertTrue(any("unvollständig" in message for message in messages))

    def test_first_empty_slot_stops_without_diagnostic_or_delay(self) -> None:
        manager = FakeManager([])
        calls: list[int] = []
        sleeps: list[float] = []

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(first=24, last=30),
            raw_reader=lambda number: calls.append(number) or str(number),
            decoder=lambda raw: empty_archive(int(raw)),
            record_adapter=lambda record: self.fail(
                "Ein leerer Platz darf nicht adaptiert werden."
            ),
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        self.assertEqual(calls, [24])
        self.assertEqual(sleeps, [])
        self.assertEqual(manager.records, [])
        self.assertEqual(sync.records_read, 0)
        self.assertEqual(sync.empty_archives, 1)
        self.assertTrue(sync.stopped_on_empty)
        self.assertFalse(sync.stopped_on_existing)
        self.assertEqual(sync.sync_result.skipped_incomplete, 0)

    def test_read_error_does_not_discard_already_saved_record(self) -> None:
        manager = FakeManager([result(imported=("id-1",))])

        def reader(number: int) -> str:
            if number == 2:
                raise RuntimeError("WLAN unterbrochen")
            return str(number)

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=2),
            raw_reader=reader,
            decoder=lambda raw: archive_record(int(raw)),
            record_adapter=lambda record: burn(record.archive_number),
            sleeper=lambda seconds: None,
            logger=lambda message: None,
        )

        self.assertEqual(sync.sync_result.imported_count, 1)
        self.assertEqual(sync.read_failures, 1)
        self.assertEqual(len(manager.records), 1)

    def test_consecutive_read_error_limit_stops_the_scan(self) -> None:
        manager = FakeManager([])
        calls: list[int] = []
        sleeps: list[float] = []

        def reader(number: int) -> str:
            calls.append(number)
            raise RuntimeError("offline")

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=10, max_read_errors=3),
            raw_reader=reader,
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(sleeps, [10, 10])
        self.assertEqual(sync.read_failures, 3)
        self.assertTrue(sync.stopped_on_read_error_limit)

    def test_cancelled_read_is_not_counted_as_failure(self) -> None:
        manager = FakeManager([])

        def reader(number: int) -> str:
            raise ArchiveReadCancelled("Dienst wird beendet")

        sync = synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=3),
            raw_reader=reader,
            sleeper=lambda seconds: None,
            logger=lambda message: None,
        )

        self.assertTrue(sync.stopped_on_request)
        self.assertEqual(sync.read_failures, 0)
        self.assertEqual(sync.archives_examined, 1)
        self.assertEqual(manager.records, [])

    def test_stop_request_prevents_the_next_archive_request(self) -> None:
        manager = FakeManager([result(imported=("id-1",))])
        running = True
        calls: list[int] = []

        def stop_during_delay(seconds: float) -> None:
            nonlocal running
            running = False

        synchronize_archives(
            manager,  # type: ignore[arg-type]
            self.settings(last=3),
            raw_reader=lambda number: calls.append(number) or str(number),
            decoder=lambda raw: archive_record(int(raw)),
            record_adapter=lambda record: burn(record.archive_number),
            sleeper=stop_during_delay,
            logger=lambda message: None,
            is_running=lambda: running,
        )

        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
