#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die MQTT-Abbildung dekodierter Archivdaten."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from bridge.archive import build_archive_attributes


class ArchiveAttributesTests(unittest.TestCase):
    def test_build_archive_attributes_preserves_payload(self) -> None:
        record = SimpleNamespace(
            archive_number=3,
            timestamp=datetime(2026, 4, 11, 2, 21),
            measurement_count=121,
            start_temperature_c=48,
            end_temperature_c=272,
            max_temperature_c=620,
            max_temperature_minute=30,
            stage_90_minute=2,
            stage_75_minute=41,
            stage_50_minute=51,
            stage_25_minute=104,
            stage_0_minute=164,
            temperatures=[48, 69, 119],
        )

        attributes = build_archive_attributes(record)

        self.assertEqual(attributes["archive_number"], 3)
        self.assertEqual(attributes["start"], "2026-04-11T02:21")
        self.assertEqual(attributes["max_temperature_c"], 620)
        self.assertEqual(attributes["duration_minutes"], 164)
        self.assertEqual(
            attributes["duration_source"],
            "stage_0_unwrapped",
        )
        self.assertEqual(
            attributes["temperatures_c"],
            [48, 69, 119],
        )


if __name__ == "__main__":
    unittest.main()
