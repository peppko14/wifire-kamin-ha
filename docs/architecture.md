# Architektur

Dokumentversion: 1.0.0  
Projektziel: WiFire-Kamin Home Assistant Bridge v0.6.0

## Zweck

Dieses Dokument beschreibt die geplante technische Architektur für die nächste Entwicklungsstufe des Projekts.

Ziele:

- klare Trennung der Verantwortlichkeiten,
- dauerhaft speicherbare Abbrandhistorie,
- stabile eindeutige IDs für Abbrände,
- robuste MQTT-Anbindung,
- einfache Erweiterbarkeit,
- weiterhin ausschließlich lesender Zugriff auf die FireControls-WiFire-Steuerung.

## Grundprinzipien

- Das Projekt arbeitet nur lesend.
- Keine benutzerspezifischen absoluten Pfade.
- Laufzeitdaten werden unter `data/` gespeichert.
- Protokolldekodierung bleibt unabhängig von MQTT.
- Historienlogik bleibt unabhängig von Home Assistant.
- MQTT veröffentlicht nur bereits dekodierte und validierte Daten.
- Jede Funktion soll genau eine Verantwortung haben.

## Geplante Projektstruktur

```text
wifire-kamin-ha/
├── bridge/
│   ├── __init__.py
│   ├── mqtt_client.py
│   ├── discovery.py
│   ├── polling.py
│   └── application.py
├── protocol/
│   ├── __init__.py
│   ├── client.py
│   ├── live.py
│   ├── archive.py
│   └── models.py
├── history/
│   ├── __init__.py
│   ├── identifiers.py
│   ├── storage.py
│   ├── manager.py
│   └── statistics.py
├── tools/
├── docs/
├── systemd/
├── data/
├── config.example.py
├── version.py
├── VERSION
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Modulübersicht

### `protocol/`

Verantwortlich für die Kommunikation mit der WiFire-Steuerung und die Dekodierung der Rohdaten.

#### `protocol/client.py`

Aufgaben:

- HTTP-Kommunikation mit der Steuerung,
- Zeitüberschreitungen,
- Wiederholungsversuche,
- kontrollierte Pausen zwischen Abfragen,
- zentrale URL- und Verbindungsverwaltung.

Das Modul liefert Rohantworten, wertet sie aber nicht fachlich aus.

#### `protocol/live.py`

Aufgaben:

- Dekodierung von `/direct/00`,
- Temperatur,
- Luftklappenstellung,
- Türstatus,
- Abbrenndauer,
- optionale Diagnosewerte.

#### `protocol/archive.py`

Aufgaben:

- Dekodierung der Archivantworten von `/direct/35`,
- Zeitstempel,
- Luftklappenstufen,
- Temperaturkurve,
- Status abgeschlossen oder unvollständig.

#### `protocol/models.py`

Enthält zentrale Datenmodelle, vorzugsweise als `dataclass`.

Beispiele:

```python
@dataclass
class LiveStatus:
    temperature_c: int
    flap_percent: int
    door_open: bool
    burn_total_minutes: int
```

```python
@dataclass
class BurnRecord:
    burn_id: str
    start: datetime
    temperatures_c: list[int]
    max_temperature_c: int
    max_temperature_minute: int
    source_archive_number: int | None
