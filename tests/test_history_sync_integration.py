# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Offline-Abnahmetests für die lokale Ringpuffer-Synchronisation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from bridge.archive_sync import RingBufferArchiveSynchronizer
from history.diagnostics import HistoryDiagnosticStorage
from history.manager import HistoryManager
from history.storage import HistoryStorage
from history.sync import ArchiveSyncSettings, synchronize_archives
from protocol.models import BurnRecord




def simulated_burn(archive_number: int) -> BurnRecord:
    """Erzeugt denselben Abbrand an wechselnden Ringpufferplätzen."""
    return BurnRecord(
        start=datetime(2026, 7, 13, 20, 0),
        temperatures_c=(24, 80, 210, 430, 280, 90),
        source_archive_number=archive_number,
    )


def archive_record(archive_number: int) -> SimpleNamespace:
    """Erzeugt einen belegten dekodierten Archivplatz."""
    return SimpleNamespace(
        archive_number=archive_number,
        timestamp=datetime(2026, 7, 13, 20, 0),
        stage_90_minute=5,
        stage_75_minute=30,
        stage_50_minute=60,
        stage_25_minute=120,
        stage_0_minute=180,
        temperatures=[24, 80, 210, 430, 280, 90],
        active_or_incomplete=False,
        raw="aacc3355",
    )


def empty_archive_record(archive_number: int) -> SimpleNamespace:
    """Erzeugt einen beobachteten leeren, aber adressierbaren Platz."""
    return SimpleNamespace(
        archive_number=archive_number,
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


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FailingArchivePublisher:
    def publish_archive(
        self,
        number: int,
        *,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        raise RuntimeError("simulierter MQTT-Ausfall")


class HistorySyncIntegrationTests(unittest.TestCase):
    def settings(self, *, last: int) -> ArchiveSyncSettings:
        return ArchiveSyncSettings(
            live_url="http://192.0.2.1/direct/00",
            first_archive=1,
            last_archive=last,
            archive_delay_seconds=10,
        )

    def test_second_scan_creates_no_duplicate_and_changes_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            manager = HistoryManager(storage)
            first_calls: list[int] = []
            first_sleeps: list[float] = []

            first = synchronize_archives(
                manager,
                self.settings(last=3),
                raw_reader=(
                    lambda number: first_calls.append(number)
                    or str(number)
                ),
                decoder=lambda raw: archive_record(int(raw)),
                record_adapter=lambda record: simulated_burn(
                    record.archive_number
                ),
                sleeper=first_sleeps.append,
                logger=lambda message: None,
            )

            files_after_first = sorted(Path(directory).glob("*.json"))
            self.assertEqual(len(files_after_first), 1)
            self.assertEqual(first.sync_result.imported_count, 1)
            self.assertEqual(first.sync_result.existing_count, 1)
            self.assertEqual(first_calls, [1, 2])
            self.assertEqual(first_sleeps, [10])

            original_digest = file_digest(files_after_first[0])
            second_calls: list[int] = []
            second_sleeps: list[float] = []

            second = synchronize_archives(
                manager,
                self.settings(last=3),
                raw_reader=(
                    lambda number: second_calls.append(number)
                    or str(number)
                ),
                decoder=lambda raw: archive_record(int(raw)),
                record_adapter=lambda record: simulated_burn(
                    record.archive_number
                ),
                sleeper=second_sleeps.append,
                logger=lambda message: None,
            )

            files_after_second = sorted(Path(directory).glob("*.json"))
            self.assertEqual(files_after_second, files_after_first)
            self.assertEqual(file_digest(files_after_second[0]), original_digest)
            self.assertEqual(second.sync_result.imported_count, 0)
            self.assertEqual(second.sync_result.existing_count, 1)
            self.assertTrue(second.stopped_on_existing)
            self.assertEqual(second_calls, [1])
            self.assertEqual(second_sleeps, [])

    def test_mqtt_failure_does_not_prevent_json_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            manager = HistoryManager(storage)
            messages: list[str] = []
            synchronizer = RingBufferArchiveSynchronizer(
                settings=self.settings(last=1),
                history_manager=manager,
                publisher=FailingArchivePublisher(),
                sleeper=lambda seconds: None,
                logger=messages.append,
                raw_reader=lambda number: str(number),
                decoder=lambda raw: archive_record(int(raw)),
                record_adapter=lambda record: simulated_burn(
                    record.archive_number
                ),
                attributes_builder=lambda record: {},
            )

            result = synchronizer.synchronize()

            self.assertEqual(result.sync_result.imported_count, 1)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)
            self.assertTrue(
                any(
                    "nachgelagerte Verarbeitung" in message
                    for message in messages
                )
            )

    def test_empty_slot_creates_neither_history_nor_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = HistoryStorage(root / "history")
            diagnostics = HistoryDiagnosticStorage(root / "diagnostics")
            manager = HistoryManager(storage, diagnostics)
            calls: list[int] = []

            result = synchronize_archives(
                manager,
                ArchiveSyncSettings(
                    live_url="http://192.0.2.1/direct/00",
                    first_archive=24,
                    last_archive=30,
                    archive_delay_seconds=10,
                ),
                raw_reader=(
                    lambda number: calls.append(number) or str(number)
                ),
                decoder=lambda raw: empty_archive_record(int(raw)),
                record_adapter=lambda record: self.fail(
                    "Ein leerer Platz darf nicht adaptiert werden."
                ),
                sleeper=lambda seconds: self.fail(
                    "Nach einem leeren Platz darf nicht gewartet werden."
                ),
                logger=lambda message: None,
            )

            self.assertEqual(calls, [24])
            self.assertTrue(result.stopped_on_empty)
            self.assertEqual(result.empty_archives, 1)
            self.assertEqual(list((root / "history").glob("*.json")), [])
            self.assertEqual(
                list((root / "diagnostics").glob("*.json")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
