#!/usr/bin/env python3

import json
import signal
import time
from typing import Any
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

import config
from decoder import decode_live_data, read_live_data
from version import APP_VERSION
from wifire_protocol import decode_archive_record


APP_NAME = "WiFire-Kamin MQTT Bridge"

BASE_TOPIC = f"wifire_kamin/{config.DEVICE_ID}"
STATE_TOPIC = f"{BASE_TOPIC}/state"
AVAILABILITY_TOPIC = f"{BASE_TOPIC}/availability"

HA_STATUS_TOPIC = f"{config.MQTT_DISCOVERY_PREFIX}/status"
DEVICE_DISCOVERY_TOPIC = (
    f"{config.MQTT_DISCOVERY_PREFIX}/device/{config.DEVICE_ID}/config"
)

NORMAL_UPDATE_INTERVAL = getattr(config, "NORMAL_UPDATE_INTERVAL", 60)
ACTIVE_FIRE_UPDATE_INTERVAL = getattr(
    config, "ACTIVE_FIRE_UPDATE_INTERVAL", 10
)
ERROR_RETRY_INTERVAL = getattr(config, "ERROR_RETRY_INTERVAL", 300)
ACTIVE_FIRE_TEMPERATURE_C = getattr(
    config, "ACTIVE_FIRE_TEMPERATURE_C", 40
)
OFFLINE_AFTER_FAILURES = getattr(config, "OFFLINE_AFTER_FAILURES", 3)

ARCHIVE_UPDATE_INTERVAL = getattr(config, "ARCHIVE_UPDATE_INTERVAL", 21600)
ARCHIVE_REQUEST_DELAY = getattr(config, "ARCHIVE_REQUEST_DELAY", 2)
ARCHIVE_REQUEST_TIMEOUT = getattr(config, "ARCHIVE_REQUEST_TIMEOUT", 15)
ARCHIVE_RETRY_COUNT = getattr(config, "ARCHIVE_RETRY_COUNT", 3)
ARCHIVE_RETRY_DELAY = getattr(config, "ARCHIVE_RETRY_DELAY", 5)

ARCHIVE_URL = "http://192.168.0.1/direct/35"
ARCHIVE_COMMANDS = {
    "archive_1": "aacc3355023501ffff",
    "archive_2": "aacc3355023502ffff",
    "archive_3": "aacc3355023503ffff",
}

running = True
latest_state: dict | None = None


def stop_program(*_: Any) -> None:
    global running
    running = False


def archive_state_topic(number: int) -> str:
    return f"{BASE_TOPIC}/archive/{number}/state"


def archive_attributes_topic(number: int) -> str:
    return f"{BASE_TOPIC}/archive/{number}/attributes"


def discovery_payload() -> dict:
    components: dict[str, dict] = {
        f"{config.DEVICE_ID}_temperature": {
            "platform": "sensor",
            "name": "Temperatur",
            "unique_id": f"{config.DEVICE_ID}_temperature",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "suggested_display_precision": 0,
            "value_template": "{{ value_json.temperature_c }}",
            "icon": "mdi:fire",
        },
        f"{config.DEVICE_ID}_flap": {
            "platform": "sensor",
            "name": "Luftklappe",
            "unique_id": f"{config.DEVICE_ID}_flap",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "suggested_display_precision": 0,
            "value_template": "{{ value_json.flap_percent }}",
            "icon": "mdi:valve",
        },
        f"{config.DEVICE_ID}_burn_time": {
            "platform": "sensor",
            "name": "Abbrenndauer",
            "unique_id": f"{config.DEVICE_ID}_burn_time",
            "value_template": "{{ value_json.burn_time }}",
            "icon": "mdi:timer-outline",
        },
        f"{config.DEVICE_ID}_burn_minutes": {
            "platform": "sensor",
            "name": "Abbrenndauer Minuten",
            "unique_id": f"{config.DEVICE_ID}_burn_minutes",
            "device_class": "duration",
            "unit_of_measurement": "min",
            "state_class": "measurement",
            "value_template": "{{ value_json.burn_total_minutes }}",
            "entity_category": "diagnostic",
            "icon": "mdi:timer-sand",
        },
        f"{config.DEVICE_ID}_door": {
            "platform": "binary_sensor",
            "name": "Tür",
            "unique_id": f"{config.DEVICE_ID}_door",
            "device_class": "door",
            "value_template": "{{ 'ON' if value_json.door_open else 'OFF' }}",
            "payload_on": "ON",
            "payload_off": "OFF",
        },
        f"{config.DEVICE_ID}_flap_moving": {
            "platform": "binary_sensor",
            "name": "Luftklappe bewegt sich",
            "unique_id": f"{config.DEVICE_ID}_flap_moving",
            "value_template": "{{ 'ON' if value_json.flap_moving else 'OFF' }}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "entity_category": "diagnostic",
            "icon": "mdi:valve",
        },
    }

    if config.ENABLE_FAN_ENTITY:
        components[f"{config.DEVICE_ID}_fan_raw"] = {
            "platform": "sensor",
            "name": "Lüfter Rohwert",
            "unique_id": f"{config.DEVICE_ID}_fan_raw",
            "value_template": "{{ value_json.fan_raw }}",
            "entity_category": "diagnostic",
            "icon": "mdi:fan",
        }

    for number in (1, 2, 3):
        components[f"{config.DEVICE_ID}_archive_{number}"] = {
            "platform": "sensor",
            "name": f"Archivierter Abbrand {number}",
            "unique_id": f"{config.DEVICE_ID}_archive_{number}",
            "state_topic": archive_state_topic(number),
            "json_attributes_topic": archive_attributes_topic(number),
            "device_class": "timestamp",
            "icon": "mdi:chart-line",
            "entity_category": "diagnostic",
        }

    return {
        "device": {
            "identifiers": [config.DEVICE_ID],
            "name": config.DEVICE_NAME,
            "manufacturer": config.MANUFACTURER,
            "model": config.MODEL,
            "sw_version": APP_VERSION,
        },
        "origin": {
            "name": APP_NAME,
            "sw_version": APP_VERSION,
        },
        "components": components,
        "state_topic": STATE_TOPIC,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "qos": 1,
    }


