#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.heating_failure_monitor."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bridge.heating_failure_monitor import (
    HeatingFailureMonitor,
    HeatingFailureStateStorage,
    build_heating_failure_state,
    find_new_entries,
)
from protocol.device_diagnostics import (
    AlarmEntry,
    AlarmList,
    DeviceDiagnosticsReadError,
)


BERLIN_SUMMER = timezone(timedelta(hours=2))


def alarm(day: int, raw_record: str) -> AlarmEntry:
    return AlarmEntry(
        occurred_on=date(2026, 3, day),
        code=1,
        label="Heizfehler",
        value_byte=0,
        metadata_byte=0,
        raw_record=raw_record,
    )


def alarm_list(*entries: AlarmEntry) -> AlarmList:
    return AlarmList(entries=tuple(entries), raw="aacc3355")


class FakeClient:
    def __init__(self, values: list[AlarmList | Exception]) -> None:
        self.values = values
        self.calls = 0

    def read_alarms(self) -> AlarmList:
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


class FakePublisher:
    def __init__(self) -> None:
        self.lists: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []

    def publish_heating_failures(
        self,
        payload: dict[str, object],
    ) -> None:
        self.lists.append(payload)

    def publish_heating_failure_event(
        self,
        payload: dict[str, object],
    ) -> None:
        self.events.append(payload)


class FakeSchedule:
    def __init__(self, due: bool = True) -> None:
        self.due = due
        self.marked: list[float] = []

    def is_due(self, now: float) -> bool:
        return self.due

    def mark_updated(self, now: float) -> None:
        self.marked.append(now)


class HeatingFailureMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state.json"
        self.storage = HeatingFailureStateStorage(
            self.path,
            logger=lambda message: None,
        )
        self.observed_at = datetime(
            2026,
            7,
            17,
            14,
            20,
            tzinfo=BERLIN_SUMMER,
        )

    def create_monitor(
        self,
        client: FakeClient,
        publisher: FakePublisher,
        schedule: FakeSchedule,
    ) -> HeatingFailureMonitor:
        return HeatingFailureMonitor(
            client=client,
            publisher=publisher,
            storage=self.storage,
            schedule=schedule,
            monotonic=lambda: 1000.0,
            clock=lambda: self.observed_at,
            logger=lambda message: None,
        )

    def test_first_success_creates_baseline_without_event(self) -> None:
        current = alarm_list(alarm(5, "1a0305010000"))
        publisher = FakePublisher()
        schedule = FakeSchedule()
        monitor = self.create_monitor(
            FakeClient([current]),
            publisher,
            schedule,
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.checked)
        self.assertTrue(result.baseline_created)
        self.assertFalse(result.event_published)
        self.assertEqual(len(publisher.lists), 1)
        self.assertEqual(publisher.events, [])
        self.assertEqual(
            self.storage.load(),
            build_heating_failure_state(current),
        )
        self.assertEqual(schedule.marked, [1000.0])

    def test_changed_list_publishes_one_restart_safe_event(self) -> None:
        old = alarm_list(alarm(4, "1a0304010000"))
        new = alarm_list(
            alarm(5, "1a0305010000"),
            alarm(4, "1a0304010000"),
        )
        self.storage.save(build_heating_failure_state(old))
        publisher = FakePublisher()
        monitor = self.create_monitor(
            FakeClient([new]),
            publisher,
            FakeSchedule(),
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.event_published)
        self.assertEqual(len(publisher.events), 1)
        event = publisher.events[0]
        self.assertEqual(event["new_count"], 1)
        self.assertEqual(event["current_count"], 2)
        self.assertEqual(
            event["event_id"],
            build_heating_failure_state(new).fingerprint,
        )

    def test_duplicate_date_is_detected_by_record_multiset(self) -> None:
        first = alarm(5, "1a0305010000")
        duplicate = alarm(5, "1a0305010001")
        previous = build_heating_failure_state(alarm_list(first))

        added = find_new_entries(
            alarm_list(duplicate, first),
            previous,
        )

        self.assertEqual(added, (duplicate,))

    def test_unchanged_list_does_not_publish_event(self) -> None:
        current = alarm_list(alarm(5, "1a0305010000"))
        self.storage.save(build_heating_failure_state(current))
        publisher = FakePublisher()
        monitor = self.create_monitor(
            FakeClient([current]),
            publisher,
            FakeSchedule(),
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.checked)
        self.assertFalse(result.event_published)
        self.assertEqual(publisher.events, [])

    def test_removed_entry_updates_baseline_without_false_event(self) -> None:
        first = alarm(5, "1a0305010000")
        second = alarm(4, "1a0304010000")
        previous = alarm_list(first, second)
        current = alarm_list(first)
        self.storage.save(build_heating_failure_state(previous))
        publisher = FakePublisher()
        monitor = self.create_monitor(
            FakeClient([current]),
            publisher,
            FakeSchedule(),
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.checked)
        self.assertFalse(result.event_published)
        self.assertEqual(publisher.events, [])
        self.assertEqual(
            self.storage.load(),
            build_heating_failure_state(current),
        )

    def test_read_failure_keeps_existing_state_and_values(self) -> None:
        previous = alarm_list(alarm(4, "1a0304010000"))
        state = build_heating_failure_state(previous)
        self.storage.save(state)
        publisher = FakePublisher()
        monitor = self.create_monitor(
            FakeClient([DeviceDiagnosticsReadError("offline")]),
            publisher,
            FakeSchedule(),
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.checked)
        self.assertEqual(self.storage.load(), state)
        self.assertEqual(publisher.lists, [])
        self.assertEqual(publisher.events, [])

    def test_not_due_does_not_read_or_mark_schedule(self) -> None:
        client = FakeClient([alarm_list()])
        schedule = FakeSchedule(due=False)
        monitor = self.create_monitor(client, FakePublisher(), schedule)

        result = monitor.refresh_if_due()

        self.assertFalse(result.checked)
        self.assertEqual(client.calls, 0)
        self.assertEqual(schedule.marked, [])

    def test_corrupt_state_becomes_new_baseline_without_event(self) -> None:
        self.path.write_text("not json", encoding="utf-8")
        current = alarm_list(alarm(5, "1a0305010000"))
        publisher = FakePublisher()
        monitor = self.create_monitor(
            FakeClient([current]),
            publisher,
            FakeSchedule(),
        )

        result = monitor.refresh_if_due()

        self.assertTrue(result.baseline_created)
        self.assertEqual(publisher.events, [])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
