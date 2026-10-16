# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für das Archivabschluss-Probe-Werkzeug."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.archive_completion_probe_v1_0_0 import (
    CONFIRMATION_THRESHOLD,
    ProbeTracker,
    run_probe,
)


class MockArchiveClient:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    def read_raw(self, slot: int) -> str:
        return self.raw


class ArchiveCompletionProbeTrackerTests(unittest.TestCase):
    def test_tracker_detects_flap_zero(self) -> None:
        tracker = ProbeTracker()
        event = tracker.observe(
            live_flap=0,
            archive_fingerprint="fp1",
            archive_is_complete=False,
            archive_active_or_incomplete=True,
            burn_id=None,
        )
        self.assertIsNotNone(event)
        self.assertIn("Klappe 0 %", event)
        self.assertIn("Datensatz noch unvollständig", event)

        # Flap 0 should only be logged once
        event2 = tracker.observe(
            live_flap=0,
            archive_fingerprint="fp1",
            archive_is_complete=False,
            archive_active_or_incomplete=True,
            burn_id=None,
        )
        self.assertNotIn("Klappe 0 %", event2 or "")

    def test_tracker_detects_new_slot_and_confirms_completion(self) -> None:
        tracker = ProbeTracker()

        # Erste Beobachtung mit alter Burn-ID
        tracker.observe(
            live_flap=50,
            archive_fingerprint="old_fp",
            archive_is_complete=True,
            archive_active_or_incomplete=False,
            burn_id="burn_old",
        )

        # Neuer Fingerprint erkannt
        event_new = tracker.observe(
            live_flap=0,
            archive_fingerprint="new_fp",
            archive_is_complete=True,
            archive_active_or_incomplete=False,
            burn_id="burn_new_1234567890ab",
        )
        self.assertIn("neuer Archivplatz 1 erkannt", event_new)
        self.assertIn("Treffer 1/2", event_new)
        self.assertFalse(tracker.confirmed_complete)

        # Zweite Beobachtung mit gleicher Burn-ID -> Bestätigung
        event_confirm = tracker.observe(
            live_flap=0,
            archive_fingerprint="new_fp",
            archive_is_complete=True,
            archive_active_or_incomplete=False,
            burn_id="burn_new_1234567890ab",
        )
        self.assertIn("BESTÄTIGT", event_confirm)
        self.assertTrue(tracker.confirmed_complete)


class ArchiveCompletionProbeRunTests(unittest.TestCase):
    def test_run_probe_creates_valid_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            logs: list[str] = []

            # We create a run with stop_check returning True after 1 sample
            run_count = 0

            def stop_check() -> bool:
                nonlocal run_count
                run_count += 1
                return run_count > 1

            # Mock live raw packet: 19 bytes with aacc3355 header
            # packet: header(4) + status(2) + status_raw(1) + temp(2) + flap(1) + burn_h(1) + burn_m(1) + ...
            # status_raw=0x00, temp=200 (0x00c8), flap=0 (0x00), burn_h=2, burn_m=45
            live_hex = "aacc335500000000c800022d00000000000000"

            import tools.archive_completion_probe_v1_0_0 as probe_mod

            orig_fetch = probe_mod.fetch_live_raw
            probe_mod.fetch_live_raw = lambda url, timeout: live_hex

            try:
                log_path = run_probe(
                    live_url="http://mock/direct/00",
                    interval=1.0,
                    inter_request_delay=0.01,
                    timeout=1,
                    slot=1,
                    output_dir=out_dir,
                    max_samples=1,
                    sleep_fn=lambda _: None,
                    logger=logs.append,
                )
                self.assertTrue(log_path.exists())
                lines = log_path.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)

                data = json.loads(lines[0])
                self.assertEqual(data["live_temperature_c"], 200)
                self.assertEqual(data["live_flap_percent"], 0)
                self.assertEqual(data["live_burn_time"], "2:45")
                self.assertEqual(data["archive_slot"], 1)
            finally:
                probe_mod.fetch_live_raw = orig_fetch


if __name__ == "__main__":
    unittest.main()
