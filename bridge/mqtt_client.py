#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-Verbindungsverwaltung der WiFire-Kamin-Bridge."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Protocol

import paho.mqtt.client as mqtt

from bridge.discovery import build_discovery_payload
from bridge.publisher import MqttPublisher
from bridge.topics import MqttTopics
from protocol.models import LiveStatus




Logger = Callable[[str], None]
RunningCheck = Callable[[], bool]
SleepFunction = Callable[[float], None]
ClientFactory = Callable[..., mqtt.Client]


class MqttConfig(Protocol):
    MQTT_HOST: str
    MQTT_PORT: int
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    DEVICE_ID: str
    DEVICE_NAME: str
    MANUFACTURER: str
    MODEL: str
    ENABLE_FAN_ENTITY: bool


class MqttConnection:
    """Kapselt MQTT-Client, Callbacks und Verbindungslebenszyklus."""

    def __init__(
        self,
        config: MqttConfig,
        topics: MqttTopics,
        *,
        app_name: str,
        app_version: str,
        is_running: RunningCheck,
        client_factory: ClientFactory = mqtt.Client,
        logger: Logger = print,
        sleep: SleepFunction = time.sleep,
    ) -> None:
        self.config = config
        self.topics = topics
        self.app_name = app_name
        self.app_version = app_version
        self.is_running = is_running
        self.logger = logger
        self.sleep = sleep
        self.latest_state: LiveStatus | None = None

        self.client = client_factory(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{config.DEVICE_ID}_bridge",
            reconnect_on_failure=True,
        )
        self.publisher = MqttPublisher(
            self.client,
            topics,
        )

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        if config.MQTT_USERNAME:
            self.client.username_pw_set(
                config.MQTT_USERNAME,
                config.MQTT_PASSWORD,
            )

        self.client.will_set(
            topics.availability,
            payload="offline",
            qos=1,
            retain=True,
        )
        self.client.reconnect_delay_set(
            min_delay=2,
            max_delay=60,
        )

    def remember_state(self, data: LiveStatus) -> None:
        """Merkt den letzten Live-Zustand für Neuverbindungen."""
        self.latest_state = data

    def publish_discovery(self) -> None:
        """Veröffentlicht die Home-Assistant-Device-Discovery."""
        payload = build_discovery_payload(
            self.config,
            self.topics,
            app_name=self.app_name,
            app_version=self.app_version,
        )

        self.client.publish(
            self.topics.device_discovery,
            payload=json.dumps(
                payload,
                ensure_ascii=False,
            ),
            qos=1,
            retain=True,
        )

        self.logger(
            f'Home-Assistant-Geräte-Discovery für '
            f'"{self.config.DEVICE_NAME}" veröffentlicht.'
        )

    def on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Verarbeitet eine hergestellte MQTT-Verbindung."""
        if reason_code.is_failure:
            self.logger(
                f"MQTT-Verbindung fehlgeschlagen: {reason_code}"
            )
            return

        self.logger("Mit MQTT verbunden.")
        client.subscribe(
            self.topics.home_assistant_status,
            qos=1,
        )

        self.publish_discovery()
        self.publisher.publish_availability(True)

        if self.latest_state is not None:
            self.publisher.publish_state(self.latest_state)

    def on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Reagiert auf den Home-Assistant-Onlinestatus."""
        if message.topic != self.topics.home_assistant_status:
            return

        payload = (
            message.payload.decode(
                "utf-8",
                errors="replace",
            )
            .strip()
            .lower()
        )

        if payload != "online":
            return

        self.logger(
            "Home Assistant ist online – "
            "Discovery wird erneut gesendet."
        )
        self.publish_discovery()
        self.publisher.publish_availability(True)

        if self.latest_state is not None:
            self.publisher.publish_state(self.latest_state)

    def on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Protokolliert unerwartete MQTT-Unterbrechungen."""
        if self.is_running() and reason_code.is_failure:
            self.logger(
                f"MQTT-Verbindung unterbrochen: {reason_code}"
            )

    def start(self) -> None:
        """Startet die asynchrone MQTT-Verbindung."""
        self.logger(
            f"Verbinde mit MQTT-Broker "
            f"{self.config.MQTT_HOST}:{self.config.MQTT_PORT} ..."
        )

        try:
            self.client.connect_async(
                self.config.MQTT_HOST,
                self.config.MQTT_PORT,
                keepalive=60,
            )
        except (OSError, ValueError) as error:
            self.logger(
                f"MQTT-Konfiguration ungültig: {error}"
            )
            raise

        self.client.loop_start()

    def stop(self) -> None:
        """Meldet das Gerät offline und beendet den MQTT-Client."""
        self.publisher.publish_availability(False)
        self.sleep(0.2)
        self.client.loop_stop()
        self.client.disconnect()
