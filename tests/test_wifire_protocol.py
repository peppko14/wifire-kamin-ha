# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Regressionstests für die Byte-Dekodierung der WiFire-Archive."""

from __future__ import annotations

from datetime import datetime
import unittest

from protocol.adapters import archive_record_to_burn_record
from wifire_protocol import (
    ARCHIVE_LENGTH,
    ArchiveRecord,
    decode_archive_record,
)


def build_archive_packet(
    *,
    archive_number: int = 7,
    year: int = 26,
    month_byte: int = 0xA4,
    day: int = 22,
    hour: int = 21,
    minute: int = 23,
    stages: tuple[int, int, int, int, int] = (
        7,
        36,
        57,
        109,
        169,
    ),
    temperatures: tuple[int, ...] | None = None,
) -> str:
    """Erzeugt ein vollständiges Telegramm im beobachteten Wire-Format."""
    values = temperatures or tuple(range(100, 221))
    data = bytearray(ARCHIVE_LENGTH)
    data[:4] = bytes.fromhex("aacc3355")
    data[7] = archive_number
    data[8] = year
    data[9] = month_byte
    data[10] = day
    data[11] = hour
    data[12] = minute

    for position, value in zip((13, 15, 17, 19, 21), stages):
        data[position] = value

    for index, temperature in enumerate(values):
        position = 22 + index * 2
        data[position] = temperature & 0xFF
        data[position + 1] = temperature >> 8

    terminator = 22 + len(values) * 2
    if terminator + 1 < 504:
        data[terminator : terminator + 2] = b"\xff\xff"

    return data.hex()


class ArchiveDecoderTests(unittest.TestCase):
    def test_complete_packet_maps_all_observed_offsets(self) -> None:
        raw = build_archive_packet()

        record = decode_archive_record(raw)

        self.assertIsInstance(record, ArchiveRecord)
        self.assertEqual(record.archive_number, 7)
        self.assertEqual(
            record.timestamp,
            datetime(2026, 4, 22, 21, 23),
        )
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
        self.assertEqual(record.measurement_count, 121)
        self.assertEqual(record.temperatures[0], 100)
        self.assertEqual(record.temperatures[-1], 220)
        self.assertFalse(record.active_or_incomplete)
        self.assertEqual(record.raw, raw)

    def test_temperature_values_are_little_endian(self) -> None:
        temperatures = (24, 256, 453) + tuple(range(118))

        record = decode_archive_record(
            build_archive_packet(temperatures=temperatures)
        )

        self.assertEqual(record.temperatures[:3], [24, 256, 453])
        self.assertEqual(record.max_temperature_c, 453)
        self.assertEqual(record.max_temperature_minute, 2)

    def test_timestamp_month_uses_low_nibble(self) -> None:
        record = decode_archive_record(
            build_archive_packet(month_byte=0xF4)
        )

        self.assertEqual(
            record.timestamp,
            datetime(2026, 4, 22, 21, 23),
        )

    def test_invalid_timestamp_is_preserved_as_missing(self) -> None:
        record = decode_archive_record(
            build_archive_packet(month_byte=0)
        )

        self.assertIsNone(record.timestamp)

    def test_zero_phase_byte_is_decoded_as_missing(self) -> None:
        record = decode_archive_record(
            build_archive_packet(stages=(0, 36, 57, 109, 0))
        )

        self.assertIsNone(record.stage_90_minute)
        self.assertIsNone(record.stage_0_minute)

    def test_phase_overflow_is_unwrapped_after_model_conversion(self) -> None:
        record = decode_archive_record(
            build_archive_packet(stages=(11, 79, 122, 201, 5))
        )

        burn = archive_record_to_burn_record(record)

        self.assertEqual(record.stage_0_minute, 5)
        self.assertEqual(burn.duration_minutes, 261)

    def test_trailing_zeroes_mark_short_record_incomplete(self) -> None:
        record = decode_archive_record(
            build_archive_packet(temperatures=(24, 100, 0))
        )

        self.assertEqual(record.temperatures, [24, 100])
        self.assertTrue(record.active_or_incomplete)

    def test_invalid_hex_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Hex"):
            decode_archive_record("not-hex")

    def test_wrong_packet_length_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "506"):
            decode_archive_record("aacc3355")

    def test_unknown_packet_header_is_rejected(self) -> None:
        data = bytearray.fromhex(build_archive_packet())
        data[0] = 0

        with self.assertRaisesRegex(ValueError, "Paketkopf"):
            decode_archive_record(data.hex())


if __name__ == "__main__":
    unittest.main()
