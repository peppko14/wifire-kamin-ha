# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die MQTT-unabhängige Ringpuffer-Synchronisation."""

from __future__ import annotations

import unittest
from datetime import datetime

from history.manager import HistorySyncResult
from history.sync import (
    ArchiveSyncSettings,
    build_archive_command,
    build_archive_url,
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

    def test_archive_url_is_derived_from_live_url(self) -> None:
        self.assertEqual(
            build_archive_url("http://192.168.0.1/direct/00"),
            "http://192.168.0.1/direct/35",
        )

    def test_archive_url_preserves_host_and_port(self) -> None:
        self.assertEqual(
            build_archive_url("http://wifire.local:8080/direct/00"),
            "http://wifire.local:8080/direct/35",
        )

    def test_invalid_live_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_archive_url("192.168.0.1/direct/00")

    def test_non_direct_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_archive_url("http://192.168.0.1/status/00")

    def test_archive_command_is_correct(self) -> None:
        self.assertEqual(build_archive_command(1), "aacc3355023501ffff")
        self.assertEqual(build_archive_command(23), "aacc3355023517ffff")

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
            raw_reader=lambda url, number: calls.append(number) or str(number),
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
            raw_reader=lambda url, number: calls.append(number) or str(number),
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
            raw_reader=lambda url, number: str(number),
            decoder=lambda raw: int(raw),
            record_adapter=lambda number: burn(number, incomplete=True),
            sleeper=lambda seconds: None,
            logger=messages.append,
        )

        self.assertEqual(sync.sync_result.skipped_incomplete, 1)
        self.assertTrue(any("unvollständig" in message for message in messages))

    def test_read_error_does_not_discard_already_saved_record(self) -> None:
        manager = FakeManager([result(imported=("id-1",))])

        def reader(url: str, number: int) -> str:
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


if __name__ == "__main__":
    unittest.main()
