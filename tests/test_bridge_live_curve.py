#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.live_curve."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bridge.live_curve import (
    LIVE_CURVE_SCHEMA_VERSION,
    LiveCurvePoint,
    LiveCurveSession,
    LiveCurveStorageError,
    create_default_live_curve_storage,
)
from protocol.models import LiveStatus


def live_status(temperature_c: int = 120) -> LiveStatus:
    return LiveStatus(
        temperature_c=temperature_c,
        flap_percent=75,
        flap_moving=False,
        burn_hours=0,
        burn_minutes=12,
        burn_total_minutes=12,
        door_open=False,
        fan_raw=1,
        status_raw=32,
        raw="aacc3355",
    )


def live_point(
    observed_at: datetime,
    temperature_c: int = 120,
) -> LiveCurvePoint:
    return LiveCurvePoint.from_status(
        live_status(temperature_c),
        observed_at=observed_at,
    )


class LiveCurveModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.started_at = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)
        self.first = live_point(self.started_at)

    def test_point_copies_relevant_live_status_fields(self) -> None:
        point = self.first

        self.assertEqual(point.temperature_c, 120)
        self.assertEqual(point.burn_total_minutes, 12)
        self.assertEqual(point.status_raw, 32)
        self.assertEqual(point.flap_percent, 75)
        self.assertFalse(point.door_open)

    def test_point_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "Zeitzone"):
            live_point(datetime(2026, 11, 4, 18, 30))

    def test_session_append_is_immutable(self) -> None:
        session = LiveCurveSession.start(
            session_id="session-2026-11-04",
            point=self.first,
        )
        second = live_point(
            self.started_at + timedelta(seconds=10),
            temperature_c=125,
        )

        updated = session.append(second)

        self.assertEqual(len(session.points), 1)
        self.assertEqual(updated.points, (self.first, second))
        self.assertEqual(updated.updated_at, second.observed_at)

    def test_session_rejects_unsorted_points(self) -> None:
        later = live_point(self.started_at + timedelta(seconds=10))
        earlier = live_point(self.started_at)

        with self.assertRaisesRegex(ValueError, "zeitlich sortiert"):
            LiveCurveSession(
                session_id="unsorted",
                started_at=later.observed_at,
                points=(later, earlier),
            )


class LiveCurveStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project_dir = Path(self.temporary_directory.name)
        self.storage = create_default_live_curve_storage(self.project_dir)
        self.started_at = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)
        self.session = LiveCurveSession.start(
            session_id="session-2026-11-04",
            point=live_point(self.started_at),
        ).append(
            live_point(
                self.started_at + timedelta(seconds=10),
                temperature_c=125,
            )
        )

    def test_default_storage_uses_project_data_directory(self) -> None:
        self.assertEqual(
            self.storage.path,
            self.project_dir.resolve()
            / "data"
            / "live-curve"
            / "current.json",
        )

    def test_missing_session_returns_none(self) -> None:
        self.assertIsNone(self.storage.load())

    def test_save_and_load_round_trip(self) -> None:
        self.storage.save(self.session)

        loaded = self.storage.load()

        self.assertEqual(loaded, self.session)

    def test_save_uses_versioned_schema_and_removes_temporary_file(
        self,
    ) -> None:
        self.storage.save(self.session)

        payload = json.loads(self.storage.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], LIVE_CURVE_SCHEMA_VERSION)
        self.assertEqual(payload["point_count"], 2)
        self.assertEqual(payload["points"][1]["temperature_c"], 125)
        self.assertFalse(
            self.storage.path.with_suffix(".json.tmp").exists()
        )

    def test_second_save_replaces_previous_snapshot(self) -> None:
        self.storage.save(self.session)
        updated = self.session.append(
            live_point(
                self.started_at + timedelta(seconds=20),
                temperature_c=130,
            )
        )

        self.storage.save(updated)

        self.assertEqual(self.storage.load(), updated)

    def test_corrupted_json_is_reported(self) -> None:
        self.storage.path.parent.mkdir(parents=True)
        self.storage.path.write_text("{broken", encoding="utf-8")

        with self.assertRaisesRegex(LiveCurveStorageError, "nicht lesbar"):
            self.storage.load()

    def test_inconsistent_point_count_is_rejected(self) -> None:
        self.storage.save(self.session)
        payload = json.loads(self.storage.path.read_text(encoding="utf-8"))
        payload["point_count"] = 99
        self.storage.path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(LiveCurveStorageError, "point_count"):
            self.storage.load()

    def test_clear_removes_current_session(self) -> None:
        self.storage.save(self.session)

        self.storage.clear()

        self.assertFalse(self.storage.path.exists())
        self.assertIsNone(self.storage.load())


if __name__ == "__main__":
    unittest.main()
