#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.mqtt_client."""

from __future__ import annotations

from dataclasses import replace
import json
import sys
import types
import unittest
from types import SimpleNamespace
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

from bridge.mqtt_client import MqttConnection
from bridge.topics import MqttTopics
from protocol.models import LiveStatus


class FakeReasonCode:
    def __init__(self, failure: bool) -> None:
        self.is_failure = failure

    def __str__(self) -> str:
        return "fake-reason"


class FakeClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.init_args = args
        self.init_kwargs = kwargs
        self.on_connect: Any = None
        self.on_message: Any = None
        self.on_disconnect: Any = None
        self.credentials: tuple[str, str] | None = None
        self.will: tuple[Any, ...] | None = None
        self.reconnect: tuple[int, int] | None = None
        self.published: list[tuple[str, Any, int, bool]] = []
        self.subscriptions: list[tuple[str, int]] = []
        self.connect_calls: list[tuple[str, int, int]] = []
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False
        self.connect_error: Exception | None = None

    def username_pw_set(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def will_set(
        self,
        topic: str,
        *,
        payload: str,
        qos: int,
        retain: bool,
    ) -> None:
        self.will = (topic, payload, qos, retain)

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        self.reconnect = (min_delay, max_delay)

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int,
        retain: bool,
    ) -> None:
        self.published.append((topic, payload, qos, retain))

    def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append((topic, qos))

    def connect_async(
        self,
        host: str,
        port: int,
        *,
        keepalive: int,
    ) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connect_calls.append((host, port, keepalive))

    def loop_start(self) -> None:
        self.loop_started = True

    def loop_stop(self) -> None:
        self.loop_stopped = True

    def disconnect(self) -> None:
        self.disconnected = True


def create_config(username: str = "mqtt-user") -> SimpleNamespace:
    return SimpleNamespace(
        MQTT_HOST="broker.local",
        MQTT_PORT=1883,
        MQTT_USERNAME=username,
        MQTT_PASSWORD="secret",
        DEVICE_ID="wifire_kamin",
        DEVICE_NAME="WiFire-Kamin",
        MANUFACTURER="FireControls",
        MODEL="WiFire",
        ENABLE_FAN_ENTITY=False,
    )


class MqttConnectionTests(unittest.TestCase):
    def create_connection(
        self,
        *,
        username: str = "mqtt-user",
        running: bool = True,
    ) -> tuple[MqttConnection, FakeClient, list[str], list[float]]:
        client = FakeClient()
        messages: list[str] = []
        sleeps: list[float] = []

        def client_factory(*args: Any, **kwargs: Any) -> FakeClient:
            client.init_args = args
            client.init_kwargs = kwargs
            return client

        connection = MqttConnection(
            create_config(username),
            MqttTopics("wifire_kamin"),
            app_name="WiFire Bridge",
            app_version="0.6.1",
            is_running=lambda: running,
            client_factory=client_factory,
            logger=messages.append,
            sleep=sleeps.append,
        )
        return connection, client, messages, sleeps

    def test_client_is_configured_with_login_will_and_reconnect(self) -> None:
        connection, client, _, _ = self.create_connection()

        self.assertIsNotNone(connection.publisher)
        self.assertEqual(client.credentials, ("mqtt-user", "secret"))
        self.assertEqual(
            client.will,
            (
                "wifire_kamin/wifire_kamin/availability",
                "offline",
                1,
                True,
            ),
        )
        self.assertEqual(client.reconnect, (2, 60))
        self.assertEqual(client.init_kwargs["client_id"], "wifire_kamin_bridge")
        self.assertTrue(client.init_kwargs["reconnect_on_failure"])

    def test_empty_username_skips_login(self) -> None:
        _, client, _, _ = self.create_connection(username="")

        self.assertIsNone(client.credentials)

    def test_callbacks_are_registered(self) -> None:
        connection, client, _, _ = self.create_connection()

        self.assertEqual(client.on_connect, connection.on_connect)
        self.assertEqual(client.on_message, connection.on_message)
        self.assertEqual(client.on_disconnect, connection.on_disconnect)

    def test_start_connects_and_starts_loop(self) -> None:
        connection, client, messages, _ = self.create_connection()

        connection.start()

        self.assertEqual(
            client.connect_calls,
            [("broker.local", 1883, 60)],
        )
        self.assertTrue(client.loop_started)
        self.assertIn("broker.local:1883", messages[0])

    def test_stop_publishes_offline_and_disconnects(self) -> None:
        connection, client, _, sleeps = self.create_connection()

        connection.stop()

        self.assertEqual(client.published[-1][1], "offline")
        self.assertEqual(sleeps, [0.2])
        self.assertTrue(client.loop_stopped)
        self.assertTrue(client.disconnected)

    def test_successful_connect_publishes_discovery_and_state(self) -> None:
        connection, client, messages, _ = self.create_connection()
        state = LiveStatus(
            temperature_c=24,
            flap_percent=100,
            flap_moving=False,
            burn_hours=0,
            burn_minutes=12,
            burn_total_minutes=12,
            door_open=False,
            fan_raw=1,
            status_raw=1,
            raw="raw-live-data",
        )
        connection.remember_state(state)

        connection.on_connect(
            client,
            None,
            None,
            FakeReasonCode(False),
            None,
        )

        self.assertEqual(
            client.subscriptions,
            [("homeassistant/status", 1)],
        )
        published_topics = [item[0] for item in client.published]
        self.assertIn(
            "homeassistant/device/wifire_kamin/config",
            published_topics,
        )
        self.assertIn(
            "wifire_kamin/wifire_kamin/state",
            published_topics,
        )
        discovery = json.loads(client.published[0][1])
        self.assertEqual(discovery["device"]["sw_version"], "0.6.1")
        self.assertIn("Mit MQTT verbunden.", messages)

    def test_remember_state_uses_stable_snapshot(self) -> None:
        connection, _, _, _ = self.create_connection()
        first = LiveStatus(
            temperature_c=24,
            flap_percent=100,
            flap_moving=False,
            burn_hours=0,
            burn_minutes=12,
            burn_total_minutes=12,
            door_open=False,
            fan_raw=1,
            status_raw=1,
            raw="first",
        )
        second = replace(first, temperature_c=25, raw="second")

        connection.remember_state(first)
        snapshot = connection.latest_state_snapshot()
        connection.remember_state(second)

        self.assertIs(snapshot, first)
        self.assertIs(connection.latest_state_snapshot(), second)

    def test_failed_connect_does_not_publish(self) -> None:
        connection, client, messages, _ = self.create_connection()

        connection.on_connect(
            client,
            None,
            None,
            FakeReasonCode(True),
            None,
        )

        self.assertEqual(client.published, [])
        self.assertIn("fehlgeschlagen", messages[0])

    def test_home_assistant_online_republishes_discovery(self) -> None:
        connection, client, _, _ = self.create_connection()
        message = SimpleNamespace(
            topic="homeassistant/status",
            payload=b"online",
        )

        connection.on_message(client, None, message)

        published_topics = [item[0] for item in client.published]
        self.assertIn(
            "homeassistant/device/wifire_kamin/config",
            published_topics,
        )

    def test_unexpected_disconnect_is_logged_only_while_running(self) -> None:
        connection, client, messages, _ = self.create_connection(
            running=True
        )

        connection.on_disconnect(
            client,
            None,
            None,
            FakeReasonCode(True),
            None,
        )

        self.assertIn("unterbrochen", messages[0])


if __name__ == "__main__":
    unittest.main()
