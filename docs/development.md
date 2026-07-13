# Entwicklungsrichtlinien

Version: 1.0.0

Diese Datei beschreibt die verbindlichen Entwicklungs- und Strukturregeln für das Projekt **WiFire-Kamin Home Assistant Bridge**.

## Lizenz und Copyright

Alle neuen Quellcodedateien müssen mit folgendem SPDX-Header beginnen:

```python
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only
```

Für Shell-Skripte gilt:

```bash
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only
```

Das gesamte Projekt steht unter der GNU General Public License Version 3.0 only.

## Python-Version

- Mindestversion: Python 3.11
- Neue Funktionen sollen mit Python 3.11 kompatibel bleiben.
- Neue Abhängigkeiten müssen in `requirements.txt` eingetragen werden.

## Stilrichtlinien

- PEP 8 einhalten.
- Funktionen und Variablen in `snake_case`.
- Klassen in `PascalCase`.
- Konstanten in `UPPER_CASE`.
- Aussagekräftige Namen verwenden.
- Keine unnötigen Abkürzungen.
- Funktionen möglichst klein und auf eine Aufgabe begrenzen.
- Komplexe Logik in Hilfsfunktionen auslagern.

## Typannotationen

Neue Funktionen sollen Typannotationen verwenden.

Beispiel:

```python
def decode_temperature(raw: str) -> int:
    ...
```

Für komplexe Datenstrukturen sollen `dataclass`, `TypedDict` oder klar dokumentierte Dictionaries verwendet werden.

## Dateipfade

- Keine benutzerspezifischen absoluten Pfade.
- Keine Pfade wie `/home/benutzer/...` im Repository.
- `pathlib.Path` statt `os.path` verwenden.
- Projektpfade relativ zur Datei bestimmen.

Beispiel:

```python
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
```

Für Werkzeuge im Unterordner `tools/`:

```python
PROJECT_DIR = Path(__file__).resolve().parent.parent
```

## Konfiguration

- Private Werte ausschließlich in `config.py`.
- `config.py` darf nicht in Git aufgenommen werden.
- Öffentliche Vorlage in `config.example.py`.
- Keine Passwörter, Tokens oder privaten IP-Adressen in Beispiel-, Test- oder Dokumentationsdateien.
- Neue konfigurierbare Werte mit sinnvollen Standardwerten dokumentieren.

## Versionsverwaltung

Die Projektversion wird zentral verwaltet über:

```text
VERSION
version.py
```

Versionsschema:

```text
MAJOR.MINOR.PATCH
```

- `PATCH`: Fehlerbehebungen und kleine Wartungsänderungen
- `MINOR`: neue rückwärtskompatible Funktionen
- `MAJOR`: inkompatible Änderungen

Jede veröffentlichte Version erhält:

- Eintrag in `CHANGELOG.md`
- passenden Git-Tag, z. B. `v0.6.0`
- aktualisierte Datei `VERSION`

## Dateiversionen für Werkzeuge

Eigenständige Werkzeuge im Ordner `tools/` tragen ihre Versionsnummer im Dateinamen:

```text
archive_importer_v1.0.0.py
archive_mapper_v1.0.0.py
```

Zusätzlich soll im Quellcode stehen:

```python
__version__ = "1.0.0"
```

Dateiname und interne Versionsnummer müssen übereinstimmen.

## Projektstruktur

Vorgesehene Struktur:

```text
wifire-kamin-ha/
├── docs/
├── systemd/
├── tools/
├── data/
├── mqtt_discovery.py
├── wifire_protocol.py
├── config.example.py
├── version.py
├── VERSION
├── CHANGELOG.md
├── LICENSE
└── README.md
```

Laufzeitdaten gehören nach `data/` und dürfen nicht ins Repository eingecheckt werden.

## Lesender Zugriff

Das Projekt arbeitet ausschließlich lesend.

Nicht zulässig sind:

- Schreibzugriffe auf die FireControls WiFire-Steuerung
- Ändern von Abbrandparametern
- Ändern von Schließzeitverzögerungen
- Firmware-Updates
- Steuerbefehle für Luftklappe oder Lüfter

Neue Funktionen müssen diese Grenze einhalten.

## Fehlerbehandlung

- Netzwerk- und MQTT-Fehler müssen verständlich protokolliert werden.
- Wiederholungsversuche müssen begrenzt sein.
- Endlosschleifen ohne Abbruchbedingung vermeiden.
- Fehler nicht stillschweigend ignorieren.
- Dienste müssen auf `SIGINT` und `SIGTERM` sauber reagieren.

## Logging

- Dienstmeldungen sollen ohne Pufferung erscheinen.
- systemd verwendet Python mit `-u`.
- Keine sensiblen Daten protokollieren.
- Logmeldungen kurz, verständlich und handlungsorientiert formulieren.

## MQTT

- MQTT-Topics zentral definieren.
- Discovery-Nachrichten retained veröffentlichen.
- Availability retained veröffentlichen.
- Live-Zustände nur retained veröffentlichen, wenn dies ausdrücklich sinnvoll ist.
- Eindeutige `unique_id`-Werte verwenden.
- Alle Entitäten dem Gerät `WiFire-Kamin` zuordnen.

## Historienverwaltung

Für jeden abgeschlossenen Abbrand wird eine stabile ID erzeugt.

Empfohlene Grundlage:

- Startzeit
- Anzahl Messpunkte
- vollständige Temperaturkurve

Daraus wird ein SHA-256-Hash berechnet.

Die Archivnummer der WiFire-Steuerung darf nicht als dauerhafte ID verwendet werden, da sie sich im Ringpuffer ändern kann.

## Tests

Vor jedem Commit mindestens ausführen:

```bash
python3 -m py_compile   mqtt_discovery.py   wifire_protocol.py   archive_reader.py
```

Zusätzlich die betroffenen Werkzeuge prüfen:

```bash
python3 -m py_compile tools/<datei>.py
```

Später sollen automatisierte Tests für folgende Bereiche ergänzt werden:

- Live-Datendecoder
- Archivdecoder
- stabile Abbrand-ID
- Duplikaterkennung
- Statistikberechnung

## Git-Workflow

Für größere Änderungen:

```bash
git switch -c <thema-version>
```

Vor dem Commit:

```bash
git status
git diff
```

Commits sollen klein und thematisch zusammenhängend sein.

Beispiele:

```text
Make systemd installation portable
Add archive history manager
Fix archive retry handling
```

Keine Zugangsdaten oder Laufzeitdaten committen.

## Dokumentation

Jede neue Funktion soll dokumentiert werden in mindestens einer der folgenden Dateien:

- `README.md`
- `CHANGELOG.md`
- passende Datei unter `docs/`

Befehle und Pfade müssen portabel sein und dürfen keine benutzerspezifischen Werte enthalten.

## Bekannte unterstützte Hardware

Getestet:

- Raspberry Pi 3 Model B+
- FireControls WiFire

Nicht unterstützt:

- FireControls WiFire NET
- FireControls WiFire H2O

Nicht getestet:

- optionale Lüftersteuerung, z. B. für eine Abluftsteuerung am Kochfeld

## Freigabekriterien

Eine Version darf erst veröffentlicht werden, wenn:

- Syntaxprüfung erfolgreich ist
- keine privaten Daten enthalten sind
- `CHANGELOG.md` aktualisiert ist
- `VERSION` aktualisiert ist
- Git-Arbeitsverzeichnis sauber ist
- systemd-Dienst erfolgreich startet
- MQTT-Verbindung funktioniert
- Home Assistant Discovery funktioniert

