# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from bridge.time_sync import (
    TimeSyncManager,
    TimeSyncState,
    TimeSyncStateStorage,
    can_synchronize,
    get_calendar_week,
    is_time_sync_due,
)
from protocol.device_diagnostics import ControllerTime
from protocol.models import LiveStatus


def make_live_status(
    *,
    temperature_c: int = 24,
    flap_percent: int = 0,
    flap_moving: bool = False,
    door_open: bool = False,
) -> LiveStatus:
    return LiveStatus(
        temperature_c=temperature_c,
        flap_percent=flap_percent,
        flap_moving=flap_moving,
        burn_hours=0,
        burn_minutes=0,
        burn_total_minutes=0,
        door_open=door_open,
        fan_raw=1,
        status_raw=32,
        raw="raw-status",
    )


class FakeDiagnosticsClient:
    def __init__(
        self,
        controller_time: datetime | None = None,
        fail_set: bool = False,
    ) -> None:
        self.time = controller_time or datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        self.fail_set = fail_set
        self.set_calls: list[datetime] = []
        self.read_calls: int = 0

    def read_controller_time(self) -> ControllerTime:
        self.read_calls += 1
        return ControllerTime(
            value=self.time,
            month_flags=16,
            raw="fake-raw",
        )

    def set_controller_time(self, target_time: datetime) -> ControllerTime:
        if self.fail_set:
            raise RuntimeError("Schreibzugriff verweigert")
        self.set_calls.append(target_time)
        self.time = target_time
        return ControllerTime(
            value=target_time,
            month_flags=16,
            raw="fake-raw",
        )


class FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def publish_time_sync_state(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


class TimeSyncDueTests(unittest.TestCase):
    def test_get_calendar_week(self) -> None:
        dt = datetime(2026, 10, 16, 12, 0)
        self.assertEqual(get_calendar_week(dt), "2026-W42")

    def test_due_on_regular_tuesday_morning(self) -> None:
        # 2026-10-13 ist ein Dienstag
        tuesday_0600 = datetime(2026, 10, 13, 6, 0)
        state = TimeSyncState(last_synced_week="2026-W41")

        due, reason = is_time_sync_due(tuesday_0600, state)
        self.assertTrue(due)
        self.assertIn("Regulärer Termin", reason)

    def test_not_due_before_tuesday_morning(self) -> None:
        # Montag 10:00 Uhr
        monday = datetime(2026, 10, 12, 10, 0)
        state = TimeSyncState(last_synced_week="2026-W41")

        due, reason = is_time_sync_due(monday, state)
        self.assertFalse(due)
        self.assertIn("Warte auf regulären Termin", reason)

        # Dienstag 05:59 Uhr
        tuesday_early = datetime(2026, 10, 13, 5, 59)
        due_early, _ = is_time_sync_due(tuesday_early, state)
        self.assertFalse(due_early)

    def test_catch_up_due_later_in_the_week(self) -> None:
        # Freitag oder Samstag (Dienstag wurde verpasst)
        friday = datetime(2026, 10, 16, 18, 0)
        state = TimeSyncState(last_synced_week="2026-W41")

        due, reason = is_time_sync_due(friday, state)
        self.assertTrue(due)
        self.assertIn("Nachhol-Termin", reason)

    def test_not_due_if_already_synced_this_week(self) -> None:
        current = datetime(2026, 10, 16, 18, 0)
        state = TimeSyncState(last_synced_week="2026-W42")

        due, reason = is_time_sync_due(current, state)
        self.assertFalse(due)
        self.assertEqual(reason, "Kalenderwoche bereits synchronisiert")

    def test_drift_guard_triggers_after_seven_days_with_large_drift(self) -> None:
        now = datetime(2026, 10, 20, 12, 0)
        state = TimeSyncState(
            last_synced_week="2026-W43",
            last_synced_at="2026-10-12T06:00:00",
        )

        due, reason = is_time_sync_due(now, state, drift_seconds=-120.0)
        self.assertTrue(due)
        self.assertIn("Drift-Guard", reason)


class TimeSyncSafetyGateTests(unittest.TestCase):
    def test_blocks_if_ntp_not_synchronized(self) -> None:
        allowed, reason = can_synchronize(
            make_live_status(),
            is_curve_active=False,
            ntp_synchronized=False,
        )
        self.assertFalse(allowed)
        self.assertIn("NTP", reason)

    def test_blocks_if_live_status_missing(self) -> None:
        allowed, reason = can_synchronize(
            None,
            is_curve_active=False,
            ntp_synchronized=True,
        )
        self.assertFalse(allowed)
        self.assertIn("Keine aktuellen Live-Daten", reason)

    def test_blocks_if_flap_open(self) -> None:
        allowed, reason = can_synchronize(
            make_live_status(flap_percent=75),
            is_curve_active=False,
            ntp_synchronized=True,
        )
        self.assertFalse(allowed)
        self.assertIn("Luftklappe steht bei 75 %", reason)

    def test_blocks_if_flap_moving(self) -> None:
        allowed, reason = can_synchronize(
            make_live_status(flap_percent=0, flap_moving=True),
            is_curve_active=False,
            ntp_synchronized=True,
        )
        self.assertFalse(allowed)
        self.assertIn("bewegt sich aktuell", reason)

    def test_blocks_if_curve_active(self) -> None:
        allowed, reason = can_synchronize(
            make_live_status(),
            is_curve_active=True,
            ntp_synchronized=True,
        )
        self.assertFalse(allowed)
        self.assertIn("Brennkurven-Aufzeichnung", reason)

    def test_allows_when_fireplace_idle_and_ntp_ok(self) -> None:
        allowed, reason = can_synchronize(
            make_live_status(flap_percent=0, flap_moving=False),
            is_curve_active=False,
            ntp_synchronized=True,
        )
        self.assertTrue(allowed)
        self.assertIn("Freigegeben", reason)


class TimeSyncStorageTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            storage = TimeSyncStateStorage(path)

            initial = storage.load()
            self.assertEqual(initial.status, "idle")

            updated = TimeSyncState(
                last_synced_week="2026-W42",
                last_synced_at="2026-10-16T12:00:00",
                last_offset_seconds=-45.2,
                status="completed",
                message="Erfolgreich",
            )
            storage.save(updated)

            loaded = storage.load()
            self.assertEqual(loaded.last_synced_week, "2026-W42")
            self.assertEqual(loaded.last_offset_seconds, -45.2)
            self.assertEqual(loaded.status, "completed")


class TimeSyncManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = TimeSyncStateStorage(
            Path(self.temp_dir.name) / "state.json"
        )
        self.diagnostics_client = FakeDiagnosticsClient()
        self.publisher = FakePublisher()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_check_if_due_sets_blocked_when_fire_burning(self) -> None:
        now = datetime(2026, 10, 16, 12, 0)
        manager = TimeSyncManager(
            storage=self.storage,
            diagnostics_client=self.diagnostics_client,
            publisher=self.publisher,
            clock=lambda: now,
            host_time_check=lambda: True,
        )

        burning_status = make_live_status(flap_percent=80)
        res = manager.check_if_due(
            burning_status,
            is_curve_active=True,
        )

        self.assertFalse(res)
        self.assertEqual(manager.current_state.status, "blocked")
        self.assertIn("Luftklappe steht bei 80 %", manager.current_state.message)
        self.assertTrue(len(self.publisher.payloads) > 0)
        self.assertEqual(self.publisher.payloads[-1]["status"], "blocked")

    def test_check_if_due_executes_sync_when_idle(self) -> None:
        now = datetime(2026, 10, 16, 12, 0)
        manager = TimeSyncManager(
            storage=self.storage,
            diagnostics_client=self.diagnostics_client,
            publisher=self.publisher,
            clock=lambda: now,
            host_time_check=lambda: True,
        )

        idle_status = make_live_status(flap_percent=0)
        res = manager.check_if_due(
            idle_status,
            is_curve_active=False,
        )

        self.assertTrue(res)
        self.assertEqual(manager.current_state.status, "completed")
        self.assertEqual(manager.current_state.last_synced_week, "2026-W42")
        self.assertEqual(len(self.diagnostics_client.set_calls), 1)
        self.assertEqual(self.publisher.payloads[-1]["status"], "completed")

    def test_manual_trigger_verifies_safety_gates(self) -> None:
        now = datetime(2026, 10, 16, 12, 0)
        manager = TimeSyncManager(
            storage=self.storage,
            diagnostics_client=self.diagnostics_client,
            publisher=self.publisher,
            clock=lambda: now,
            host_time_check=lambda: True,
        )

        # 1. Sperre bei bewegender Klappe
        blocked_res = manager.trigger_manual_sync(
            make_live_status(flap_moving=True),
            is_curve_active=False,
        )
        self.assertFalse(blocked_res)
        self.assertEqual(manager.current_state.status, "blocked")

        # 2. Erfolg im Ruhezustand
        ok_res = manager.trigger_manual_sync(
            make_live_status(flap_percent=0, flap_moving=False),
            is_curve_active=False,
        )
        self.assertTrue(ok_res)
        self.assertEqual(manager.current_state.status, "completed")
        self.assertEqual(len(self.diagnostics_client.set_calls), 1)


if __name__ == "__main__":
    unittest.main()
