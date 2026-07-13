# Architektur

Dokumentversion: 1.2.0

Projektstand: WiFire-Kamin Home Assistant Bridge v0.6.1

## Ziele

Die Architektur trennt Gerätekommunikation, Datenmodelle, lokale Historie
und Home-Assistant-Anbindung. Das Projekt bleibt ausschließlich lesend.

Grundsätze:

- keine Steuer- oder Konfigurationsbefehle an den Kamin,
- keine benutzerspezifischen absoluten Pfade,
- Laufzeitdaten ausschließlich unter `data/`,
- stabile Identität historischer Abbrände,
- keine parallelen HTTP-Zugriffe auf das empfindliche WiFire-Gerät,
- kleine, testbare Module mit klarer Verantwortung.

## Umgesetzte Struktur

```text
wifire-kamin-ha/
├── bridge/
│   ├── topics.py
│   ├── discovery.py
│   ├── publisher.py
│   ├── mqtt_client.py
│   ├── polling.py
│   ├── archive.py
│   ├── archive_sync.py
│   ├── scheduler.py
│   ├── runtime.py
│   └── application.py
├── history/
│   ├── identifiers.py
│   ├── storage.py
│   ├── manager.py
│   └── sync.py
├── protocol/
│   ├── models.py
│   └── adapters.py
├── tests/
├── tools/
├── docs/
├── systemd/
├── data/
├── mqtt_discovery.py
├── decoder.py
├── wifire_protocol.py
├── config.example.py
├── VERSION
└── CHANGELOG.md
```

## Bridge

### `bridge/topics.py`

Erzeugt alle MQTT-Topics zentral aus Geräte-ID und Discovery-Präfix.

### `bridge/discovery.py`

Erzeugt die Home-Assistant-Device-Discovery für Live-Sensoren,
Diagnosewerte und die drei veröffentlichten Archivplätze.

### `bridge/publisher.py`

Kapselt MQTT-Veröffentlichungen für Verfügbarkeit, Live-Zustand und
Archivattribute.

### `bridge/mqtt_client.py`

Kapselt den vollständigen MQTT-Lebenszyklus: Client-Erzeugung, Anmeldung,
Last Will, Reconnect-Einstellungen, Callbacks, Discovery bei einer
Neuverbindung sowie kontrollierten Start und Stopp.

### `bridge/polling.py`

Liest und dekodiert einen Live-Datensatz und bestimmt das adaptive
Abfrageintervall:

- 10 Sekunden bei aktivem Abbrand,
- 60 Sekunden im Normalbetrieb,
- 300 Sekunden nach Lesefehlern.

### `bridge/archive.py`

Liest einen Archivblock über `/direct/35`, prüft die JSON-/Hex-Antwort
und führt begrenzte Wiederholungsversuche aus.

### `bridge/archive_sync.py`

Koordiniert die bekannten Archivbefehle. Ein gültiger Datensatz wird
gleichzeitig per MQTT veröffentlicht und an den History Manager übergeben.

### `bridge/scheduler.py`

Enthält wiederkehrende Zeitpläne und eine unterbrechbare Wartefunktion,
damit SIGINT und SIGTERM zeitnah wirken.

### `bridge/runtime.py`

Steuert die zyklische Live-Abfrage, Offline-Erkennung, Archivplanung und
Wartezeit. Die Klasse ist unabhängig vom konkreten MQTT-Client testbar.

### `bridge/application.py`

Erzeugt und verbindet alle Bridge-Komponenten. Der Application Runner
registriert SIGINT und SIGTERM, startet MQTT und Laufzeitsteuerung und
garantiert den kontrollierten MQTT-Stopp auch bei einem Laufzeitfehler.

### `mqtt_discovery.py`

Ist nur noch der Programmeinstieg. Die Datei lädt Konfiguration und Version,
erzeugt über `create_application()` den Application Runner und startet ihn.

## Protokoll und Datenmodelle

### `decoder.py`

