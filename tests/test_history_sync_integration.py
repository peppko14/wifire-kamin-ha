# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Offline-Abnahmetests für die lokale Ringpuffer-Synchronisation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from bridge.archive_sync import RingBufferArchiveSynchronizer
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
                    lambda url, number: first_calls.append(number)
                    or str(number)
                ),
                decoder=lambda raw: int(raw),
                record_adapter=simulated_burn,
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
                    lambda url, number: second_calls.append(number)
                    or str(number)
                ),
                decoder=lambda raw: int(raw),
                record_adapter=simulated_burn,
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
                raw_reader=lambda url, number: str(number),
                decoder=lambda raw: int(raw),
                record_adapter=simulated_burn,
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


if __name__ == "__main__":
    unittest.main()
