#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.application."""

from __future__ import annotations

import signal
import sys
import types
import unittest
from typing import Any


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

from bridge.application import BridgeApplication, RunningState


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


if __name__ == "__main__":
    unittest.main()
