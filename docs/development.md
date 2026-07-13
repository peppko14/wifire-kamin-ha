# Entwicklungsrichtlinien

Dokumentversion: 1.1.0

Diese Regeln gelten für die WiFire-Kamin Home Assistant Bridge.

## Lizenz

Neue Quellcodedateien beginnen mit:

```python
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only
```

Das Projekt steht unter GNU GPL v3.0 only.

## Python und Stil

- Mindestversion Python 3.11
- PEP 8 und aussagekräftige Namen
- Typannotationen für neue Funktionen
- `snake_case` für Funktionen und Variablen
- `PascalCase` für Klassen
- `UPPER_CASE` für Konstanten
- kleine Funktionen und klar getrennte Verantwortlichkeiten
- für zentrale Datenstrukturen bevorzugt `@dataclass(slots=True)`
- neue Abhängigkeiten in `requirements.txt` dokumentieren

## Dateien und Pfade

- keine benutzerspezifischen absoluten Pfade,
- `pathlib.Path` statt `os.path`,
- Projektpfade relativ zur jeweiligen Quelldatei bestimmen,
- Laufzeitdaten ausschließlich unter `data/`,
- `data/`, `config.py`, virtuelle Umgebungen und Zugangsdaten niemals
  committen.

## Konfiguration

- Private Werte stehen ausschließlich in `config.py`.
- Öffentliche Standardwerte stehen in `config.example.py`.
- Neue Konfigurationswerte benötigen einen sinnvollen Standardwert und
  eine kurze Erklärung.
- Persönliche Broker-Adressen, Benutzernamen und Passwörter dürfen nicht
  in Code, Tests oder Dokumentation gelangen.

## Ausschließlich lesender Zugriff

Nicht zulässig sind:

- Änderung von Abbrandparametern,
- Änderung von Schließzeitverzögerungen,
- Steuerbefehle für Luftklappe oder Lüfter,
- Firmware-Updates,
- sonstige schreibende Gerätefunktionen.

HTTP-POST ist nur zulässig, wenn er wie `/direct/35` ausschließlich eine
lesende Archivabfrage transportiert.

## Bridge-Architektur

- MQTT-Topics werden ausschließlich in `bridge/topics.py` erzeugt.
- Discovery-Payloads gehören nach `bridge/discovery.py`.
- MQTT-Veröffentlichungen gehören nach `bridge/publisher.py`.
- Live-Polling und Intervallwahl gehören nach `bridge/polling.py`.
- Archivzugriff und -koordination gehören nach `bridge/archive.py` und
  `bridge/archive_sync.py`.
- Zeitplanung gehört nach `bridge/scheduler.py`.
- Die zyklische Ablaufsteuerung gehört nach `bridge/runtime.py`.
- `mqtt_discovery.py` bleibt ein schlanker Programmeinstieg.

## Historie

- Ein Abbrand wird durch eine reproduzierbare SHA-256-ID identifiziert.
- Grundlage sind Startzeit, Messpunktanzahl und Temperaturkurve.
- Die rotierende Archivnummer darf die ID nicht beeinflussen.
- Nur vollständige Abbrände werden dauerhaft gespeichert.
- JSON-Dateien werden atomisch geschrieben.
- Bereits vorhandene Abbrände werden nicht überschrieben.
- Änderungen am JSON-Format erfordern eine neue Historien-Schema-Version.

## Netzwerk und Fehlerbehandlung

- Der WiFire-Webserver darf nicht durch parallele Anfragen belastet werden.
- Wiederholungsversuche sind begrenzt.
- Zwischen Archivzugriffen werden konservative Pausen eingehalten.
- Fehler werden verständlich protokolliert und nicht still ignoriert.
- SIGINT und SIGTERM müssen die Bridge kontrolliert beenden.
- Keine Zugangsdaten oder vollständigen privaten Payloads protokollieren.

## MQTT

- Discovery und Availability werden retained veröffentlicht.
- Jede Entität besitzt eine stabile `unique_id`.
- Alle Entitäten gehören zum Gerät `WiFire-Kamin`.
- Ein MQTT-Ausfall darf vorhandene lokale Historien nicht beschädigen.

## Tests

Vor jedem Commit:

```bash
python3 -m py_compile \
  mqtt_discovery.py \
  bridge/*.py \
  history/*.py \
  protocol/*.py

python3 -m unittest discover \
  -s tests \
  -p "test_*.py" \
  -v
```

Neue Logik benötigt passende Unit-Tests. Tests müssen ohne echten Kamin,
MQTT-Broker und Home Assistant ausführbar sein. Ein Hardware-Praxistest
ergänzt die Unit-Tests vor einem Release, ersetzt sie aber nicht.

## Git-Workflow

- größere Änderungen in einem eigenen Branch durchführen,
- Commits klein und thematisch zusammenhängend halten,
- vor jedem Commit `git status` und `git diff` prüfen,
- nur die vorgesehenen Dateien mit `git add <dateien>` aufnehmen,
- temporäre Downloads und Sicherungskopien nicht committen.

## Versionsverwaltung

Die Projektversion steht zentral in `VERSION`; `version.py` liest sie zur
Laufzeit ein. Es gilt Semantic Versioning:

- `PATCH`: kompatible Fehlerbehebungen,
- `MINOR`: kompatible neue Funktionen,
- `MAJOR`: inkompatible Änderungen.

Vor jedem Release müssen diese drei Angaben synchron sein:

1. `VERSION` enthält `X.Y.Z`.
2. `CHANGELOG.md` enthält den Abschnitt `[X.Y.Z]`.
3. Der Git-Tag lautet `vX.Y.Z`.

## Versionierte Werkzeuge

Eigenständige Werkzeuge unter `tools/` tragen ihre Version im Dateinamen
und zusätzlich als `__version__` im Quellcode. Beide Angaben müssen
übereinstimmen.

## Release-Prozess

1. Funktionsumfang einfrieren.
2. `VERSION`, `CHANGELOG.md`, `README.md`, Architektur und
   Beispielkonfiguration aktualisieren.
3. Syntaxprüfung und vollständige Tests ausführen.
4. Prüfen, dass keine privaten Daten oder Laufzeitdateien enthalten sind.
5. Einen kurzen Hardware-/MQTT-Praxistest durchführen.
6. Release-Commit erstellen und Branch nach `main` zusammenführen.
7. Annotierten Tag `vX.Y.Z` erstellen.
8. `main` und Tag nach GitHub übertragen.

## Freigabekriterien

Eine Version darf veröffentlicht werden, wenn:

- alle automatisierten Tests erfolgreich sind,
- die Syntaxprüfung erfolgreich ist,
- das Git-Arbeitsverzeichnis nach dem Release-Commit sauber ist,
- `VERSION`, Changelog und Tag übereinstimmen,
- README und Architektur den tatsächlichen Stand beschreiben,
- keine privaten Daten enthalten sind,
- der kontrollierte Programmstart und -stopp funktionieren,
- MQTT-Verbindung und Home Assistant Discovery praktisch geprüft wurden.

## Getestete Hardware

- Raspberry Pi 3 Model B+
- FireControls WiFire in der untersuchten Geräte-/Firmwarevariante

Nicht unterstützt werden FireControls WiFire NET und WiFire H2O. Die
optionale Lüfterhardware wurde nicht praktisch getestet.
