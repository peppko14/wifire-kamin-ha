#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.archive_sync."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from bridge.archive_sync import RingBufferArchiveSynchronizer
from history.manager import HistorySyncResult
from history.sync import ArchiveSyncSettings
from protocol.models import BurnRecord


def make_record(
    archive_number: int,
    timestamp: datetime | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        archive_number=archive_number,
        timestamp=timestamp,
        max_temperature_c=453,
        measurement_count=121,
    )


class FakePublisher:
    def __init__(self) -> None:
        self.archives: list[dict[str, object]] = []

    def publish_archive(
        self,
        number: int,
        *,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        self.archives.append(
            {
                "number": number,
                "state": state,
                "attributes": attributes,
            }
        )


class FakeHistoryManager:
    def __init__(self, result: SimpleNamespace) -> None:
        self.result = result
        self.records: list[list[Any]] = []

    def synchronize(self, records: list[Any]) -> SimpleNamespace:
        self.records.append(records)
        return self.result


class RingBufferArchiveSynchronizerTests(unittest.TestCase):
    def settings(self, *, first: int = 1, last: int = 1) -> ArchiveSyncSettings:
        return ArchiveSyncSettings(
            live_url="http://192.0.2.1/direct/00",
            first_archive=first,
            last_archive=last,
            archive_delay_seconds=10,
        )

    def burn_record(self, number: int) -> BurnRecord:
        return BurnRecord(
            start=datetime(2026, 4, 22, 21, 23),
            temperatures_c=(20, 100, 453),
            source_archive_number=number,
        )

    def test_local_storage_happens_before_mqtt_publication(self) -> None:
        events: list[str] = []

        class OrderedManager:
            def synchronize(self, records: list[Any]) -> HistorySyncResult:
                events.append("local")
                return HistorySyncResult(("id-1",), (), 0, 0)

        class OrderedPublisher(FakePublisher):
            def publish_archive(
                self,
                number: int,
                *,
                state: str,
                attributes: dict[str, object],
            ) -> None:
                events.append("mqtt")
                super().publish_archive(
                    number,
                    state=state,
                    attributes=attributes,
                )

        synchronizer = RingBufferArchiveSynchronizer(
            settings=self.settings(),
            history_manager=OrderedManager(),  # type: ignore[arg-type]
            publisher=OrderedPublisher(),
            sleeper=lambda seconds: None,
            logger=lambda message: None,
            raw_reader=lambda number: str(number),
            decoder=lambda raw: make_record(
                int(raw),
                datetime(2026, 4, 22, 21, 23),
            ),
            record_adapter=lambda record: self.burn_record(
                record.archive_number
            ),
            attributes_builder=lambda record: {"maximum": 453},
            on_complete=lambda: events.append("statistics"),
        )

        result = synchronizer.synchronize()

        self.assertEqual(events, ["local", "mqtt", "statistics"])
        self.assertEqual(result.sync_result.imported_count, 1)

    def test_mqtt_failure_does_not_undo_local_result(self) -> None:
        class FailingPublisher(FakePublisher):
            def publish_archive(
                self,
                number: int,
                *,
                state: str,
                attributes: dict[str, object],
            ) -> None:
                raise RuntimeError("MQTT nicht erreichbar")

        manager = FakeHistoryManager(
            HistorySyncResult(("id-1",), (), 0, 0)
        )
        messages: list[str] = []
        synchronizer = RingBufferArchiveSynchronizer(
            settings=self.settings(),
            history_manager=manager,  # type: ignore[arg-type]
            publisher=FailingPublisher(),
            sleeper=lambda seconds: None,
            logger=messages.append,
            raw_reader=lambda number: str(number),
            decoder=lambda raw: make_record(
                int(raw),
                datetime(2026, 4, 22, 21, 23),
            ),
            record_adapter=lambda record: self.burn_record(
                record.archive_number
            ),
            attributes_builder=lambda record: {},
        )

        result = synchronizer.synchronize()

        self.assertEqual(result.sync_result.imported_count, 1)
        self.assertTrue(
            any("nachgelagerte Verarbeitung" in message for message in messages)
        )

    def test_slots_after_three_are_not_published_to_mqtt(self) -> None:
        publisher = FakePublisher()
        synchronizer = RingBufferArchiveSynchronizer(
            settings=self.settings(first=4, last=4),
            history_manager=FakeHistoryManager(
                HistorySyncResult((), ("id-4",), 0, 0)
            ),  # type: ignore[arg-type]
            publisher=publisher,
            sleeper=lambda seconds: None,
            logger=lambda message: None,
            raw_reader=lambda number: str(number),
            decoder=lambda raw: make_record(
                int(raw),
                datetime(2026, 4, 22, 21, 23),
            ),
            record_adapter=lambda record: self.burn_record(
                record.archive_number
            ),
            attributes_builder=lambda record: {},
        )

        synchronizer.synchronize()

        self.assertEqual(publisher.archives, [])

    def test_statistics_failure_does_not_change_local_result(self) -> None:
        messages: list[str] = []

        def fail_statistics() -> None:
            raise RuntimeError("Statistik nicht verfügbar")

        synchronizer = RingBufferArchiveSynchronizer(
            settings=self.settings(),
            history_manager=FakeHistoryManager(
                HistorySyncResult(("id-1",), (), 0, 0)
            ),  # type: ignore[arg-type]
            publisher=FakePublisher(),
            sleeper=lambda seconds: None,
            logger=messages.append,
            raw_reader=lambda number: str(number),
            decoder=lambda raw: make_record(
                int(raw),
                datetime(2026, 4, 22, 21, 23),
            ),
            record_adapter=lambda record: self.burn_record(
                record.archive_number
            ),
            attributes_builder=lambda record: {},
            on_complete=fail_statistics,
        )

        result = synchronizer.synchronize()

        self.assertEqual(result.sync_result.imported_count, 1)
        self.assertTrue(
            any(
                "Historienausgaben konnten nicht aktualisiert" in message
                for message in messages
            )
        )


if __name__ == "__main__":
    unittest.main()