def publish_discovery(client: mqtt.Client) -> None:
    client.publish(
        DEVICE_DISCOVERY_TOPIC,
        payload=json.dumps(discovery_payload(), ensure_ascii=False),
        qos=1,
        retain=True,
    )
    print(
        f'Home-Assistant-Geräte-Discovery für '
        f'"{config.DEVICE_NAME}" veröffentlicht.'
    )


def publish_availability(client: mqtt.Client, online: bool) -> None:
    client.publish(
        AVAILABILITY_TOPIC,
        payload="online" if online else "offline",
        qos=1,
        retain=True,
    )


def publish_state(client: mqtt.Client, data: dict) -> None:
    payload = {
        "temperature_c": data["temperature_c"],
        "flap_percent": data["flap_percent"],
        "flap_moving": data["flap_moving"],
        "burn_time": data["burn_time"],
        "burn_total_minutes": data["burn_total_minutes"],
        "door_open": data["door_open"],
        "door_state": data["door_state"],
        "fan_raw": data["fan_raw"],
    }
    client.publish(
        STATE_TOPIC,
        payload=json.dumps(payload, ensure_ascii=False),
        qos=1,
        retain=False,
    )


def interruptible_sleep(seconds: int) -> None:
    for _ in range(max(1, seconds * 10)):
        if not running:
            break
        time.sleep(0.1)


def read_archive_block(command: str) -> str:
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
                result = json.loads(response.read().decode("utf-8"))

            raw = result.get("raw")
            if not isinstance(raw, str):
                raise ValueError(
                    "Archivantwort enthält kein gültiges Feld 'raw'."
                )

            return raw

        except (OSError, ValueError) as error:
            # OSError deckt u. a. URLError/HTTPError/Timeouts ab,
            # ValueError deckt ungültiges JSON sowie unser eigenes
            # "raw fehlt"/"kein gültiges Hex" ab. Andere Exceptions
            # (z. B. echte Programmfehler) sollen hier nicht als
            # simple "Lesefehler" verschluckt werden.
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
    }


def update_archives(client: mqtt.Client) -> None:
    print("Archivaktualisierung wird gestartet.")

    for index, (name, command) in enumerate(ARCHIVE_COMMANDS.items(), start=1):
        if not running:
            return

        try:
            raw = read_archive_block(command)
            record = decode_archive_record(raw)

            if record.timestamp is None:
                print(f"{name}: kein gültiger Zeitstempel – übersprungen.")
                continue

            state = record.timestamp.isoformat(timespec="seconds")

            client.publish(
                archive_state_topic(index),
                payload=state,
                qos=1,
                retain=True,
            )
            client.publish(
                archive_attributes_topic(index),
                payload=json.dumps(
                    archive_attributes(record),
                    ensure_ascii=False,
                ),
                qos=1,
                retain=True,
            )

            print(
                f"{name}: {state}, Maximum "
                f"{record.max_temperature_c} °C, "
                f"{record.measurement_count} Messpunkte."
            )

        except (RuntimeError, ValueError) as error:
            # RuntimeError kommt von read_archive_block, wenn alle
            # Versuche fehlgeschlagen sind. ValueError kommt von
            # decode_archive_record bei einem unerwarteten/kaputten
            # Datensatz. Beides sind erwartbare Betriebsfälle für ein
            # einzelnes Archiv – die anderen zwei laufen unabhängig
            # weiter. Ein echter Programmfehler soll dagegen sichtbar
            # werden statt hier als "Archivfehler" zu verschwinden.
            print(f"{name}: Archivfehler: {error}")

        if index < len(ARCHIVE_COMMANDS):
            interruptible_sleep(ARCHIVE_REQUEST_DELAY)

    print("Archivaktualisierung beendet.")


