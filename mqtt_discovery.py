#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""WiFire-Kamin MQTT Bridge."""

from __future__ import annotations

import json
import signal
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

import config
from bridge.archive import (
    ArchiveReader,
)
from bridge.archive_sync import ArchiveSynchronizer
from bridge.discovery import build_discovery_payload
from bridge.polling import (
    LivePoller,
    PollingSettings,
    get_next_poll_interval,
)
from bridge.publisher import MqttPublisher
from bridge.scheduler import (
    InterruptibleSleeper,
    IntervalSchedule,
)
from bridge.topics import MqttTopics
from decoder import decode_live_data, read_live_data
from history.manager import create_default_history_manager
from version import APP_VERSION


APP_NAME = "WiFire-Kamin MQTT Bridge"

TOPICS = MqttTopics(
    device_id=config.DEVICE_ID,
    discovery_prefix=config.MQTT_DISCOVERY_PREFIX,
)

POLLING_SETTINGS = PollingSettings.from_config(config)
LIVE_POLLER = LivePoller(read_live_data, decode_live_data)
OFFLINE_AFTER_FAILURES = getattr(
    config,
    "OFFLINE_AFTER_FAILURES",
    3,
)

ARCHIVE_UPDATE_INTERVAL = getattr(
    config,
    "ARCHIVE_UPDATE_INTERVAL",
    21600,
)
ARCHIVE_REQUEST_DELAY = getattr(
    config,
    "ARCHIVE_REQUEST_DELAY",
    2,
)
ARCHIVE_REQUEST_TIMEOUT = getattr(
    config,
    "ARCHIVE_REQUEST_TIMEOUT",
    15,
)
ARCHIVE_RETRY_COUNT = getattr(
    config,
    "ARCHIVE_RETRY_COUNT",
    3,
)
ARCHIVE_RETRY_DELAY = getattr(
    config,
    "ARCHIVE_RETRY_DELAY",
    5,
)

ARCHIVE_URL = "http://192.168.0.1/direct/35"
ARCHIVE_COMMANDS = {
    "archive_1": "aacc3355023501ffff",
    "archive_2": "aacc3355023502ffff",
    "archive_3": "aacc3355023503ffff",
}

running = True
latest_state: dict[str, Any] | None = None
publisher: MqttPublisher | None = None


def stop_program(*_: Any) -> None:
    """Beendet die Hauptschleife kontrolliert."""
    global running
    running = False


def require_publisher() -> MqttPublisher:
    """Liefert den initialisierten MQTT-Publisher."""
    if publisher is None:
        raise RuntimeError(
            "MQTT-Publisher wurde noch nicht initialisiert."
        )
    return publisher


def publish_discovery(client: mqtt.Client) -> None:
    """Veröffentlicht die Home-Assistant-Device-Discovery."""
    payload = build_discovery_payload(
        config,
        TOPICS,
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )

    client.publish(
        TOPICS.device_discovery,
        payload=json.dumps(payload, ensure_ascii=False),
        qos=1,
        retain=True,
    )

    print(
        f'Home-Assistant-Geräte-Discovery für '
        f'"{config.DEVICE_NAME}" veröffentlicht.'
    )


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    """Paho-Callback nach erfolgreicher MQTT-Verbindung."""
    if reason_code.is_failure:
        print(
            f"MQTT-Verbindung fehlgeschlagen: {reason_code}"
        )
        return

    print("Mit MQTT verbunden.")
    client.subscribe(TOPICS.home_assistant_status, qos=1)

    publish_discovery(client)

    mqtt_publisher = require_publisher()
    mqtt_publisher.publish_availability(True)

    if latest_state is not None:
        mqtt_publisher.publish_state(latest_state)


def on_message(
    client: mqtt.Client,
    userdata: Any,
    message: mqtt.MQTTMessage,
) -> None:
    """Veröffentlicht Discovery erneut, wenn Home Assistant startet."""
    if message.topic != TOPICS.home_assistant_status:
        return

    payload = (
        message.payload.decode(
            "utf-8",
            errors="replace",
        )
        .strip()
        .lower()
    )

    if payload == "online":
        print(
            "Home Assistant ist online – "
            "Discovery wird erneut gesendet."
        )

        publish_discovery(client)

        mqtt_publisher = require_publisher()
        mqtt_publisher.publish_availability(True)

        if latest_state is not None:
            mqtt_publisher.publish_state(latest_state)


