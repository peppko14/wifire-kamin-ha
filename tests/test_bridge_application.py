#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.application."""

from __future__ import annotations

import signal
import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


try:
    import paho.mqtt.client  # noqa: F401
except ModuleNotFoundError:
    paho_module = types.ModuleType("paho")
    mqtt_package = types.ModuleType("paho.mqtt")
    mqtt_client_module = types.ModuleType("paho.mqtt.client")

    class StubClient:
        pass

    class StubCallbackApiVersion:
        VERSION2 = 2

    mqtt_client_module.Client = StubClient
    mqtt_client_module.CallbackAPIVersion = StubCallbackApiVersion
    mqtt_package.client = mqtt_client_module
    paho_module.mqtt = mqtt_package
    sys.modules["paho"] = paho_module
    sys.modules["paho.mqtt"] = mqtt_package
    sys.modules["paho.mqtt.client"] = mqtt_client_module

if "config" not in sys.modules:
    config_module = types.ModuleType("config")
    config_module.REQUEST_TIMEOUT = 5
    config_module.WIFIRE_URL = "http://192.0.2.1/direct/00"
    sys.modules["config"] = config_module

from bridge.application import (
    BridgeApplication,
    LiveStateHandler,
    RunningState,
    build_archive_sync_settings,
    create_application,
    refresh_archive_outputs,
    refresh_history_outputs,
)
from protocol.models import LiveStatus


