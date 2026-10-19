# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridge.settings import (
    SettingsManager,
    SettingsState,
    SettingsStateStorage,
)
from protocol.device_diagnostics import (
    ControllerSettings,
    DeviceDiagnosticsReadError,
)
from protocol.models import LiveStatus


class FakeDiagnosticsClient:
    def __init__(self, initial_delay: int = 50) -> None:
        self.current_delay = initial_delay
        self.read_calls = 0
        self.set_calls: list[int] = []
        self.fail_read = False
        self.fail_write = False

    def read_controller_settings(self) -> ControllerSettings:
        self.read_calls += 1
        if self.fail_read:
            raise DeviceDiagnosticsReadError("Verbindungsfehler")
        return ControllerSettings(
            closing_delay_minutes=self.current_delay,
            raw_payload="0101320004b0005001e0",
            raw="aacc33550b120101320004b0005001e02b02",
        )

    def set_closing_delay(
        self,
        new_delay_minutes: int,
        current_settings: ControllerSettings | None = None,
    ) -> ControllerSettings:
        self.set_calls.append(new_delay_minutes)
        if self.fail_write:
            raise DeviceDiagnosticsReadError("Schreibfehler")
        self.current_delay = new_delay_minutes
        return ControllerSettings(
            closing_delay_minutes=new_delay_minutes,
            raw_payload="0101" + f"{new_delay_minutes:02x}" + "0004b0005001e0",
            raw="dummy",
        )


class FakePublisher:
    def __init__(self) -> None:
        self.delays: list[int] = []
        self.locks: list[bool] = []

    def publish_closing_delay(self, minutes: int) -> None:
        self.delays.append(minutes)

    def publish_settings_lock(self, unlocked: bool) -> None:
        self.locks.append(unlocked)


class FakeClock:
    def __init__(self, current: float = 1000.0) -> None:
        self.now = current

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SettingsManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "state.json"
        self.storage = SettingsStateStorage(self.storage_path)
        self.diagnostics = FakeDiagnosticsClient(initial_delay=50)
        self.publisher = FakePublisher()
        self.clock = FakeClock()
        self.messages: list[str] = []
        self.manager = SettingsManager(
            storage=self.storage,
            diagnostics_client=self.diagnostics,
            publisher=self.publisher,
            unlock_timeout_seconds=300.0,
            clock=self.clock,
            logger=self.messages.append,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_state_storage_roundtrip(self) -> None:
        state = SettingsState(
            closing_delay_minutes=45,
            raw_payload="test",
            last_updated_at="2026-10-19T12:00:00+02:00",
        )
        self.storage.save(state)
        loaded = self.storage.load()
        self.assertEqual(loaded.closing_delay_minutes, 45)
        self.assertEqual(loaded.raw_payload, "test")

    def test_default_state_when_storage_missing(self) -> None:
        missing_storage = SettingsStateStorage(
            Path(self.temp_dir.name) / "missing.json"
        )
        state = missing_storage.load()
        self.assertEqual(state.closing_delay_minutes, 60)

    def test_refresh_from_controller_updates_state_and_publishes(self) -> None:
        self.manager.refresh_from_controller()
        self.assertEqual(self.manager.current_state.closing_delay_minutes, 50)
        self.assertEqual(self.publisher.delays, [50])
        loaded = self.storage.load()
        self.assertEqual(loaded.closing_delay_minutes, 50)

    def test_refresh_handles_controller_error(self) -> None:
        self.diagnostics.fail_read = True
        self.manager.refresh_from_controller()
        self.assertTrue(any("konnten nicht gelesen werden" in msg for msg in self.messages))

    def test_write_rejected_when_locked(self) -> None:
        self.assertFalse(self.manager.is_unlocked)
        result = self.manager.handle_closing_delay_command("45", live_status=None)
        self.assertFalse(result)
        self.assertEqual(self.diagnostics.set_calls, [])
        self.assertTrue(any("Schreibschutz ist aktiv" in msg for msg in self.messages))
        # Reverts/publishes current value to HA
        self.assertEqual(self.publisher.delays, [60])

    def test_unlock_timeout_and_auto_lock(self) -> None:
        self.manager.handle_lock_command("ON")
        self.assertTrue(self.manager.is_unlocked)
        self.assertEqual(self.publisher.locks, [True])

        # After 200 seconds still unlocked
        self.clock.advance(200.0)
        self.assertTrue(self.manager.is_unlocked)
        self.manager.check_auto_lock()
        self.assertEqual(self.publisher.locks, [True])

        # After 301 seconds expired
        self.clock.advance(101.0)
        self.assertFalse(self.manager.is_unlocked)
        self.manager.check_auto_lock()
        self.assertEqual(self.publisher.locks, [True, False])
        self.assertTrue(any("Freigabefenster abgelaufen" in msg for msg in self.messages))

    def test_manual_lock_command(self) -> None:
        self.manager.handle_lock_command("ON")
        self.assertTrue(self.manager.is_unlocked)
        self.manager.handle_lock_command("OFF")
        self.assertFalse(self.manager.is_unlocked)
        self.assertEqual(self.publisher.locks, [True, False])

    def test_write_rejected_when_flap_moving(self) -> None:
        self.manager.handle_lock_command("ON")
        moving_status = LiveStatus(
            temperature_c=250,
            flap_percent=50,
            flap_moving=True,
            burn_hours=0,
            burn_minutes=30,
            burn_total_minutes=30,
            door_open=False,
            fan_raw=1,
            status_raw=1,
            raw="dummy",
        )
        result = self.manager.handle_closing_delay_command("45", live_status=moving_status)
        self.assertFalse(result)
        self.assertEqual(self.diagnostics.set_calls, [])
        self.assertTrue(any("Luftklappe bewegt sich" in msg for msg in self.messages))

    def test_write_rejected_when_out_of_range(self) -> None:
        self.manager.handle_lock_command("ON")
        result = self.manager.handle_closing_delay_command("150", live_status=None)
        self.assertFalse(result)
        self.assertEqual(self.diagnostics.set_calls, [])
        self.assertTrue(any("au\u00dferhalb des erlaubten Bereichs" in msg for msg in self.messages))

    def test_write_rejected_when_invalid_number(self) -> None:
        self.manager.handle_lock_command("ON")
        result = self.manager.handle_closing_delay_command("abc", live_status=None)
        self.assertFalse(result)
        self.assertEqual(self.diagnostics.set_calls, [])
        self.assertTrue(any("Ung\u00fcltiger Wert" in msg for msg in self.messages))

    def test_successful_write_updates_state_storage_and_publishes(self) -> None:
        self.manager.handle_lock_command("ON")
        result = self.manager.handle_closing_delay_command("45", live_status=None)
        self.assertTrue(result)
        self.assertEqual(self.diagnostics.set_calls, [45])
        self.assertEqual(self.manager.current_state.closing_delay_minutes, 45)
        self.assertEqual(self.publisher.delays, [45])
        loaded = self.storage.load()
        self.assertEqual(loaded.closing_delay_minutes, 45)
        self.assertTrue(any("erfolgreich auf 45 min gesetzt" in msg for msg in self.messages))

    def test_failed_write_logs_error_and_reverts(self) -> None:
        self.manager.handle_lock_command("ON")
        self.diagnostics.fail_write = True
        result = self.manager.handle_closing_delay_command("45", live_status=None)
        self.assertFalse(result)
        self.assertTrue(any("Fehler beim Setzen der Schlie\u00dfzeitverz\u00f6gerung" in msg for msg in self.messages))
        self.assertEqual(self.publisher.delays, [60])


if __name__ == "__main__":
    unittest.main()
