#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.runtime."""

from __future__ import annotations

import unittest
from itertools import chain, repeat
from typing import Any

from bridge.polling import PollingSettings
from bridge.runtime import BridgeRuntime
from bridge.scheduler import IntervalSchedule


class FakePoller:
    def __init__(
        self,
        result: dict[str, Any] | Exception,
    ) -> None:
        self.result = result
        self.calls = 0

    def poll(self) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePublisher:
    def __init__(self) -> None:
        self.availability: list[bool] = []
        self.states: list[dict[str, Any]] = []

    def publish_availability(self, online: bool) -> None:
        self.availability.append(online)

    def publish_state(self, data: dict[str, Any]) -> None:
        self.states.append(data)


class FakeArchiveSynchronizer:
    def __init__(self) -> None:
        self.calls = 0

    def synchronize(self) -> None:
        self.calls += 1


def live_state(temperature_c: int = 24) -> dict[str, Any]:
    return {
        "temperature_c": temperature_c,
        "flap_percent": 100,
        "burn_time": "0:12",
        "door_state": "geschlossen",
    }


class BridgeRuntimeTests(unittest.TestCase):
    def create_runtime(
        self,
        poll_result: dict[str, Any] | Exception,
        *,
        schedule: IntervalSchedule | None = None,
        clock_values: tuple[float, ...] = (1.0,),
    ) -> tuple[
        BridgeRuntime,
        FakePublisher,
        FakeArchiveSynchronizer,
        list[int | float],
        list[dict[str, Any]],
        list[str],
    ]:
        publisher = FakePublisher()
        archive = FakeArchiveSynchronizer()
        sleeps: list[int | float] = []
        states: list[dict[str, Any]] = []
        messages: list[str] = []
        clock = chain(
            clock_values,
            repeat(clock_values[-1]),
        )

        runtime = BridgeRuntime(
            live_poller=FakePoller(poll_result),
            publisher=publisher,
            archive_synchronizer=archive,
            archive_schedule=(
                schedule
                if schedule is not None
                else IntervalSchedule(21600)
            ),
            polling_settings=PollingSettings(),
            sleeper=sleeps.append,
            is_running=lambda: True,
            offline_after_failures=3,
            on_state=states.append,
            monotonic=lambda: next(clock),
            logger=messages.append,
        )
        return (
            runtime,
            publisher,
            archive,
            sleeps,
            states,
            messages,
        )

    def test_success_publishes_state_and_uses_normal_interval(
        self,
    ) -> None:
        state = live_state()
        runtime, publisher, _, sleeps, states, messages = (
            self.create_runtime(state)
        )

        result = runtime.run_cycle()

        self.assertEqual(publisher.states, [state])
        self.assertEqual(states, [state])
        self.assertEqual(sleeps, [60])
        self.assertEqual(result, (60, "Normalbetrieb"))
        self.assertIn("24 °C | 100 % | 0:12", messages[0])

    def test_active_fire_uses_short_interval(self) -> None:
        runtime, _, _, sleeps, _, _ = self.create_runtime(
            live_state(temperature_c=40)
        )

        result = runtime.run_cycle()

        self.assertEqual(sleeps, [10])
        self.assertEqual(result, (10, "aktiver Abbrand"))

    def test_failure_uses_error_interval(self) -> None:
        runtime, publisher, _, sleeps, states, _ = (
            self.create_runtime(OSError("timeout"))
        )

        result = runtime.run_cycle()

        self.assertEqual(publisher.states, [])
        self.assertEqual(states, [])
        self.assertEqual(sleeps, [300])
        self.assertEqual(result, (300, "Lesefehler"))

    def test_repeated_failures_publish_offline_once(self) -> None:
        runtime, publisher, _, _, _, _ = self.create_runtime(
            ValueError("invalid")
        )

        runtime.run_cycle()
        runtime.run_cycle()
        runtime.run_cycle()
        runtime.run_cycle()

        self.assertEqual(publisher.availability, [False])
        self.assertFalse(runtime.availability_online)

    def test_success_after_failure_publishes_online(self) -> None:
        poller = FakePoller(OSError("timeout"))
        runtime, publisher, _, _, _, _ = self.create_runtime(
            live_state()
        )
        runtime.live_poller = poller
        runtime.availability_online = False
        poller.result = live_state()

        runtime.run_cycle()

        self.assertEqual(publisher.availability, [True])
        self.assertTrue(runtime.availability_online)

    def test_due_archive_is_synchronized_and_rescheduled(
        self,
    ) -> None:
        schedule = IntervalSchedule(60)
        runtime, _, archive, _, _, _ = self.create_runtime(
            live_state(),
            schedule=schedule,
            clock_values=(60.0, 61.5),
        )

        runtime.run_cycle()

        self.assertEqual(archive.calls, 1)
        self.assertEqual(schedule.last_update, 61.5)

    def test_run_stops_after_running_check_changes(self) -> None:
        checks = iter((True, False))
        runtime, publisher, _, _, _, _ = self.create_runtime(
            live_state()
        )
        runtime.is_running = lambda: next(checks)

        runtime.run()

        self.assertEqual(len(publisher.states), 1)


if __name__ == "__main__":
    unittest.main()