def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    disconnect_flags: mqtt.DisconnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    """Paho-Callback nach einer MQTT-Unterbrechung."""
    if running and reason_code.is_failure:
        print(
            f"MQTT-Verbindung unterbrochen: {reason_code}"
        )


def main() -> None:
    """Startet die MQTT-Bridge und die adaptive Polling-Schleife."""
    global latest_state
    global publisher

    signal.signal(signal.SIGINT, stop_program)
    signal.signal(signal.SIGTERM, stop_program)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{config.DEVICE_ID}_bridge",
        reconnect_on_failure=True,
    )

    publisher = MqttPublisher(client, TOPICS)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    if config.MQTT_USERNAME:
        client.username_pw_set(
            config.MQTT_USERNAME,
            config.MQTT_PASSWORD,
        )

    client.will_set(
        TOPICS.availability,
        payload="offline",
        qos=1,
        retain=True,
    )

    client.reconnect_delay_set(
        min_delay=2,
        max_delay=60,
    )

    print(
        f"Verbinde mit MQTT-Broker "
        f"{config.MQTT_HOST}:{config.MQTT_PORT} ..."
    )

    try:
        client.connect_async(
            config.MQTT_HOST,
            config.MQTT_PORT,
            keepalive=60,
        )
    except (OSError, ValueError) as error:
        print(f"MQTT-Konfiguration ungültig: {error}")
        raise

    client.loop_start()

    consecutive_failures = 0
    availability_online = True
    archive_schedule = IntervalSchedule(
        ARCHIVE_UPDATE_INTERVAL
    )
    sleeper = InterruptibleSleeper(lambda: running)

    project_dir = Path(__file__).resolve().parent
    history_manager = create_default_history_manager(
        project_dir
    )
    archive_reader = ArchiveReader(
        archive_url=ARCHIVE_URL,
        request_timeout=ARCHIVE_REQUEST_TIMEOUT,
        retry_count=ARCHIVE_RETRY_COUNT,
        retry_delay=ARCHIVE_RETRY_DELAY,
        sleeper=sleeper,
    )
    archive_synchronizer = ArchiveSynchronizer(
        commands=tuple(ARCHIVE_COMMANDS.items()),
        reader=archive_reader,
        publisher=publisher,
        history_manager=history_manager,
        request_delay=ARCHIVE_REQUEST_DELAY,
        sleeper=sleeper,
        is_running=lambda: running,
    )

    try:
        while running:
            read_failed = False

            try:
                data = LIVE_POLLER.poll()

                latest_state = data
                consecutive_failures = 0

                if not availability_online:
                    publisher.publish_availability(True)
                    availability_online = True

                publisher.publish_state(data)

                print(
                    f"{data['temperature_c']} °C | "
                    f"{data['flap_percent']} % | "
                    f"{data['burn_time']} | "
                    f"Tür {data['door_state']}"
                )

            except (OSError, ValueError) as error:
                read_failed = True
                consecutive_failures += 1

                print(
                    f"Lesefehler {consecutive_failures}/"
                    f"{OFFLINE_AFTER_FAILURES}: {error}"
                )

                if (
                    consecutive_failures
                    >= OFFLINE_AFTER_FAILURES
                    and availability_online
                ):
                    publisher.publish_availability(False)
                    availability_online = False

                    print(
                        "WiFire-Kamin wird als offline gemeldet."
                    )

            now = time.monotonic()

            if archive_schedule.is_due(now):
                archive_synchronizer.synchronize()
                archive_schedule.mark_updated(
                    time.monotonic()
                )

            next_interval, interval_reason = (
                get_next_poll_interval(
                    latest_state,
                    read_failed,
                    POLLING_SETTINGS,
                )
            )

            print(
                f"Nächste Abfrage in {next_interval} Sekunden "
                f"({interval_reason})."
            )

            sleeper(next_interval)

    finally:
        publisher.publish_availability(False)
        time.sleep(0.2)

        client.loop_stop()
        client.disconnect()

        print("WiFire-Kamin MQTT Bridge beendet.")


if __name__ == "__main__":
    main()
