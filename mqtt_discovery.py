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
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

import config
from bridge.discovery import build_discovery_payload
from bridge.polling import (
    LivePoller,
    PollingSettings,
    get_next_poll_interval,
)
from bridge.publisher import MqttPublisher
from bridge.topics import MqttTopics
from decoder import decode_live_data, read_live_data
from history.manager import HistoryManager, create_default_history_manager
from protocol.adapters import archive_record_to_burn_record
from version import APP_VERSION
from wifire_protocol import decode_archive_record


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


def interruptible_sleep(seconds: int | float) -> None:
    """Schläft in kurzen Abschnitten und reagiert auf Stoppsignale."""
    steps = max(1, int(seconds * 10))

    for _ in range(steps):
        if not running:
            break
        time.sleep(0.1)


def read_archive_block(command: str) -> str:
    """Liest einen Archivblock mit begrenzten Wiederholungen."""
    last_error: Exception | None = None

    for attempt in range(1, ARCHIVE_RETRY_COUNT + 1):
        try:
            body = json.dumps({"raw": command}).encode("utf-8")

            request = Request(
                ARCHIVE_URL,
                data=body,
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                    "Connection": "close",
                },
                method="POST",
            )

            with urlopen(
                request,
                timeout=ARCHIVE_REQUEST_TIMEOUT,
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            raw = result.get("raw")
            if not isinstance(raw, str):
                raise ValueError(
                    "Archivantwort enthält kein gültiges Feld 'raw'."
                )

            bytes.fromhex(raw)
            return raw

        except (OSError, ValueError) as error:
            last_error = error

            print(
                f"Archivversuch {attempt}/{ARCHIVE_RETRY_COUNT} "
                f"fehlgeschlagen: {error}"
            )

            if attempt < ARCHIVE_RETRY_COUNT:
                interruptible_sleep(ARCHIVE_RETRY_DELAY)

    raise RuntimeError(
        f"Archivabfrage nach {ARCHIVE_RETRY_COUNT} Versuchen "
        f"fehlgeschlagen: {last_error}"
    )


def archive_attributes(record: Any) -> dict[str, object]:
    """Erzeugt die MQTT-Attribute eines Archivdatensatzes."""
    timestamp = (
        record.timestamp.isoformat(timespec="minutes")
        if record.timestamp
        else None
    )

    return {
        "archive_number": record.archive_number,
        "start": timestamp,
        "measurement_count": record.measurement_count,
        "duration_minutes": record.measurement_count,
        "start_temperature_c": record.start_temperature_c,
        "end_temperature_c": record.end_temperature_c,
        "max_temperature_c": record.max_temperature_c,
        "max_temperature_minute": (
            record.max_temperature_minute
        ),
        "stage_90_minute": record.stage_90_minute,
        "stage_75_minute": record.stage_75_minute,
        "stage_50_minute": record.stage_50_minute,
        "stage_25_minute": record.stage_25_minute,
        "stage_0_minute": record.stage_0_minute,
        "temperatures_c": record.temperatures,
    }


def update_archives(
    mqtt_publisher: MqttPublisher,
    history_manager: HistoryManager,
) -> None:
    """Aktualisiert MQTT-Archive und die lokale Historie."""
    print("Archivaktualisierung wird gestartet.")

    for index, (name, command) in enumerate(
        ARCHIVE_COMMANDS.items(),
        start=1,
    ):
        if not running:
            return

        try:
            raw = read_archive_block(command)
            record = decode_archive_record(raw)

            if record.timestamp is None:
                print(
                    f"{name}: kein gültiger Zeitstempel – "
                    f"übersprungen."
                )
                continue

            state = record.timestamp.isoformat(
                timespec="seconds"
            )

            mqtt_publisher.publish_archive(
                index,
                state=state,
                attributes=archive_attributes(record),
            )

            print(
                f"{name}: {state}, Maximum "
                f"{record.max_temperature_c} °C, "
                f"{record.measurement_count} Messpunkte."
            )

            burn_record = archive_record_to_burn_record(record)
            history_result = history_manager.synchronize(
                [burn_record]
            )

            if history_result.imported_count:
                print(
                    f"{name}: neuer Abbrand lokal unter "
                    f"data/history gespeichert."
                )
            elif history_result.existing_count:
                print(
                    f"{name}: Abbrand bereits in lokaler Historie."
                )
            elif history_result.skipped_incomplete:
                print(
                    f"{name}: unvollständiger Abbrand "
                    f"nicht gespeichert."
                )

        except (RuntimeError, ValueError) as error:
            print(f"{name}: Archivfehler: {error}")

        if index < len(ARCHIVE_COMMANDS):
            interruptible_sleep(ARCHIVE_REQUEST_DELAY)

    print("Archivaktualisierung beendet.")


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
    last_archive_update = 0.0

    project_dir = Path(__file__).resolve().parent
    history_manager = create_default_history_manager(
        project_dir
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

            if (
                now - last_archive_update
                >= ARCHIVE_UPDATE_INTERVAL
            ):
                update_archives(
                    publisher,
                    history_manager,
                )
                last_archive_update = time.monotonic()

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

            interruptible_sleep(next_interval)

    finally:
        publisher.publish_availability(False)
        time.sleep(0.2)

        client.loop_stop()
        client.disconnect()

        print("WiFire-Kamin MQTT Bridge beendet.")


if __name__ == "__main__":
    main()
