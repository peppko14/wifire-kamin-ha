# WiFire-Kamin Home Assistant Bridge

Eine ausschließlich lesende MQTT-Bridge für eine FireControls
WiFire-Kaminsteuerung. Sie überträgt Live-Daten an Home Assistant und
sichert abgeschlossene Abbrände dauerhaft auf einem Raspberry Pi.

## Funktionen

- Home Assistant MQTT Discovery ohne YAML-Konfiguration
- Temperatur, Luftklappe, Türstatus und Abbrenndauer
- optionale Diagnoseentität für einen gekoppelten Lüfter
- adaptive Live-Abfrage:
  - 10 Sekunden während eines aktiven Abbrands
  - 60 Sekunden im Normalbetrieb
  - 5 Minuten nach Kommunikationsfehlern
- lesender Zugriff auf archivierte Abbrände
- automatische lokale Historisierung unter `data/history/`
- schonende Synchronisation der bekannten Ringpufferplätze 1 bis 23
- stabile SHA-256-ID und Duplikaterkennung
- atomisches Speichern der JSON-Dateien
- Historien-Schema 2 mit zentraler Dauer- und Qualitätsdefinition
- getrennte Diagnoseablage für unvollständige Datensätze
- rein lesendes Audit für Historie und Diagnoseablage
- Import bereits vorhandener Archive
- lokale Abbrandstatistik mit optionalem Datumsfilter
- sechs automatisch erkannte Statistikentitäten in Home Assistant
- Monatsstatistiken und Heizsaisonberichte von Juli bis Juni
- drei rollierende Heizsaisons zum direkten Vergleich in Home Assistant
- begrenzte Wiederholungsversuche für die instabile Geräteschnittstelle
- portabler systemd-Installer

Das Projekt schreibt keine Daten oder Einstellungen zur Steuerung zurück.

## Getestete Umgebung

- Raspberry Pi 3 Model B+
- Raspberry Pi OS
- Python 3.11 oder neuer
- Mosquitto MQTT Broker
- Home Assistant mit MQTT-Integration
- FireControls WiFire in der im Projekt untersuchten Geräte-/Firmwarevariante

Nicht unterstützt werden die modernere **FireControls WiFire NET**-Variante
und **WiFire H2O**. Die optionale Lüfterfunktion der unterstützten WiFire
konnte mangels angeschlossener Hardware nicht praktisch getestet werden.

## Netzwerkaufbau

Der Raspberry Pi verwendet zwei Verbindungen:

```text
Heimnetz/MQTT <-- Ethernet --> Raspberry Pi <-- WLAN --> WiFire-Kamin
```

- `eth0` verbindet den Raspberry mit dem Heimnetz und MQTT-Broker.
- `wlan0` verbindet ihn ausschließlich mit dem WiFire-WLAN.
- Die getestete WiFire-Steuerung ist unter `192.168.0.1` erreichbar.

## Installation

Repository klonen:

```bash
git clone https://github.com/peppko14/wifire-kamin-ha.git
cd wifire-kamin-ha
```

Virtuelle Umgebung und Abhängigkeiten einrichten:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Private Konfiguration anlegen:

```bash
cp config.example.py config.py
nano config.py
```

Mindestens MQTT-Adresse, Benutzername und Passwort anpassen. Der optionale
inklusive Statistikfilter kann beispielsweise so gesetzt werden:

```python
STATISTICS_SINCE = "2026-01-01"
```

Mit `None` wird die gesamte lokale Historie berücksichtigt. `config.py` ist
von Git ausgeschlossen.

## Manueller Start

```bash
source venv/bin/activate
python3 -u mqtt_discovery.py
```

Mit `Strg+C` wird die Bridge kontrolliert beendet.

## systemd-Dienst

```bash
chmod +x systemd/install_service_v0.5.1.sh
sudo systemd/install_service_v0.5.1.sh
```

Der Installer erkennt Benutzer, Projektpfad und Python-Umgebung. Status
prüfen:

```bash
sudo systemctl status wifire-kamin.service --no-pager -l
```

## Home Assistant

MQTT Discovery erzeugt automatisch das Gerät **WiFire-Kamin** mit
Entitäten für:

- Temperatur
- Luftklappenstellung und Bewegung
- Türstatus
- Abbrenndauer
- Verfügbarkeit
- drei aktuelle Archivplätze als Diagnoseentitäten
- Anzahl berücksichtigter historischer Abbrände
- Zeitpunkt des neuesten historischen Abbrands
- gesamte und mittlere historische Abbrenndauer
- mittlere historische Maximaltemperatur
- höchste historische Temperatur
- aktueller Statistikmonat mit Anzahl, Dauer und mittlerer Maximaltemperatur
- aktuelle, vorherige und vorvorherige Heizsaison mit jeweils:
  - Saisonbezeichnung
  - Anzahl der Abbrände
  - gesamter und mittlerer Abbrenndauer
  - mittlerer Maximaltemperatur und Höchsttemperatur
- optionaler Lüfter-Rohwert

Ein Eintrag in `configuration.yaml` ist nicht erforderlich.

Alle Entitäten verwenden die gemeinsame MQTT-Verfügbarkeit der Bridge. Wird
die Bridge beendet oder der Dienst gestoppt, zeigt Home Assistant die
Entitäten deshalb als **nicht verfügbar** an. Beim nächsten Start werden sie
wieder verfügbar; die Statistikwerte selbst werden retained veröffentlicht.

## Lokale Abbrandhistorie

Abgeschlossene Abbrände werden als einzelne JSON-Dateien gespeichert:

```text
data/history/<startzeit>_<kurze-burn-id>.json
```