Liest `/direct/00` und dekodiert Temperatur, Luftklappe, Türstatus,
Abbrenndauer sowie Diagnosewerte.

### `wifire_protocol.py`

Dekodiert die Rohdaten der Archivantworten.

### `protocol/models.py`

Definiert unveränderliche Datenmodelle:

- `LiveStatus` für dekodierte Live-Daten,
- `BurnRecord` für vollständige oder unvollständige Abbrände.

### `protocol/adapters.py`

Überführt die bestehende Archivstruktur in das zentrale `BurnRecord`-Modell.

## Historie

### `history/identifiers.py`

Erzeugt eine reproduzierbare SHA-256-ID aus:

1. normalisierter Startzeit,
2. Anzahl der Messpunkte,
3. vollständiger Temperaturkurve.

Die Archivnummer wird nicht berücksichtigt, weil sie im Ringpuffer rotiert.

### `history/storage.py`

Speichert ausschließlich abgeschlossene Abbrände als JSON. Neue Dateien
werden zunächst als temporäre Datei geschrieben und anschließend atomisch
umbenannt. Das Schema besitzt eine eigene Version.

Speicherort:

```text
data/history/<startzeit>_<erste-12-Zeichen-der-burn-id>.json
```

### `history/manager.py`

Validiert Datensätze, erkennt vorhandene IDs und speichert nur neue,
vollständige Abbrände.

### `history/sync.py`

Stellt die vollständige Ringpuffer-Synchronisation für Importwerkzeuge
bereit. Die Archiv-URL wird aus der konfigurierten Live-URL abgeleitet.

## Datenfluss

```text
FireControls WiFire
   │ HTTP, ausschließlich lesend
   ├── /direct/00 ──> decoder.py ──> Live-Zustand
   │                                      │
   │                                      └──> MQTT ──> Home Assistant
   │
   └── /direct/35 ──> Archivdecoder ──> BurnRecord
                                            │
                                            ├──> MQTT-Archivdiagnose
                                            └──> History Manager
                                                     │
                                                     └──> data/history/
```

Alle Zugriffe erfolgen nacheinander innerhalb derselben Laufzeitsteuerung.
Das schützt den eingebetteten Webserver vor parallelen Anfragen.

## Historienformat

Jede JSON-Datei enthält unter anderem:

```json
{
  "schema_version": 1,
  "burn_id": "vollständiger SHA-256-Hash",
  "start": "2026-04-22T21:23:00",
  "source_archive_number": 1,
  "measurement_count": 121,
  "duration_minutes": 121,
  "max_temperature_c": 453,
  "max_temperature_minute": 26,
  "temperatures_c": [22, 24, 30],
  "active_or_incomplete": false,
  "imported_at": "2026-07-13T12:00:00+00:00"
}
```

Die Historien-Schema-Version ist unabhängig von der Projektversion.

## Fehlerbehandlung

- Live-Fehler führen zu einem längeren Abfrageintervall.
- Nach mehreren Live-Fehlern wird das MQTT-Gerät als offline gemeldet.
- Archivzugriffe besitzen begrenzte Wiederholungsversuche.
- Zwischen Archivanforderungen werden kontrollierte Pausen eingehalten.
- Fehlerhafte Archive verhindern nicht die Verarbeitung weiterer Plätze.
- Vorhandene Historieneinträge werden weder überschrieben noch gelöscht.

## Tests

Version 0.6.1 umfasst 93 Unit-Tests. Netzwerk, MQTT-Broker und Kamin sind
für diese Tests nicht erforderlich.

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## Bewusst verschoben

Nicht Bestandteil von v0.6.0 sind:

- Statistikberechnungen,
- Monats- und Saisonübersichten,
- ein Home-Assistant-Dashboard,
- die vollständige Ablösung der bestehenden Decoder-Einstiegspunkte.

Diese Punkte können auf der stabilen Historien- und Bridge-Architektur in
einer späteren Version aufgebaut werden.
