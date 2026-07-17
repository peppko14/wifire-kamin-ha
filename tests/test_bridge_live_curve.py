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
    MAX_LIVE_CURVE_MQTT_PAYLOAD_BYTES,
    MAX_LIVE_CURVE_MQTT_POINTS,
    LiveCurvePoint,
    LiveCurvePayloadError,
    LiveCurveRecorder,
    LiveCurveSession,
    LiveCurveStorageError,
    build_live_curve_mqtt_payload,
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

    def test_session_id_rejects_path_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "unzulässige Zeichen"):
            LiveCurveSession.start(
                session_id="../outside",
                point=self.first,
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


class LiveCurveMqttPayloadTests(unittest.TestCase):
    def test_inactive_payload_is_explicit_and_empty(self) -> None:
        payload = build_live_curve_mqtt_payload(None)

        self.assertEqual(payload["status"], "inactive")
        self.assertEqual(payload["point_count"], 0)
        self.assertEqual(payload["temperatures_c"], [])

    def test_long_session_is_bounded_and_preserves_endpoints(self) -> None:
        started_at = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)
        points = tuple(
            live_point(
                started_at + timedelta(seconds=index * 10),
                temperature_c=40 + index,
            )
            for index in range(500)
        )
        session = LiveCurveSession(
            session_id="long-session",
            started_at=started_at,
            points=points,
        )

        payload = build_live_curve_mqtt_payload(session)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertEqual(payload["point_count"], 500)
        self.assertEqual(
            payload["published_point_count"],
            MAX_LIVE_CURVE_MQTT_POINTS,
        )
        self.assertEqual(payload["temperatures_c"][0], 40)
        self.assertEqual(payload["temperatures_c"][-1], 539)
        self.assertLessEqual(
            len(encoded),
            MAX_LIVE_CURVE_MQTT_PAYLOAD_BYTES,
        )

    def test_payload_limit_is_enforced(self) -> None:
        started_at = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)
        session = LiveCurveSession.start(
            session_id="small-limit",
            point=live_point(started_at),
        )

        with self.assertRaisesRegex(LiveCurvePayloadError, "größer"):
            build_live_curve_mqtt_payload(
                session,
                maximum_payload_bytes=1,
            )


class LiveCurveRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project_dir = Path(self.temporary_directory.name)
        self.storage = create_default_live_curve_storage(self.project_dir)
        self.started_at = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)
        self.messages: list[str] = []

    def create_recorder(
        self,
        *clock_values: datetime,
        end_after_inactive_samples: int = 3,
    ) -> LiveCurveRecorder:
        clock = iter(clock_values)
        return LiveCurveRecorder(
            storage=self.storage,
            active_temperature_c=40,
            end_after_inactive_samples=end_after_inactive_samples,
            clock=lambda: next(clock),
            session_id_factory=lambda: "live-session-1",
            logger=self.messages.append,
        )

    def test_cold_status_does_not_start_session(self) -> None:
        recorder = self.create_recorder(self.started_at)

        result = recorder.observe(live_status(temperature_c=39))

        self.assertIsNone(result)
        self.assertFalse(self.storage.path.exists())

    def test_active_status_starts_and_persists_session(self) -> None:
        recorder = self.create_recorder(self.started_at)

        result = recorder.observe(live_status(temperature_c=40))

        self.assertIsNotNone(result)
        self.assertEqual(self.storage.load(), result)
        self.assertIn("Live-Brennkurve gestartet", self.messages[0])

    def test_active_status_appends_to_existing_session(self) -> None:
        recorder = self.create_recorder(
            self.started_at,
            self.started_at + timedelta(seconds=10),
        )

        recorder.observe(live_status(temperature_c=80))
        result = recorder.observe(live_status(temperature_c=90))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result.points), 2)
        self.assertEqual(result.points[-1].temperature_c, 90)

    def test_transient_cold_sample_does_not_end_session(self) -> None:
        recorder = self.create_recorder(
            self.started_at,
            self.started_at + timedelta(seconds=10),
            self.started_at + timedelta(seconds=20),
            end_after_inactive_samples=2,
        )

        recorder.observe(live_status(temperature_c=80))
        recorder.observe(live_status(temperature_c=35))
        result = recorder.observe(live_status(temperature_c=45))

        self.assertIsNotNone(result)
        self.assertEqual(recorder.inactive_samples, 0)
        self.assertTrue(self.storage.path.exists())

    def test_consecutive_cold_samples_finalize_session(self) -> None:
        recorder = self.create_recorder(
            self.started_at,
            self.started_at + timedelta(seconds=10),
            self.started_at + timedelta(seconds=20),
            end_after_inactive_samples=2,
        )

        recorder.observe(live_status(temperature_c=80))
        recorder.observe(live_status(temperature_c=35))
        result = recorder.observe(live_status(temperature_c=34))

        self.assertIsNone(result)
        self.assertIsNone(recorder.current_session)
        self.assertFalse(self.storage.path.exists())
        completed = tuple(self.storage.completed_directory.glob("*.json"))
        self.assertEqual(len(completed), 1)
        payload = json.loads(completed[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["point_count"], 3)

    def test_new_recorder_resumes_persisted_session(self) -> None:
        first = self.create_recorder(self.started_at)
        first.observe(live_status(temperature_c=80))
        second = self.create_recorder(
            self.started_at + timedelta(seconds=10)
        )

        result = second.observe(live_status(temperature_c=90))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result.points), 2)
        self.assertTrue(
            any("wiederaufgenommen" in message for message in self.messages)
        )

    def test_corrupted_snapshot_disables_only_curve_recording(self) -> None:
        self.storage.path.parent.mkdir(parents=True)
        self.storage.path.write_text("{broken", encoding="utf-8")
        recorder = self.create_recorder(self.started_at)

        result = recorder.observe(live_status(temperature_c=80))

        self.assertIsNone(result)
        self.assertFalse(recorder.enabled)
        self.assertTrue(self.storage.path.exists())
        self.assertTrue(
            any("deaktiviert" in message for message in self.messages)
        )


if __name__ == "__main__":
    unittest.main()