def get_next_poll_interval(
    current_state: dict | None,
    read_failed: bool,
) -> tuple[int, str]:
    if read_failed or current_state is None:
        return ERROR_RETRY_INTERVAL, "Lesefehler"

    if current_state["temperature_c"] >= ACTIVE_FIRE_TEMPERATURE_C:
        return ACTIVE_FIRE_UPDATE_INTERVAL, "aktiver Abbrand"

    return NORMAL_UPDATE_INTERVAL, "Normalbetrieb"


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    if reason_code.is_failure:
        print(f"MQTT-Verbindung fehlgeschlagen: {reason_code}")
        return

    print("Mit MQTT verbunden.")
    client.subscribe(HA_STATUS_TOPIC, qos=1)
    publish_discovery(client)
    publish_availability(client, True)

    if latest_state is not None:
        publish_state(client, latest_state)


def on_message(
    client: mqtt.Client,
    userdata: Any,
    message: mqtt.MQTTMessage,
) -> None:
    if message.topic != HA_STATUS_TOPIC:
        return

    payload = message.payload.decode("utf-8", errors="replace").strip().lower()

    if payload == "online":
        print("Home Assistant ist online – Discovery wird erneut gesendet.")
        publish_discovery(client)
        publish_availability(client, True)

        if latest_state is not None:
            publish_state(client, latest_state)


def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    disconnect_flags: mqtt.DisconnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    if running and reason_code.is_failure:
        print(f"MQTT-Verbindung unterbrochen: {reason_code}")


def main() -> None:
    global latest_state

    signal.signal(signal.SIGINT, stop_program)
    signal.signal(signal.SIGTERM, stop_program)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{config.DEVICE_ID}_bridge",
        reconnect_on_failure=True,
    )

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    if config.MQTT_USERNAME:
        client.username_pw_set(
            config.MQTT_USERNAME,
            config.MQTT_PASSWORD,
        )

    client.will_set(
        AVAILABILITY_TOPIC,
        payload="offline",
        qos=1,
        retain=True,
    )

    client.reconnect_delay_set(min_delay=2, max_delay=60)

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

    consecutive_failures = 0
    availability_online = True
    last_archive_update = 0.0

    try:
        while running:
            read_failed = False

            try:
                raw = read_live_data()
                data = decode_live_data(raw)
                latest_state = data
                consecutive_failures = 0

                if not availability_online:
                    publish_availability(client, True)
                    availability_online = True

                publish_state(client, data)

                print(
                    f"{data['temperature_c']} °C | "
                    f"{data['flap_percent']} % | "
                    f"{data['burn_time']} | "
                    f"Tür {data['door_state']}"
                )

            except (OSError, ValueError) as error:
                # OSError: Netzwerkfehler beim Abruf (Timeout, Verbindung
                # abgelehnt, DNS, ...). ValueError: kaputtes JSON oder ein
                # von decode_live_data erkannter ungültiger Datensatz.
                # Ein unerwarteter Fehlertyp weist auf einen echten Bug
                # hin und soll den Prozess sichtbar beenden (systemd
                # startet ihn neu und der Fehler landet im Journal),
                # statt endlos als "Lesefehler" maskiert zu werden.
                read_failed = True
                consecutive_failures += 1

                print(
                    f"Lesefehler {consecutive_failures}/"
                    f"{OFFLINE_AFTER_FAILURES}: {error}"
                )

                if (
                    consecutive_failures >= OFFLINE_AFTER_FAILURES
                    and availability_online
                ):
                    publish_availability(client, False)
                    availability_online = False
                    print("WiFire-Kamin wird als offline gemeldet.")

            now = time.monotonic()
            if now - last_archive_update >= ARCHIVE_UPDATE_INTERVAL:
                update_archives(client)
                last_archive_update = time.monotonic()

            next_interval, interval_reason = get_next_poll_interval(
                latest_state,
                read_failed,
            )
            print(
                f"Nächste Abfrage in {next_interval} Sekunden "
                f"({interval_reason})."
            )
            interruptible_sleep(next_interval)

    finally:
        publish_availability(client, False)
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        print("WiFire-Kamin MQTT Bridge beendet.")


if __name__ == "__main__":
    main()