Die ID basiert auf Startzeit, Messpunktanzahl und vollständiger
Temperaturkurve. Die rotierende Archivnummer gehört bewusst nicht zur
Identität. Dadurch wird derselbe Abbrand nicht mehrfach gespeichert.

`data/` enthält persönliche Laufzeitdaten und wird nicht versioniert.

Das vollständige Schema, die Dauerdefinition und alle Qualitätsregeln sind in
[`docs/history-schema.md`](docs/history-schema.md) dokumentiert.

### Bestehende Archive importieren

Da die WiFire-Schnittstelle empfindlich auf schnelle Folgeanfragen
reagiert, sollten konservative Pausen verwendet werden:

```bash
python3 -u tools/history_importer_v1_0_1.py \
  --first 1 \
  --last 23 \
  --delay 10 \
  --retries 5
```

Während eines manuellen Vollimports sollte der laufende Bridge-Dienst
gestoppt sein, damit nicht mehrere Prozesse gleichzeitig zugreifen.

### Automatische Synchronisation

Die Bridge prüft den Ringpuffer nur im konfigurierten, langen
Archivintervall. Die Plätze werden nacheinander mit mindestens zehn Sekunden
Abstand gelesen. Bereits bekannte Abbrände beenden den Scan frühzeitig;
unvollständige oder vorübergehend nicht lesbare Plätze werden protokolliert.

Neue vollständige Abbrände werden zuerst atomisch lokal gespeichert. Erst
danach folgt die optionale MQTT-Veröffentlichung. Ein MQTT-Ausfall kann daher
keinen bereits gelesenen Abbrand aus der lokalen Historie entfernen.

## Historienstatistik

Die Statistik wird aus den lokalen JSON-Dateien berechnet. Sie benötigt
keine zusätzlichen HTTP-Anfragen an den WiFire-Kamin und wird nach einer
Archiv-Synchronisation über MQTT aktualisiert.

Manuelle Textausgabe:

```bash
python3 tools/history_statistics_v1_2_0.py --since 2026-01-01
```

Maschinenlesbare Ausgabe:

```bash
python3 tools/history_statistics_v1_2_0.py \
  --since 2026-01-01 \
  --json
```

Monatsbericht:

```bash
python3 tools/history_statistics_v1_2_0.py \
  --since 2026-01-01 \
  --monthly
```

Heizsaisonbericht:

```bash
python3 tools/history_statistics_v1_2_0.py \
  --since 2026-01-01 \
  --seasons
```

Eine Heizsaison beginnt am 1. Juli und endet am 30. Juni des Folgejahres.
Home Assistant veröffentlicht immer die aktuelle sowie die beiden
vorherigen Saisons als feste, automatisch rollierende Entitäten. Zeiträume
ohne Abbrand besitzen Anzahl und Dauer `0`; nicht berechenbare Mittel- oder
Höchsttemperaturen bleiben unbekannt.

Die Abbrenndauer wird aus den Phasenzeitpunkten rekonstruiert. Dabei werden
Überläufe der als Byte gespeicherten Minutenwerte berücksichtigt. Maßgeblich
ist der entrollte Zeitpunkt der Klappenstellung 0 %. Die Anzahl der
Temperaturmesspunkte ist ausdrücklich keine Dauerangabe.

## Historien-Audit

Historie und Diagnoseablage können vollständig und ohne Kaminzugriff geprüft
werden:

```bash
python3 tools/history_audit_v1_0_0.py
```

Mit `--json` entsteht eine maschinenlesbare Ausgabe. Dateien mit unsicheren
Zeitstempeln bleiben verwendbar und werden als Warnung ausgewiesen;
strukturell beschädigte Dateien führen zu einem Fehlerstatus.

## Projektstruktur

```text
wifire-kamin-ha/
├── bridge/              MQTT, Polling, Archiv und Laufzeitsteuerung
├── history/             IDs, Speicherung und History Manager
├── protocol/            Datenmodelle und Archivadapter
├── tests/               automatisierte Unit-Tests
├── tools/               Import- und Analysewerkzeuge
├── docs/                Architektur und Entwicklungsrichtlinien
├── systemd/             portable Dienstinstallation
├── data/                lokale, nicht versionierte Laufzeitdaten
├── mqtt_discovery.py    schlanker Programmeinstieg
├── decoder.py           Live-Dekodierung
├── wifire_protocol.py   Archivdekodierung
├── config.example.py    öffentliche Konfigurationsvorlage
├── VERSION
└── CHANGELOG.md
```

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

Der Entwicklungsstand für Version 0.9.0 umfasst 215 automatisierte Tests.

## Werkzeuge

- `tools/history_importer_v1_0_1.py`: lokale Historie importieren
- `tools/history_statistics_v1_2_0.py`: Gesamt-, Monats- und Saisonstatistik
- `tools/history_audit_v1_0_0.py`: Historie und Diagnoseablage prüfen
- `tools/archive_importer_v1.0.0.py`: Archivdaten untersuchen
- `tools/archive_mapper_v1.0.0.py`: Archivfelder zuordnen
- `tools/endpoint_scanner_v1.0.0.py`: bekannte Endpunkte prüfen
- `tools/reverse_engineering_suite_v1.0.0.py`: Protokollanalyse

## Roadmap

Für eine spätere Version vorgesehen:

- Home-Assistant-Dashboard
- weiter vereinheitlichte Protokollschnittstelle

## Lizenz

Dieses Projekt steht unter der GNU General Public License v3.0 only.
Details enthält die Datei `LICENSE`.

## Haftungsausschluss

Dieses private Hobbyprojekt steht in keiner Verbindung zu FireControls.
Alle Marken- und Produktnamen gehören ihren jeweiligen Inhabern. Die
Nutzung erfolgt auf eigene Verantwortung.
