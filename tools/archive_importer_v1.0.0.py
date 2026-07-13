#!/usr/bin/env python3
"""
WiFire-Kamin Archiv-Einmalimport
Version: 1.0.0

Liest abgeschlossene Archive aus dem WiFire-Kamin und veröffentlicht sie
einmalig als retained MQTT-Sensoren für Home Assistant.

Voraussetzungen:
- config.py
- wifire_protocol.py
- paho-mqtt
- laufenden wifire-kamin.service während des Imports stoppen
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from typing import Any
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

import config
from wifire_protocol import decode_archive_record


__version__ = "1.0.0"

APP_NAME = "WiFire-Kamin Archiv-Importer"
ARCHIVE_URL = "http://192.168.0.1/direct/35"

DEFAULT_FIRST_ARCHIVE = 1
DEFAULT_LAST_ARCHIVE = 23
DEFAULT_DELAY = 3.0
DEFAULT_RETRIES = 3
REQUEST_TIMEOUT = 15

BASE_TOPIC = f"wifire_kamin/{config.DEVICE_ID}/history"
DISCOVERY_TOPIC = (
    f"{config.MQTT_DISCOVERY_PREFIX}/device/"
    f"{config.DEVICE_ID}_archive/config"
)

running = True


def stop_program(*_: Any) -> None:
    global running
    running = False


def build_command(number: int) -> str:
    if not 1 <= number <= 255:
        raise ValueError("Archivnummer muss zwischen 1 und 255 liegen.")
    return f"aacc33550235{number:02x}ffff"


def state_topic(number: int) -> str:
    return f"{BASE_TOPIC}/{number:03d}/state"


def attributes_topic(number: int) -> str:
    return f"{BASE_TOPIC}/{number:03d}/attributes"


def read_archive(
    number: int,
    retries: int,
    retry_delay: float,
) -> str:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            body = json.dumps(
                {"raw": build_command(number)}
            ).encode("utf-8")

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

            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            raw = result.get("raw")

            if not isinstance(raw, str):
                raise ValueError(
                    "Archivantwort enthält kein gültiges raw-Feld."
                )

            bytes.fromhex(raw)
            return raw

        except Exception as error:
            last_error = error
            print(
                f"  Versuch {attempt}/{retries} fehlgeschlagen: "
                f"{error}"
            )

            if attempt < retries:
                interruptible_sleep(retry_delay)

    raise RuntimeError(
        f"Archiv {number} nach {retries} Versuchen "
        f"nicht lesbar: {last_error}"
    )


def interruptible_sleep(seconds: float) -> None:
    steps = max(1, int(seconds * 10))

    for _ in range(steps):
        if not running:
            break
        time.sleep(0.1)


def archive_attributes(record: Any) -> dict:
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
        "max_temperature_minute": record.max_temperature_minute,
        "stage_90_minute": record.stage_90_minute,
        "stage_75_minute": record.stage_75_minute,
        "stage_50_minute": record.stage_50_minute,
        "stage_25_minute": record.stage_25_minute,
        "stage_0_minute": record.stage_0_minute,
        "temperatures_c": record.temperatures,
        "importer_version": __version__,
    }


def discovery_component(number: int) -> dict:
    return {
        "platform": "sensor",
        "name": f"Archivierter Abbrand {number:03d}",
        "unique_id": f"{config.DEVICE_ID}_history_{number:03d}",
        "state_topic": state_topic(number),
        "json_attributes_topic": attributes_topic(number),
        "device_class": "timestamp",
        "icon": "mdi:chart-line",
        "entity_category": "diagnostic",
    }


def discovery_payload(numbers: list[int]) -> dict:
    components = {
        f"{config.DEVICE_ID}_history_{number:03d}":
            discovery_component(number)
        for number in numbers
    }

    return {
        "device": {
            "identifiers": [config.DEVICE_ID],
            "name": config.DEVICE_NAME,
            "manufacturer": config.MANUFACTURER,
            "model": config.MODEL,
            "sw_version": __version__,
        },
        "origin": {
            "name": APP_NAME,
            "sw_version": __version__,
        },
        "components": components,
        "qos": 1,
    }


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{config.DEVICE_ID}_archive_importer",
    )

    if config.MQTT_USERNAME:
        client.username_pw_set(
            config.MQTT_USERNAME,
            config.MQTT_PASSWORD,
        )

    print(
        f"Verbinde mit MQTT-Broker "
        f"{config.MQTT_HOST}:{config.MQTT_PORT} ..."
    )

    client.connect(
        config.MQTT_HOST,
        config.MQTT_PORT,
        keepalive=60,
    )
    client.loop_start()

    return client


def wait_for_publish(info: mqtt.MQTTMessageInfo) -> None:
    info.wait_for_publish(timeout=10)

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            f"MQTT-Veröffentlichung fehlgeschlagen: {info.rc}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Importiert abgeschlossene WiFire-Kamin-Archive "
            "einmalig nach Home Assistant."
        )
    )

    parser.add_argument(
        "--first",
        type=int,
        default=DEFAULT_FIRST_ARCHIVE,
        help=(
            "Erste Archivnummer "
            f"(Standard: {DEFAULT_FIRST_ARCHIVE})"
        ),
    )

    parser.add_argument(
        "--last",
        type=int,
        default=DEFAULT_LAST_ARCHIVE,
        help=(
            "Letzte Archivnummer "
            f"(Standard: {DEFAULT_LAST_ARCHIVE})"
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=(
            "Pause zwischen Archivabfragen in Sekunden "
            f"(Standard: {DEFAULT_DELAY})"
        ),
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=(
            "Versuche pro Archiv "
            f"(Standard: {DEFAULT_RETRIES})"
        ),
    )

    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Importiert zusätzlich unvollständige Archive.",
    )

    return parser.parse_args()


def main() -> None:
    signal.signal(signal.SIGINT, stop_program)
    signal.signal(signal.SIGTERM, stop_program)

    args = parse_args()

    if not 1 <= args.first <= args.last <= 255:
        print(
            "Ungültiger Bereich. Erwartet: "
            "1 <= --first <= --last <= 255"
        )
        sys.exit(1)

    if args.retries < 1:
        print("--retries muss mindestens 1 sein.")
        sys.exit(1)

    client = connect_mqtt()
    imported: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []

    try:
        print(
            f"Importiere Archiv {args.first} bis {args.last}."
        )

        for number in range(args.first, args.last + 1):
            if not running:
                print("Import wurde abgebrochen.")
                break

            print(f"Archiv {number:03d}: ", end="", flush=True)

            try:
                raw = read_archive(
                    number,
                    retries=args.retries,
                    retry_delay=max(1.0, args.delay),
                )
                record = decode_archive_record(raw)

                if record.timestamp is None:
                    print("übersprungen – kein gültiger Zeitstempel")
                    skipped.append(number)
                    continue

                if not record.temperatures:
                    print("übersprungen – keine Temperaturwerte")
                    skipped.append(number)
                    continue

                if (
                    record.active_or_incomplete
                    and not args.include_incomplete
                ):
                    print("übersprungen – unvollständig")
                    skipped.append(number)
                    continue

                timestamp = record.timestamp.isoformat(
                    timespec="seconds"
                )

                state_info = client.publish(
                    state_topic(number),
                    payload=timestamp,
                    qos=1,
                    retain=True,
                )

                attributes_info = client.publish(
                    attributes_topic(number),
                    payload=json.dumps(
                        archive_attributes(record),
                        ensure_ascii=False,
                    ),
                    qos=1,
                    retain=True,
                )

                wait_for_publish(state_info)
                wait_for_publish(attributes_info)

                imported.append(number)

                print(
                    f"importiert | {timestamp} | "
                    f"Maximum {record.max_temperature_c} °C | "
                    f"{record.measurement_count} Messpunkte"
                )

            except Exception as error:
                failed.append(number)
                print(f"FEHLER | {error}")

            if number < args.last:
                interruptible_sleep(args.delay)

        if imported:
            discovery_info = client.publish(
                DISCOVERY_TOPIC,
                payload=json.dumps(
                    discovery_payload(imported),
                    ensure_ascii=False,
                ),
                qos=1,
                retain=True,
            )
            wait_for_publish(discovery_info)

            print()
            print(
                "Home-Assistant-Discovery für "
                f"{len(imported)} Archivsensoren veröffentlicht."
            )

        print()
        print("Import-Zusammenfassung")
        print("----------------------")
        print(f"Importiert: {len(imported)}")
        print(f"Übersprungen: {len(skipped)}")
        print(f"Fehlgeschlagen: {len(failed)}")
        print(f"Importierte Archive: {imported}")

        if skipped:
            print(f"Übersprungene Archive: {skipped}")

        if failed:
            print(f"Fehlgeschlagene Archive: {failed}")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
