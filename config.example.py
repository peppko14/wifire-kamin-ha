# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Öffentliche Beispielkonfiguration der WiFire-Kamin-Bridge."""

# Die private Kopie enthält MQTT-Zugangsdaten und muss nur für ihren Besitzer
# lesbar sein: chmod 600 config.py

# Zentrale Protokollierung: DEBUG, INFO, WARNING, ERROR oder CRITICAL.
LOG_LEVEL = "INFO"

# WiFire-Steuerung
WIFIRE_URL = "http://192.168.0.1/direct/00"
REQUEST_TIMEOUT = 5

# MQTT-Broker
MQTT_HOST = "192.168.XXX.XXX"
MQTT_PORT = 1883
MQTT_USERNAME = "MQTT_NAME"
MQTT_PASSWORD = "MQTT_PASS"
MQTT_DISCOVERY_PREFIX = "homeassistant"

# Optionale MQTT-Transportverschlüsselung. Ohne TLS bleibt Port 1883 üblich;
# mit TLS wird häufig Port 8883 verwendet. Der Port bleibt bewusst separat
# konfigurierbar, da der Broker auch andere Ports verwenden kann.
MQTT_TLS_ENABLED = False
# None verwendet bei aktiviertem TLS die vertrauenswürdigen System-CAs.
MQTT_TLS_CA_CERT = None
# Optionales Client-Zertifikat und Schlüssel immer gemeinsam setzen.
MQTT_TLS_CLIENT_CERT = None
MQTT_TLS_CLIENT_KEY = None
# Deaktiviert die Prüfung des Broker-Namens und ist nur für kurze Tests gedacht.
MQTT_TLS_INSECURE = False

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
# Ohne neuen Live-Zustand werden nur die Live-Entitäten danach unavailable.
# None deaktiviert diese zusätzliche Home-Assistant-Ablaufüberwachung.
LIVE_EXPIRE_AFTER = NORMAL_UPDATE_INTERVAL * 3
# Gesamtzahl der Versuche pro Live-Zyklus; 1 entspricht altem Verhalten.
LIVE_RETRY_COUNT = 2
LIVE_RETRY_DELAY = 2
# Eine Live-Brennkurve endet erst nach so vielen aufeinanderfolgenden
# Messungen unter ACTIVE_FIRE_TEMPERATURE_C.
LIVE_CURVE_END_AFTER_INACTIVE_SAMPLES = 3

# Archivabfrage in Sekunden
ARCHIVE_UPDATE_INTERVAL = 21600
ARCHIVE_FIRST_SLOT = 1
# Reine Sicherheitsobergrenze, keine behauptete Gerätekapazität. Der Scan
# endet vorher am ersten bekannten Abbrand oder eindeutig leeren Platz.
ARCHIVE_LAST_SLOT = 255
ARCHIVE_REQUEST_DELAY = 10
ARCHIVE_REQUEST_TIMEOUT = 15
ARCHIVE_RETRY_COUNT = 3
ARCHIVE_RETRY_DELAY = 10
ARCHIVE_MAX_CONSECUTIVE_READ_ERRORS = 3

# Statistikfilter; None berücksichtigt alle gespeicherten Datensätze.
# Beispiel zum Ausschließen falsch datierter Altbestände: "2026-01-01"
STATISTICS_SINCE = None

# Kurvenfilter; ohne eigenen Wert wird STATISTICS_SINCE verwendet.
# Warnungen bleiben standardmäßig sichtbar, aber ungültige Datensätze nie.
DASHBOARD_CURVES_SINCE = STATISTICS_SINCE
DASHBOARD_INCLUDE_WARNINGS = True