```

### `history/`

Verantwortlich für lokale Sicherung, Duplikaterkennung und spätere Statistiken.

#### `history/identifiers.py`

Erzeugt die stabile eindeutige ID eines Abbrands.

Die Archivnummer darf nicht Bestandteil der dauerhaften Identität sein, da sie sich im Ringpuffer verschieben kann.

Die ID wird als SHA-256-Hash aus einer kanonischen Darstellung erzeugt.

Vorgesehene Eingaben:

- Startzeit,
- Anzahl Messpunkte,
- vollständige Temperaturkurve.

Beispiel:

```text
2026-04-22T21:23|121|22,24,30,37,...
```

Daraus:

```text
SHA-256 -> stabile burn_id
```

#### `history/storage.py`

Aufgaben:

- Speichern eines Abbrands als JSON,
- Laden bestehender Abbrände,
- Prüfen, ob eine `burn_id` bereits vorhanden ist,
- atomisches Schreiben,
- keine Duplikate.

Geplanter Speicherort:

```text
data/history/
```

Dateiname:

```text
<startzeit>_<kurze-burn-id>.json
```

Beispiel:

```text
2026-04-22_21-23_a1b2c3d4.json
```

#### `history/manager.py`

Steuert den Historienablauf.

Aufgaben:

1. Archive vom Gerät lesen.
2. Nur gültige und abgeschlossene Abbrände berücksichtigen.
3. Stabile `burn_id` berechnen.
4. Bereits gespeicherte Datensätze überspringen.
5. Neue Abbrände lokal speichern.
6. Ergebnis für MQTT und Statistik bereitstellen.

#### `history/statistics.py`

Später verantwortlich für:

- Anzahl Abbrände,
- durchschnittliche Maximaltemperatur,
- durchschnittliche Dauer,
- heißester Abbrand,
- längster Abbrand,
- Monats- und Saisonstatistiken.

### `bridge/`

Verantwortlich für MQTT, Home Assistant Discovery und den laufenden Dienst.

#### `bridge/mqtt_client.py`

Aufgaben:

- MQTT-Verbindung,
- Wiederverbindung,
- Availability,
- retained Nachrichten,
- Fehlerbehandlung.

#### `bridge/discovery.py`

Aufgaben:

- Home Assistant MQTT Discovery,
- Gerätemetadaten,
- Sensoren,
- Diagnoseentitäten,
- spätere Historien- und Statistikentitäten.

#### `bridge/polling.py`

Aufgaben:

- 60 Sekunden im Normalbetrieb,
- 10 Sekunden bei aktivem Abbrand,
- 5 Minuten nach Lesefehlern,
- seltene Archivabfragen,
- kontrollierte Koordination aller HTTP-Zugriffe.

#### `bridge/application.py`

Zentraler Programmablauf.

Aufgaben:

- Module starten,
- Signale behandeln,
- Live-Daten lesen,
- Historie synchronisieren,
- MQTT aktualisieren,
- sauber herunterfahren.

## Datenfluss

```text
FireControls WiFire
        │
        │ HTTP, nur lesend
        ▼
protocol/client.py
        │
        ├── Live-Rohdaten
        │       ▼
        │   protocol/live.py
        │       ▼
        │   LiveStatus
        │
        └── Archiv-Rohdaten
                ▼
            protocol/archive.py
                ▼
            BurnRecord
                ▼
            history/manager.py
                ▼
            history/storage.py
                │
                ├── JSON unter data/history/
                └── neue Datensätze
                        ▼
                  bridge/discovery.py
                  bridge/mqtt_client.py
                        ▼
                  Home Assistant
```

## Historienformat

Jeder Abbrand wird als eigenständige JSON-Datei gespeichert.

Beispiel:

```json
{
  "schema_version": 1,
  "burn_id": "vollständiger-sha256-hash",
  "start": "2026-04-22T21:23:00",
  "source_archive_number": 1,
  "measurement_count": 121,
  "duration_minutes": 121,
  "start_temperature_c": 22,
  "end_temperature_c": 205,
  "max_temperature_c": 453,
  "max_temperature_minute": 26,
  "stage_90_minute": 7,
  "stage_75_minute": 36,
  "stage_50_minute": 57,
  "stage_25_minute": 109,
  "stage_0_minute": 169,
  "temperatures_c": [22, 24, 30],
  "imported_at": "2026-07-13T12:00:00"
}
```

## Schema-Version

Historien-Dateien erhalten ein Feld:

```json
"schema_version": 1
```

Ändert sich das lokale Dateiformat später inkompatibel, wird die Schema-Version erhöht.

Die Projektversion und die Historien-Schema-Version sind voneinander unabhängig.

## Stabile Abbrand-ID

Die ID muss reproduzierbar sein.

Vorgesehene Berechnung:

1. Startzeit in ISO-8601 normalisieren.
2. Temperaturwerte als Ganzzahlen übernehmen.
3. Kanonischen Text erzeugen.
4. SHA-256 berechnen.

Beispiel in Python:

```python
import hashlib

canonical = (
    f"{start.isoformat(timespec='minutes')}|"
    f"{len(temperatures)}|"
    + ",".join(str(value) for value in temperatures)
)

