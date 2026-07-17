#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Golden-Tests mit einem unveränderten realen WiFire-Archivtelegramm."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import unittest

from history.identifiers import build_burn_id
from protocol.adapters import archive_record_to_burn_record
from wifire_protocol import ARCHIVE_LENGTH, decode_archive_record


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "archive_complete_real.hex"
)
EXPECTED_WIRE_SHA256 = (
    "9e3cd14f5d91f20cf1c332561c939e7547bdad95fcd90c754c641d38d14bf0b5"
)
EXPECTED_BURN_ID = (
    "3bc209258a4f954567351c4490ff79c92933b1bfb81d92473c1c1d0426429539"
)


def load_fixture() -> str:
    """Lädt das reale Telegramm ohne die abschließende Textzeile."""
    return FIXTURE_PATH.read_text(encoding="ascii").strip()


class ArchiveGoldenFixtureTests(unittest.TestCase):
    def test_fixture_wire_payload_is_immutable(self) -> None:
        raw = load_fixture()
        payload = bytes.fromhex(raw)

        self.assertEqual(len(raw), ARCHIVE_LENGTH * 2)
        self.assertEqual(len(payload), ARCHIVE_LENGTH)
        self.assertEqual(raw, raw.lower())
        self.assertEqual(raw[:16], "aacc3355fff33501")
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            EXPECTED_WIRE_SHA256,
        )

    def test_real_archive_maps_all_observed_values(self) -> None:
        record = decode_archive_record(load_fixture())

        self.assertEqual(record.archive_number, 1)
        self.assertEqual(record.timestamp, datetime(2026, 4, 22, 21, 23))
        self.assertEqual(record.measurement_count, 121)
        self.assertEqual(
            (
                record.stage_90_minute,
                record.stage_75_minute,
                record.stage_50_minute,
                record.stage_25_minute,
                record.stage_0_minute,
            ),
            (7, 36, 57, 109, 169),
        )
        self.assertEqual(
            [record.temperatures[index] for index in (0, 10, 26, 60, 120)],
            [22, 159, 453, 318, 205],
        )
        self.assertEqual(record.max_temperature_c, 453)
        self.assertEqual(record.max_temperature_minute, 26)
        self.assertFalse(record.active_or_incomplete)

    def test_real_archive_keeps_stable_history_identity(self) -> None:
        record = decode_archive_record(load_fixture())
        burn = archive_record_to_burn_record(record)

        self.assertTrue(burn.is_complete)
        self.assertEqual(burn.duration_minutes, 169)
        self.assertEqual(build_burn_id(burn), EXPECTED_BURN_ID)


if __name__ == "__main__":
    unittest.main()
