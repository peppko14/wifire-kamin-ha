# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Home-Assistant-MQTT-Discovery für den WiFire-Kamin."""

from __future__ import annotations

from typing import Protocol

from bridge.topics import MqttTopics


__version__ = "1.3.0"


class DiscoveryConfig(Protocol):
    """Benötigte öffentliche Konfigurationswerte."""

    DEVICE_ID: str
    DEVICE_NAME: str
    MANUFACTURER: str
    MODEL: str
    ENABLE_FAN_ENTITY: bool


def build_discovery_payload(
    config: DiscoveryConfig,
    topics: MqttTopics,
    *,
    app_name: str,
    app_version: str,
    archive_numbers: tuple[int, ...] = (1, 2, 3),
) -> dict[str, object]:
    """Erzeugt die vollständige Device-Discovery-Nachricht."""
    components: dict[str, dict[str, object]] = {
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
            "value_template": (
                "{{ 'ON' if value_json.door_open else 'OFF' }}"
            ),
            "payload_on": "ON",
            "payload_off": "OFF",
        },
        f"{config.DEVICE_ID}_flap_moving": {
            "platform": "binary_sensor",
            "name": "Luftklappe bewegt sich",
            "unique_id": f"{config.DEVICE_ID}_flap_moving",
            "value_template": (
                "{{ 'ON' if value_json.flap_moving else 'OFF' }}"
            ),
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

    components[f"{config.DEVICE_ID}_dashboard_curves"] = {
        "platform": "sensor",
        "name": "Brennkurven-Vergleich",
        "unique_id": f"{config.DEVICE_ID}_dashboard_curves",
        "state_topic": topics.dashboard_curves,
        "value_template": "{{ value_json.generated_at }}",
        "json_attributes_topic": topics.dashboard_curves,
        "device_class": "timestamp",
        "entity_category": "diagnostic",
        "icon": "mdi:chart-multiple",
    }

    for number in archive_numbers:
        components[f"{config.DEVICE_ID}_archive_{number}"] = {
            "platform": "sensor",
            "name": f"Archivierter Abbrand {number}",
            "unique_id": (
                f"{config.DEVICE_ID}_archive_{number}"
            ),
            "state_topic": topics.archive_state(number),
            "json_attributes_topic": (
                topics.archive_attributes(number)
            ),
            "device_class": "timestamp",
            "icon": "mdi:chart-line",
            "entity_category": "diagnostic",
        }

    statistics_components = {
        "burn_count": {
            "name": "Historische Abbrände",
            "icon": "mdi:counter",
            "value_template": "{{ value_json.burn_count }}",
        },
        "latest_burn": {
            "name": "Neuester historischer Abbrand",
            "device_class": "timestamp",
            "icon": "mdi:calendar-clock",
            "value_template": "{{ value_json.latest_burn_start }}",
        },
        "total_duration": {
            "name": "Gesamte historische Abbrenndauer",
            "device_class": "duration",
            "unit_of_measurement": "min",
            "icon": "mdi:timer-sand-complete",
            "value_template": "{{ value_json.total_duration_minutes }}",
        },
        "average_duration": {
            "name": "Mittlere historische Abbrenndauer",
            "device_class": "duration",
            "unit_of_measurement": "min",
            "state_class": "measurement",
            "suggested_display_precision": 1,
            "icon": "mdi:timer-outline",
            "value_template": "{{ value_json.average_duration_minutes }}",
        },
        "average_max_temperature": {
            "name": "Mittlere historische Maximaltemperatur",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "suggested_display_precision": 1,
            "icon": "mdi:thermometer-lines",
            "value_template": "{{ value_json.average_max_temperature_c }}",
        },
        "highest_temperature": {
            "name": "Höchste historische Temperatur",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "suggested_display_precision": 0,
            "icon": "mdi:thermometer-high",
            "value_template": "{{ value_json.highest_temperature_c }}",
        },
    }

    for key, component in statistics_components.items():
        components[f"{config.DEVICE_ID}_statistics_{key}"] = {
            "platform": "sensor",
            "unique_id": f"{config.DEVICE_ID}_statistics_{key}",
            "state_topic": topics.statistics,
            **component,
        }

    period_components = {
        "month_period": {
            "name": "Aktueller Statistikmonat",
            "icon": "mdi:calendar-month",
            "value_template": "{{ value_json.current_month.period }}",
            "entity_category": "diagnostic",
        },
        "month_burn_count": {
            "name": "Abbrände aktueller Monat",
            "icon": "mdi:counter",
            "value_template": "{{ value_json.current_month.burn_count }}",
        },
        "month_total_duration": {
            "name": "Abbrenndauer aktueller Monat",
            "device_class": "duration",
            "unit_of_measurement": "min",
            "icon": "mdi:timer-sand",
            "value_template": (
                "{{ value_json.current_month.total_duration_minutes }}"
            ),
        },
        "month_average_max_temperature": {
            "name": "Mittlere Maximaltemperatur aktueller Monat",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "suggested_display_precision": 1,
            "icon": "mdi:thermometer-lines",
            "value_template": (
                "{{ value_json.current_month.average_max_temperature_c }}"
            ),
        },
    }

    for key, component in period_components.items():
        components[f"{config.DEVICE_ID}_period_{key}"] = {
            "platform": "sensor",
            "unique_id": f"{config.DEVICE_ID}_period_{key}",
            "state_topic": topics.period_statistics,
            **component,
        }

    season_names = (
        "aktuelle Heizsaison",
        "vorherige Heizsaison",
        "vorvorherige Heizsaison",
    )
    for index, season_name in enumerate(season_names):
        number = index + 1
        season_components = {
            "period": {
                "name": season_name.capitalize(),
                "icon": "mdi:calendar-range",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].label }}"
                ),
                "entity_category": "diagnostic",
            },
            "burn_count": {
                "name": f"Abbrände {season_name}",
                "icon": "mdi:counter",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].burn_count }}"
                ),
            },
            "total_duration": {
                "name": f"Abbrenndauer {season_name}",
                "device_class": "duration",
                "unit_of_measurement": "min",
                "icon": "mdi:timer-sand-complete",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].total_duration_minutes }}"
                ),
            },
            "average_duration": {
                "name": f"Mittlere Abbrenndauer {season_name}",
                "device_class": "duration",
                "unit_of_measurement": "min",
                "state_class": "measurement",
                "suggested_display_precision": 1,
                "icon": "mdi:timer-outline",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].average_duration_minutes }}"
                ),
            },
            "average_max_temperature": {
                "name": f"Mittlere Maximaltemperatur {season_name}",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
                "suggested_display_precision": 1,
                "icon": "mdi:thermometer-lines",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].average_max_temperature_c }}"
                ),
            },
            "highest_temperature": {
                "name": f"Höchste Temperatur {season_name}",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
                "suggested_display_precision": 0,
                "icon": "mdi:thermometer-high",
                "value_template": (
                    "{{ value_json.heating_seasons["
                    f"{index}"
                    "].highest_temperature_c }}"
                ),
            },
        }

        for key, component in season_components.items():
            component_id = f"{config.DEVICE_ID}_period_season_{number}_{key}"
            components[component_id] = {
                "platform": "sensor",
                "unique_id": component_id,
                "state_topic": topics.period_statistics,
                **component,
            }

    return {
        "device": {
            "identifiers": [config.DEVICE_ID],
            "name": config.DEVICE_NAME,
            "manufacturer": config.MANUFACTURER,
            "model": config.MODEL,
            "sw_version": app_version,
        },
        "origin": {
            "name": app_name,
            "sw_version": app_version,
        },
        "components": components,
        "state_topic": topics.state,
        "availability_topic": topics.availability,
        "payload_available": "online",
        "payload_not_available": "offline",
        "qos": 1,
    }