burn_id = hashlib.sha256(
    canonical.encode("utf-8")
).hexdigest()
```

## Atomisches Speichern

Neue JSON-Dateien werden zuerst als temporäre Datei geschrieben.

Ablauf:

1. in `<datei>.tmp` schreiben,
2. Daten vollständig flushen,
3. temporäre Datei atomisch in Zieldatei umbenennen.

Dadurch entstehen bei Stromausfall möglichst keine beschädigten Historieneinträge.

## Umgang mit unvollständigen Datensätzen

Unvollständige Archive werden standardmäßig nicht in die dauerhafte Historie übernommen.

Optional können sie später getrennt gespeichert werden unter:

```text
data/history-incomplete/
```

Für Version 0.6.0 gilt zunächst:

- abgeschlossene Abbrände speichern,
- unvollständige Abbrände überspringen,
- Überspringen protokollieren.

## MQTT-Modell

Langfristiges Ziel:

- ein Sensor `Letzter Abbrand`,
- Statistik-Sensoren,
- keine dauerhaft wachsende Zahl einzelner Archivsensoren,
- vollständige Kurven primär lokal speichern.

Vorgesehene MQTT-Entitäten:

```text
sensor.wifire_kamin_letzter_abbrand
sensor.wifire_kamin_anzahl_abbrande
sensor.wifire_kamin_durchschnittliche_maximaltemperatur
sensor.wifire_kamin_heissester_abbrand
sensor.wifire_kamin_durchschnittliche_dauer
```

## Nebenläufigkeit

Es darf nur eine kontrollierte Stelle auf die WiFire-HTTP-Schnittstelle zugreifen.

Das verhindert:

- parallele HTTP-Anfragen,
- Überlastung des Geräts,
- zusätzliche Timeouts,
- Konflikte zwischen Live- und Archivabfragen.

Alle WiFire-Zugriffe werden durch `protocol/client.py` koordiniert.

## Fehlerbehandlung

- HTTP-Fehler begrenzt wiederholen.
- Nach Fehlern längere Pause einhalten.
- Einzelne fehlerhafte Archive überspringen.
- Bereits gespeicherte Daten niemals löschen.
- MQTT-Ausfall darf die lokale Historisierung nicht verhindern.
- Lokale Historisierung darf den Live-Betrieb nicht dauerhaft blockieren.

## Konfiguration

Geplante neue Konfigurationswerte:

```python
HISTORY_ENABLED = True
HISTORY_SYNC_INTERVAL = 21600
HISTORY_ARCHIVE_FIRST = 1
HISTORY_ARCHIVE_LAST = 23
HISTORY_DIRECTORY = "data/history"
```

`HISTORY_DIRECTORY` soll relativ zum Projekt ausgewertet werden.

## Migrationsstrategie

Version 0.6.0 wird schrittweise eingeführt.

### Phase 1

- Datenmodelle,
- stabile ID,
- lokale Speicherung,
- Import bestehender Archive.

### Phase 2

- automatische Synchronisation,
- Duplikaterkennung im laufenden Dienst.

### Phase 3

- neues MQTT-Historienmodell,
- Statistikwerte.

### Phase 4

- alte 22 Archiv-Discovery-Entitäten bereinigen.

## Tests

Mindestens folgende Tests sind vorgesehen:

- identische Rohdaten erzeugen identische `burn_id`,
- unterschiedliche Temperaturkurven erzeugen unterschiedliche IDs,
- Archivnummer beeinflusst die ID nicht,
- Duplikate werden nicht doppelt gespeichert,
- beschädigte JSON-Dateien werden erkannt,
- unvollständige Datensätze werden übersprungen,
- atomisches Schreiben erzeugt gültige Dateien.

## Nicht im Scope

Weiterhin ausgeschlossen:

- Schreibzugriffe auf die Steuerung,
- Änderung von Abbrandparametern,
- Änderung von Schließzeitverzögerungen,
- Steuerung von Luftklappe oder Lüfter,
- Ersatz der FireControls-App.

## Offene Entscheidungen

Vor der Implementierung festzulegen:

1. Soll die Dauer als Anzahl Messpunkte oder anhand der letzten Klappenstufe definiert werden?
2. Soll der vollständige SHA-256-Hash oder nur eine verkürzte ID im Dateinamen stehen?
3. In welchem Intervall sollen Archive im laufenden Betrieb geprüft werden?
4. Sollen alte Einzel-Archivsensoren automatisch entfernt oder nur dokumentiert werden?

## Nächster Implementierungsschritt

Als Erstes werden umgesetzt:

1. `protocol/models.py`
2. `history/identifiers.py`
3. `history/storage.py`
4. Tests für stabile ID und Duplikaterkennung

Erst danach wird die laufende MQTT-Bridge angepasst.
