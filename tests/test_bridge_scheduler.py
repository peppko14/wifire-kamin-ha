#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.scheduler."""

from __future__ import annotations

import unittest

from bridge.scheduler import (
    InterruptibleSleeper,
    IntervalSchedule,
)


class InterruptibleSleeperTests(unittest.TestCase):
    def test_sleep_is_split_into_short_steps(self) -> None:
        calls: list[float] = []
        sleeper = InterruptibleSleeper(
            is_running=lambda: True,
            sleep=calls.append,
        )

        sleeper(0.3)

        self.assertEqual(calls, [0.1, 0.1, 0.1])

    def test_stop_before_sleep_skips_wait(self) -> None:
        calls: list[float] = []
        sleeper = InterruptibleSleeper(
            is_running=lambda: False,
            sleep=calls.append,
        )

        sleeper(60)

        self.assertEqual(calls, [])

    def test_stop_during_sleep_aborts_remaining_steps(self) -> None:
        checks = iter((True, True, False))
        calls: list[float] = []
        sleeper = InterruptibleSleeper(
            is_running=lambda: next(checks),
            sleep=calls.append,
        )

        sleeper(10)

        self.assertEqual(calls, [0.1, 0.1])

    def test_zero_seconds_preserves_minimum_step(self) -> None:
        calls: list[float] = []
        sleeper = InterruptibleSleeper(
            is_running=lambda: True,
            sleep=calls.append,
        )

        sleeper(0)

        self.assertEqual(calls, [0.1])


class IntervalScheduleTests(unittest.TestCase):
    def test_schedule_is_due_at_interval_boundary(self) -> None:
        schedule = IntervalSchedule(interval_seconds=21600)

        self.assertFalse(schedule.is_due(21599.9))
        self.assertTrue(schedule.is_due(21600.0))

    def test_mark_updated_starts_new_interval(self) -> None:
        schedule = IntervalSchedule(interval_seconds=60)
        schedule.mark_updated(100.0)

        self.assertFalse(schedule.is_due(159.9))
        self.assertTrue(schedule.is_due(160.0))


if __name__ == "__main__":
    unittest.main()
