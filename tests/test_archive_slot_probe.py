# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für das begrenzte, ausschließlich lesende Archivplatz-Werkzeug."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from protocol.archive import ArchiveReadError
from tools.archive_slot_probe_v1_0_0 import (
    MAX_SLOTS_PER_RUN,
    ProbeSettings,
    default_output_path,
    probe_archive_slots,
    write_report,
)


LIVE_URL = "http://192.168.0.1/direct/00"
RAW_A = "aacc3355" + "00" * 502
RAW_B = "aacc3355" + "01" * 502


def settings(*, first: int = 24, last: int = 25) -> ProbeSettings:
    return ProbeSettings(
        live_url=LIVE_URL,
        first_slot=first,
        last_slot=last,
    )


class ArchiveSlotProbeTests(unittest.TestCase):
    def test_settings_accept_a_small_explicit_range_above_23(self) -> None:
        probe_settings = settings(
            first=24,
            last=24 + MAX_SLOTS_PER_RUN - 1,
        )

        probe_settings.validate()
        self.assertEqual(probe_settings.slot_count, MAX_SLOTS_PER_RUN)

    def test_confirmed_or_out_of_byte_range_is_rejected(self) -> None:
        for first, last in ((23, 24), (24, 256), (30, 29)):
            with self.subTest(first=first, last=last):
                with self.assertRaises(ValueError):
                    settings(first=first, last=last).validate()

    def test_more_than_sixteen_slots_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            settings(first=24, last=24 + MAX_SLOTS_PER_RUN).validate()

    def test_unsafe_delay_and_retry_settings_are_rejected(self) -> None:
        invalid_values = (
            {"request_delay_seconds": 9.9},
            {"retry_delay_seconds": 9.9},
            {"retry_count": 0},
            {"retry_count": 4},
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                ProbeSettings(
                    live_url=LIVE_URL,
                    first_slot=24,
                    last_slot=24,
                    **values,  # type: ignore[arg-type]
                ).validate()

    def test_slots_are_read_sequentially_with_fixed_delays(self) -> None:
        calls: list[int] = []
        sleeps: list[int | float] = []

        report = probe_archive_slots(
            settings(first=24, last=26),
            lambda slot: calls.append(slot) or RAW_A,
            sleeper=sleeps.append,
            logger=lambda message: None,
            generated_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        )

        self.assertEqual(calls, [24, 25, 26])
        self.assertEqual(sleeps, [10.0, 10.0])
        self.assertEqual(report.readable_count, 3)
        self.assertEqual(report.error_count, 0)

    def test_report_preserves_raw_metadata_and_detects_duplicates(self) -> None:
        payloads = {24: RAW_A, 25: RAW_B, 26: RAW_A}
        report = probe_archive_slots(
            settings(first=24, last=26),
            payloads.__getitem__,
            sleeper=lambda seconds: None,
            logger=lambda message: None,
        )

        first, second, duplicate = report.results
        self.assertEqual(first.raw, RAW_A)
        self.assertEqual(first.byte_length, 506)
        self.assertEqual(
            first.sha256,
            hashlib.sha256(bytes.fromhex(RAW_A)).hexdigest(),
        )
        self.assertEqual(first.prefix_hex, "aacc335500000000")
        self.assertTrue(first.packet_header_valid)
        self.assertTrue(first.known_wire_length)
        self.assertIsNone(second.duplicate_of_slot)
        self.assertEqual(duplicate.duplicate_of_slot, 24)

    def test_read_error_is_recorded_and_scan_continues(self) -> None:
        calls: list[int] = []

        def reader(slot: int) -> str:
            calls.append(slot)
            if slot == 24:
                raise ArchiveReadError("nicht erreichbar")
            return RAW_A

        report = probe_archive_slots(
            settings(first=24, last=25),
            reader,
            sleeper=lambda seconds: None,
            logger=lambda message: None,
        )

        self.assertEqual(calls, [24, 25])
        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.results[0].status, "read_error")
        self.assertIn("nicht erreichbar", report.results[0].error or "")
        self.assertEqual(report.results[1].status, "readable")

    def test_programming_error_is_not_hidden(self) -> None:
        def reader(slot: int) -> str:
            raise AttributeError("Programmierfehler")

        with self.assertRaises(AttributeError):
            probe_archive_slots(
                settings(first=24, last=24),
                reader,
                logger=lambda message: None,
            )

    def test_report_is_written_atomically_below_data_by_default(self) -> None:
        generated_at = datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc)
        report = probe_archive_slots(
            settings(first=24, last=24),
            lambda slot: RAW_A,
            logger=lambda message: None,
            generated_at=generated_at,
        )
        self.assertIn("data", default_output_path(report).parts)

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "probe.json"
            write_report(report, output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["first_slot"], 24)
            self.assertEqual(payload["results"][0]["raw"], RAW_A)
            self.assertFalse(output_path.with_name("probe.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
