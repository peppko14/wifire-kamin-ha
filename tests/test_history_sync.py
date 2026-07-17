# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die MQTT-unabhängige Ringpuffer-Synchronisation."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from history.manager import HistorySyncResult
from history.sync import (
    ArchiveSyncSettings,
    synchronize_archives,
)
from protocol.models import BurnRecord


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


class ArchiveSyncTests(unittest.TestCase):
    def settings(self, *, last: int = 3) -> ArchiveSyncSettings:
        return ArchiveSyncSettings(
            live_url="http://192.168.0.1/direct/00",
            first_archive=1,
            last_archive=last,
            archive_delay_seconds=10,
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

        def sleeper(seconds: float) -> None:
            pass

        def logger(message: str) -> None:
            pass

        with patch("history.sync.ArchiveClient") as client_type:
            client_type.return_value.read_raw.return_value = "1"

            synchronize_archives(
                manager,  # type: ignore[arg-type]
                self.settings(last=1),
                decoder=lambda raw: int(raw),
                record_adapter=lambda number: burn(number),
                sleeper=sleeper,
                logger=logger,
            )

        client_type.assert_called_once_with(
            live_url="http://192.168.0.1/direct/00",
            request_timeout=15,
            retry_count=3,
            retry_delay_seconds=10.0,
            sleeper=sleeper,
            logger=logger,
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
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number),
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
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number),
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
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number, incomplete=True),
            sleeper=lambda seconds: None,
            logger=messages.append,
        )

        self.assertEqual(sync.sync_result.skipped_incomplete, 1)
        self.assertTrue(any("unvollständig" in message for message in messages))

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
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number),
            sleeper=lambda seconds: None,
            logger=lambda message: None,
        )

        self.assertEqual(sync.sync_result.imported_count, 1)
        self.assertEqual(sync.read_failures, 1)
        self.assertEqual(len(manager.records), 1)

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
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number),
            sleeper=stop_during_delay,
            logger=lambda message: None,
            is_running=lambda: running,
        )

        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
