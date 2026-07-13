#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für history.ring_buffer."""

from __future__ import annotations

import unittest

from history.ring_buffer import (
    ArchiveOutcome,
    RingBufferStrategy,
)


class RingBufferStrategyTests(unittest.TestCase):
    def test_defaults_cover_known_ring_buffer(self) -> None:
        strategy = RingBufferStrategy()

        numbers = strategy.archive_numbers()

        self.assertEqual(numbers[0], 1)
        self.assertEqual(numbers[-1], 23)
        self.assertEqual(len(numbers), 23)
        self.assertEqual(strategy.request_delay_seconds, 10)

    def test_custom_valid_range_is_supported(self) -> None:
        strategy = RingBufferStrategy(
            first_archive=3,
            last_archive=5,
            request_delay_seconds=12,
        )

        self.assertEqual(strategy.archive_numbers(), (3, 4, 5))

    def test_invalid_archive_range_is_rejected(self) -> None:
        invalid_ranges = (
            (0, 23),
            (5, 4),
            (1, 256),
        )

        for first_archive, last_archive in invalid_ranges:
            with self.subTest(
                first=first_archive,
                last=last_archive,
            ):
                strategy = RingBufferStrategy(
                    first_archive=first_archive,
                    last_archive=last_archive,
                )
                with self.assertRaises(ValueError):
                    strategy.validate()

    def test_delay_below_ten_seconds_is_rejected(self) -> None:
        strategy = RingBufferStrategy(
            request_delay_seconds=9.9
        )

        with self.assertRaisesRegex(ValueError, "10 Sekunden"):
            strategy.validate()

    def test_new_record_continues_scan(self) -> None:
        strategy = RingBufferStrategy()

        self.assertTrue(
            strategy.should_continue_after(ArchiveOutcome.NEW)
        )

    def test_incomplete_record_continues_scan(self) -> None:
        strategy = RingBufferStrategy()

        self.assertTrue(
            strategy.should_continue_after(
                ArchiveOutcome.INCOMPLETE
            )
        )

    def test_read_error_continues_scan(self) -> None:
        strategy = RingBufferStrategy()

        self.assertTrue(
            strategy.should_continue_after(
                ArchiveOutcome.READ_ERROR
            )
        )

    def test_existing_record_stops_without_delay(self) -> None:
        strategy = RingBufferStrategy()

        self.assertFalse(
            strategy.should_continue_after(
                ArchiveOutcome.EXISTING
            )
        )
        self.assertFalse(
            strategy.needs_delay_after(
                3,
                ArchiveOutcome.EXISTING,
            )
        )


if __name__ == "__main__":
    unittest.main()
