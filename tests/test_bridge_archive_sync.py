#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.archive_sync."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from bridge.archive_sync import (
    ArchiveSynchronizer,
    RingBufferArchiveSynchronizer,
)
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


class FakeReader:
    def __init__(self, records: dict[str, Any]) -> None:
        self.records = records
        self.commands: list[str] = []

    def read_record(self, command: str) -> Any:
        self.commands.append(command)
        result = self.records[command]
        if isinstance(result, Exception):
            raise result
        return result


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


def history_result(
    *,
    imported: int = 0,
    existing: int = 0,
    incomplete: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        imported_count=imported,
        existing_count=existing,
        skipped_incomplete=incomplete,
    )


class ArchiveSynchronizerTests(unittest.TestCase):
    def test_successful_records_are_published_and_stored(self) -> None:
        commands = (("archive_1", "command_1"),)
        record = make_record(
            1,
            datetime(2026, 4, 22, 21, 23),
        )
        reader = FakeReader({"command_1": record})
        publisher = FakePublisher()
        manager = FakeHistoryManager(history_result(imported=1))
        messages: list[str] = []

        synchronizer = ArchiveSynchronizer(
            commands=commands,
            reader=reader,
            publisher=publisher,
            history_manager=manager,
            request_delay=2,
            sleeper=lambda seconds: None,
            is_running=lambda: True,
            logger=messages.append,
            record_adapter=lambda value: "burn-record",
            attributes_builder=lambda value: {"maximum": 453},
        )

        synchronizer.synchronize()

        self.assertEqual(reader.commands, ["command_1"])
        self.assertEqual(
            publisher.archives,
            [
                {
                    "number": 1,
                    "state": "2026-04-22T21:23:00",
                    "attributes": {"maximum": 453},
                }
            ],
        )
        self.assertEqual(manager.records, [["burn-record"]])
        self.assertIn(
            "Archivaktualisierung wird gestartet.",
            messages,
        )
        self.assertIn(
            "Archivaktualisierung beendet.",
            messages,
        )
        self.assertTrue(
            any("neuer Abbrand" in message for message in messages)
        )

    def test_delay_is_used_between_successful_records(self) -> None:
        commands = (
            ("archive_1", "command_1"),
            ("archive_2", "command_2"),
        )
        reader = FakeReader(
            {
                "command_1": make_record(
                    1,
                    datetime(2026, 4, 22, 21, 23),
                ),
                "command_2": make_record(
                    2,
                    datetime(2026, 4, 11, 21, 35),
                ),
            }
        )
        sleeps: list[int | float] = []

        synchronizer = ArchiveSynchronizer(
            commands=commands,
            reader=reader,
            publisher=FakePublisher(),
            history_manager=FakeHistoryManager(
                history_result(existing=1)
            ),
            request_delay=2,
            sleeper=sleeps.append,
            is_running=lambda: True,
            logger=lambda message: None,
            record_adapter=lambda value: value,
            attributes_builder=lambda value: {},
        )

        synchronizer.synchronize()

        self.assertEqual(sleeps, [2])

    def test_invalid_timestamp_is_skipped(self) -> None:
        reader = FakeReader(
            {"command_1": make_record(1, None)}
        )
        publisher = FakePublisher()
        manager = FakeHistoryManager(history_result())
        messages: list[str] = []

        synchronizer = ArchiveSynchronizer(
            commands=(("archive_1", "command_1"),),
            reader=reader,
            publisher=publisher,
            history_manager=manager,
            request_delay=2,
            sleeper=lambda seconds: None,
            is_running=lambda: True,
            logger=messages.append,
        )

        synchronizer.synchronize()

        self.assertEqual(publisher.archives, [])
        self.assertEqual(manager.records, [])
        self.assertTrue(
            any("Zeitstempel" in message for message in messages)
        )

    def test_read_error_is_logged_and_next_record_is_processed(self) -> None:
        reader = FakeReader(
            {
                "command_1": RuntimeError("nicht erreichbar"),
                "command_2": make_record(
                    2,
                    datetime(2026, 4, 11, 21, 35),
                ),
            }
        )
        publisher = FakePublisher()
        messages: list[str] = []

        synchronizer = ArchiveSynchronizer(
            commands=(
                ("archive_1", "command_1"),
                ("archive_2", "command_2"),
            ),
            reader=reader,
            publisher=publisher,
            history_manager=FakeHistoryManager(
                history_result(existing=1)
            ),
            request_delay=2,
            sleeper=lambda seconds: None,
            is_running=lambda: True,
            logger=messages.append,
            record_adapter=lambda value: value,
            attributes_builder=lambda value: {},
        )

        synchronizer.synchronize()

        self.assertEqual(
            reader.commands,
            ["command_1", "command_2"],
        )
        self.assertEqual(len(publisher.archives), 1)
        self.assertTrue(
            any("Archivfehler" in message for message in messages)
        )

    def test_stop_request_aborts_before_first_read(self) -> None:
        reader = FakeReader({})
        messages: list[str] = []

        synchronizer = ArchiveSynchronizer(
            commands=(("archive_1", "command_1"),),
            reader=reader,
            publisher=FakePublisher(),
            history_manager=FakeHistoryManager(history_result()),
            request_delay=2,
            sleeper=lambda seconds: None,
            is_running=lambda: False,
            logger=messages.append,
        )

        synchronizer.synchronize()

        self.assertEqual(reader.commands, [])
        self.assertEqual(
            messages,
            ["Archivaktualisierung wird gestartet."],
        )


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
            raw_reader=lambda url, number: str(number),
            decoder=lambda raw: make_record(
                int(raw),
                datetime(2026, 4, 22, 21, 23),
            ),
            record_adapter=lambda record: self.burn_record(
                record.archive_number
            ),
            attributes_builder=lambda record: {"maximum": 453},
        )

        result = synchronizer.synchronize()

        self.assertEqual(events, ["local", "mqtt"])
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
            raw_reader=lambda url, number: str(number),
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
            raw_reader=lambda url, number: str(number),
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


if __name__ == "__main__":
    unittest.main()
