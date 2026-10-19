#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-Verbindungsverwaltung der WiFire-Kamin-Bridge."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Protocol

import paho.mqtt.client as mqtt

from bridge.discovery import build_discovery_payload
from bridge.logging_setup import log_error, log_warning
from bridge.publisher import MqttPublisher
from bridge.topics import MqttTopics
from protocol.models import LiveStatus

Logger = Callable[[str], None]
RunningCheck = Callable[[], bool]
SleepFunction = Callable[[float], None]
ClientFactory = Callable[..., mqtt.Client]


@dataclass(frozen=True, slots=True)
class MqttTlsSettings:
    """Validierte optionale TLS-Einstellungen der MQTT-Verbindung."""

    enabled: bool = False
    ca_cert: Path | None = None
    client_cert: Path | None = None
    client_key: Path | None = None
    insecure: bool = False

    @classmethod
    def from_config(cls, config: object) -> MqttTlsSettings:
        """Liest TLS-Werte rückwärtskompatibel aus der Konfiguration."""
        settings = cls(
            enabled=bool(getattr(config, "MQTT_TLS_ENABLED", False)),
            ca_cert=_optional_path(
                getattr(config, "MQTT_TLS_CA_CERT", None),
                "MQTT_TLS_CA_CERT",
            ),
            client_cert=_optional_path(
                getattr(config, "MQTT_TLS_CLIENT_CERT", None),
                "MQTT_TLS_CLIENT_CERT",
            ),
            client_key=_optional_path(
                getattr(config, "MQTT_TLS_CLIENT_KEY", None),
                "MQTT_TLS_CLIENT_KEY",
            ),
            insecure=bool(getattr(config, "MQTT_TLS_INSECURE", False)),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Verhindert widersprüchliche oder unsichere Teilkonfigurationen."""
        configured_paths = (
            self.ca_cert,
            self.client_cert,
            self.client_key,
        )
        if not self.enabled and (
            any(path is not None for path in configured_paths)
            or self.insecure
        ):
            raise ValueError(
                "MQTT-TLS-Optionen erfordern MQTT_TLS_ENABLED = True."
            )

        if (self.client_cert is None) != (self.client_key is None):
            raise ValueError(
                "MQTT_TLS_CLIENT_CERT und MQTT_TLS_CLIENT_KEY müssen "
                "gemeinsam gesetzt werden."
            )


def _optional_path(value: object, setting_name: str) -> Path | None:
    """Konvertiert einen optionalen Konfigurationswert in einen Pfad."""
    if value is None or value == "":
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(
            f"{setting_name} muss ein Dateipfad oder None sein."
        )
    return Path(value).expanduser()


def _path_text(path: Path | None) -> str | None:
    """Gibt einen optionalen pathlib-Pfad für Paho als Text zurück."""
    if path is None:
        return None
    return str(path)


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
        on_time_sync_command: Callable[[], None] | None = None,
        initial_time_sync_publisher: Callable[[], None] | None = None,
        on_closing_delay_command: Callable[[str], None] | None = None,
        on_settings_lock_command: Callable[[str], None] | None = None,
        initial_settings_publisher: Callable[[], None] | None = None,
        client_factory: ClientFactory = mqtt.Client,
        logger: Logger = print,
        sleep: SleepFunction = time.sleep,
    ) -> None:
        self.config = config
        self.topics = topics
        self.app_name = app_name
        self.app_version = app_version
        self.is_running = is_running
        self.on_time_sync_command = on_time_sync_command
        self.initial_time_sync_publisher = initial_time_sync_publisher
        self.on_closing_delay_command = on_closing_delay_command
        self.on_settings_lock_command = on_settings_lock_command
        self.initial_settings_publisher = initial_settings_publisher
        self.logger = logger
        self.sleep = sleep
        self.tls_settings = MqttTlsSettings.from_config(config)
        # loop_start() führt MQTT-Callbacks in einem eigenen Thread aus.
        # Der unveränderliche LiveStatus wird deshalb als kompletter Snapshot
        # unter einem Lock zwischen Haupt- und MQTT-Thread ausgetauscht.
        self._latest_state_lock = Lock()
        self._latest_state: LiveStatus | None = None

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

        self._configure_tls()

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

    def _configure_tls(self) -> None:
        """Aktiviert TLS vor dem ersten Verbindungsaufbau."""
        if not self.tls_settings.enabled:
            return

        self.client.tls_set(
            ca_certs=_path_text(self.tls_settings.ca_cert),
            certfile=_path_text(self.tls_settings.client_cert),
            keyfile=_path_text(self.tls_settings.client_key),
        )

        if self.tls_settings.insecure:
            self.client.tls_insecure_set(True)
            log_warning(
                self.logger,
                "WARNUNG: MQTT-TLS-Hostnameprüfung ist deaktiviert. "
                "MQTT_TLS_INSECURE nur vorübergehend zum Testen verwenden."
            )

    def remember_state(self, data: LiveStatus) -> None:
        """Merkt den letzten Live-Zustand für Neuverbindungen."""
        with self._latest_state_lock:
            self._latest_state = data

    def latest_state_snapshot(self) -> LiveStatus | None:
        """Liest einen stabilen Snapshot für den aufrufenden Thread."""
        with self._latest_state_lock:
            return self._latest_state

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
            log_error(
                self.logger,
                f"MQTT-Verbindung fehlgeschlagen: {reason_code}"
            )
            return

        self.logger("Mit MQTT verbunden.")
        client.subscribe(
            self.topics.home_assistant_status,
            qos=1,
        )
        client.subscribe(
            self.topics.time_sync_command,
            qos=1,
        )
        client.subscribe(
            self.topics.closing_delay_command,
            qos=1,
        )
        client.subscribe(
            self.topics.settings_lock_command,
            qos=1,
        )

        self.publish_discovery()
        self.publisher.publish_availability(True)

        if self.initial_time_sync_publisher is not None:
            self.initial_time_sync_publisher()

        if self.initial_settings_publisher is not None:
            self.initial_settings_publisher()

        latest_state = self.latest_state_snapshot()
        if latest_state is not None:
            self.publisher.publish_state(latest_state)

    def on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Verarbeitet eingehende MQTT-Nachrichten."""
        if message.topic == self.topics.time_sync_command:
            self.logger("MQTT-Befehl zur Zeitsynchronisation empfangen.")
            if self.on_time_sync_command is not None:
                self.on_time_sync_command()
            return

        if message.topic == self.topics.closing_delay_command:
            payload = message.payload.decode("utf-8", errors="replace").strip()
            self.logger(f"MQTT-Befehl Schließzeitverzögerung empfangen: {payload}")
            if self.on_closing_delay_command is not None:
                self.on_closing_delay_command(payload)
            return

        if message.topic == self.topics.settings_lock_command:
            payload = message.payload.decode("utf-8", errors="replace").strip().upper()
            self.logger(f"MQTT-Befehl Schreibschutz empfangen: {payload}")
            if self.on_settings_lock_command is not None:
                self.on_settings_lock_command(payload)
            return

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

        if self.initial_time_sync_publisher is not None:
            self.initial_time_sync_publisher()

        if self.initial_settings_publisher is not None:
            self.initial_settings_publisher()

        latest_state = self.latest_state_snapshot()
        if latest_state is not None:
            self.publisher.publish_state(latest_state)

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
            log_warning(
                self.logger,
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
            log_error(
                self.logger,
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
