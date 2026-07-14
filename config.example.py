# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Öffentliche Beispielkonfiguration der WiFire-Kamin-Bridge."""

# WiFire-Steuerung
WIFIRE_URL = "http://192.168.0.1/direct/00"
REQUEST_TIMEOUT = 5

# MQTT-Broker
MQTT_HOST = "192.168.XXX.XXX"
MQTT_PORT = 1883
MQTT_USERNAME = "MQTT_NAME"
MQTT_PASSWORD = "MQTT_PASS"
MQTT_DISCOVERY_PREFIX = "homeassistant"

# Home-Assistant-Gerät
DEVICE_NAME = "WiFire-Kamin"
DEVICE_ID = "wifire_kamin"
MANUFACTURER = "FireControls"
MODEL = "WiFire"
ENABLE_FAN_ENTITY = False

# Adaptive Live-Abfrage in Sekunden
NORMAL_UPDATE_INTERVAL = 60
ACTIVE_FIRE_UPDATE_INTERVAL = 10
ERROR_RETRY_INTERVAL = 300
ACTIVE_FIRE_TEMPERATURE_C = 40
OFFLINE_AFTER_FAILURES = 3

# Archivabfrage in Sekunden
ARCHIVE_UPDATE_INTERVAL = 21600
ARCHIVE_FIRST_SLOT = 1
ARCHIVE_LAST_SLOT = 23
ARCHIVE_REQUEST_DELAY = 10
ARCHIVE_REQUEST_TIMEOUT = 15
ARCHIVE_RETRY_COUNT = 3
ARCHIVE_RETRY_DELAY = 10

# Statistikfilter; None berücksichtigt alle gespeicherten Datensätze.
# Beispiel zum Ausschließen falsch datierter Altbestände: "2026-01-01"
STATISTICS_SINCE = None

# Kurvenfilter; ohne eigenen Wert wird STATISTICS_SINCE verwendet.
# Warnungen bleiben standardmäßig sichtbar, aber ungültige Datensätze nie.
DASHBOARD_CURVES_SINCE = STATISTICS_SINCE
DASHBOARD_INCLUDE_WARNINGS = True