class FakeConnection:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class FakeRuntime:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    def run(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


class FakeReporter:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    def refresh(self) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return None


def live_status() -> LiveStatus:
    return LiveStatus(
        temperature_c=80,
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


class LiveStateHandlerTests(unittest.TestCase):
    def test_state_is_remembered_before_curve_is_recorded(self) -> None:
        calls: list[tuple[str, LiveStatus]] = []
        state = live_status()
        memory = types.SimpleNamespace(
            remember_state=lambda value: calls.append(("memory", value))
        )
        recorder = types.SimpleNamespace(
            observe=lambda value: calls.append(("curve", value))
        )
        publisher = types.SimpleNamespace(
            publish_live_curve=lambda value: calls.append(
                ("publish", state)
            )
        )
        handler = LiveStateHandler(memory, recorder, publisher)

        handler(state)

        self.assertEqual(
            calls,
            [
                ("memory", state),
                ("curve", state),
                ("publish", state),
            ],
        )


class RunningStateTests(unittest.TestCase):
    def test_state_is_running_initially(self) -> None:
        state = RunningState()

        self.assertTrue(state())

    def test_stop_changes_running_state(self) -> None:
        state = RunningState()

        state.stop(signal.SIGTERM, None)

        self.assertFalse(state())


class BridgeApplicationTests(unittest.TestCase):
    def create_application(
        self,
        *,
        runtime_error: Exception | None = None,
    ) -> tuple[
        BridgeApplication,
        FakeConnection,
        FakeRuntime,
        list[tuple[int, Any]],
        list[str],
    ]:
        connection = FakeConnection()
        runtime = FakeRuntime(runtime_error)
        registrations: list[tuple[int, Any]] = []
        messages: list[str] = []
        application = BridgeApplication(
            connection=connection,
            runtime=runtime,
            running_state=RunningState(),
            logger=messages.append,
            signal_registrar=(
                lambda number, handler: registrations.append(
                    (number, handler)
                )
            ),
        )
        return (
            application,
            connection,
            runtime,
            registrations,
            messages,
        )

    def test_signal_handlers_are_registered(self) -> None:
        application, _, _, registrations, _ = (
            self.create_application()
        )

        application.install_signal_handlers()

        self.assertEqual(
            [number for number, _ in registrations],
            [signal.SIGINT, signal.SIGTERM],
        )

    def test_run_starts_runtime_and_stops_connection(self) -> None:
        application, connection, runtime, _, messages = (
            self.create_application()
        )

        application.run()

        self.assertEqual(connection.started, 1)
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(connection.stopped, 1)
        self.assertEqual(
            messages,
            ["WiFire-Kamin MQTT Bridge beendet."],
        )

    def test_runtime_error_still_stops_connection(self) -> None:
        application, connection, _, _, _ = (
            self.create_application(
                runtime_error=RuntimeError("failed")
            )
        )

        with self.assertRaisesRegex(RuntimeError, "failed"):
            application.run()

        self.assertEqual(connection.stopped, 1)


class ArchiveSettingsTests(unittest.TestCase):
    def test_defaults_use_the_technical_scan_limit(self) -> None:
        config = types.SimpleNamespace(
            WIFIRE_URL="http://192.0.2.1/direct/00"
        )

        settings = build_archive_sync_settings(config)

        self.assertEqual(settings.first_archive, 1)
        self.assertEqual(settings.last_archive, 255)
        self.assertEqual(settings.archive_delay_seconds, 10)
        self.assertEqual(settings.max_consecutive_read_errors, 3)
        settings.validate()

    def test_explicit_archive_settings_are_preserved(self) -> None:
        config = types.SimpleNamespace(
            WIFIRE_URL="http://192.0.2.1/direct/00",
            ARCHIVE_FIRST_SLOT=2,
            ARCHIVE_LAST_SLOT=20,
            ARCHIVE_REQUEST_TIMEOUT=20,
            ARCHIVE_RETRY_COUNT=4,
            ARCHIVE_RETRY_DELAY=12,
            ARCHIVE_REQUEST_DELAY=15,
            ARCHIVE_MAX_CONSECUTIVE_READ_ERRORS=2,
        )

        settings = build_archive_sync_settings(config)

        self.assertEqual(settings.first_archive, 2)
        self.assertEqual(settings.last_archive, 20)
        self.assertEqual(settings.request_timeout, 20)
        self.assertEqual(settings.retry_count, 4)
        self.assertEqual(settings.retry_delay_seconds, 12)
        self.assertEqual(settings.archive_delay_seconds, 15)
        self.assertEqual(settings.max_consecutive_read_errors, 2)


class HistoryOutputRefreshTests(unittest.TestCase):
    def test_reporters_are_refreshed_independently(self) -> None:
        statistics = FakeReporter(RuntimeError("Statistik defekt"))
        dashboard = FakeReporter()
        messages: list[str] = []

        refresh_history_outputs(
            statistics,
            dashboard,
            logger=messages.append,
        )

        self.assertEqual(statistics.calls, 1)
        self.assertEqual(dashboard.calls, 1)
        self.assertTrue(
            any("Statistik defekt" in message for message in messages)
        )

    def test_device_diagnostics_isolated_from_history_reporters(self) -> None:
        statistics = FakeReporter(RuntimeError("Statistik defekt"))
        dashboard = FakeReporter()
        diagnostics = FakeReporter()

        refresh_archive_outputs(
            statistics,
            dashboard,
            diagnostics,
            logger=lambda message: None,
        )

        self.assertEqual(statistics.calls, 1)
        self.assertEqual(dashboard.calls, 1)
        self.assertEqual(diagnostics.calls, 1)

    def test_device_diagnostics_failure_does_not_escape(self) -> None:
        diagnostics = FakeReporter(RuntimeError("Diagnose defekt"))
        messages: list[str] = []

        refresh_archive_outputs(
            FakeReporter(),
            FakeReporter(),
            diagnostics,
            logger=messages.append,
        )

        self.assertTrue(
            any("Diagnose defekt" in message for message in messages)
        )


class ApplicationAssemblyTests(unittest.TestCase):
    def test_one_central_logger_is_injected_into_runtime_components(
        self,
    ) -> None:
        messages: list[str] = []
        logger = messages.append
        captured: dict[str, Any] = {}
        publisher = types.SimpleNamespace()
        connection = types.SimpleNamespace(
            publisher=publisher,
            remember_state=lambda state: None,
            start=lambda: None,
            stop=lambda: None,
        )
        history_manager = types.SimpleNamespace(
            storage=types.SimpleNamespace(directory=Path("data/history")),
        )

        def connection_factory(*args: Any, **kwargs: Any) -> Any:
            captured["connection_logger"] = kwargs["logger"]
            return connection

        def manager_factory(*args: Any, **kwargs: Any) -> Any:
            captured["storage_logger"] = kwargs["logger"]
            return history_manager

        def statistics_factory(*args: Any, **kwargs: Any) -> FakeReporter:
            captured["statistics_logger"] = kwargs["logger"]
            return FakeReporter()

        def dashboard_factory(*args: Any, **kwargs: Any) -> FakeReporter:
            captured["dashboard_logger"] = kwargs["logger"]
            return FakeReporter()

        def diagnostics_factory(*args: Any, **kwargs: Any) -> FakeReporter:
            captured["diagnostics_logger"] = kwargs["logger"]
            return FakeReporter()

        config = types.SimpleNamespace(
            LOG_LEVEL="DEBUG",
            DEVICE_ID="wifire_kamin",
            MQTT_DISCOVERY_PREFIX="homeassistant",
            WIFIRE_URL="http://192.0.2.1/direct/00",
        )

        with patch(
            "bridge.application.configure_logging",
            return_value=logger,
        ), patch(
            "bridge.application.MqttConnection",
            side_effect=connection_factory,
        ), patch(
            "bridge.application.create_default_history_manager",
            side_effect=manager_factory,
        ), patch(
            "bridge.application.HistoryStatisticsReporter",
            side_effect=statistics_factory,
        ), patch(
            "bridge.application.DashboardCurveReporter",
            side_effect=dashboard_factory,
        ), patch(
            "bridge.application.DeviceDiagnosticsReporter",
            side_effect=diagnostics_factory,
        ):
            application = create_application(
                config,
                project_dir=Path("."),
                app_name="WiFire Bridge",
                app_version="0.12.5",
            )

        runtime = application.runtime
        self.assertIs(application.logger, logger)
        self.assertIs(runtime.logger, logger)
        self.assertIs(runtime.live_poller.logger, logger)
        self.assertIs(runtime.archive_synchronizer.logger, logger)
        self.assertIs(runtime.on_state.curve_recorder.logger, logger)
        self.assertIs(runtime.on_state.curve_publisher, publisher)
        self.assertEqual(
            runtime.on_state.curve_recorder.storage.path,
            Path("data/live-curve/current.json").resolve(),
        )
        self.assertIs(captured["connection_logger"], logger)
        self.assertIs(captured["storage_logger"], logger)
        self.assertIs(captured["statistics_logger"], logger)
        self.assertIs(captured["dashboard_logger"], logger)
        self.assertIs(captured["diagnostics_logger"], logger)


if __name__ == "__main__":
    unittest.main()
