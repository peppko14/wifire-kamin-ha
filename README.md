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
- stabile SHA-256-ID und Duplikaterkennung
- atomisches Speichern der JSON-Dateien
- Import bereits vorhandener Archive
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

Mindestens MQTT-Adresse, Benutzername und Passwort anpassen. `config.py`
ist von Git ausgeschlossen.

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
- optionaler Lüfter-Rohwert

Ein Eintrag in `configuration.yaml` ist nicht erforderlich.

## Lokale Abbrandhistorie

Abgeschlossene Abbrände werden als einzelne JSON-Dateien gespeichert:

```text
data/history/<startzeit>_<kurze-burn-id>.json
```

Die ID basiert auf Startzeit, Messpunktanzahl und vollständiger
Temperaturkurve. Die rotierende Archivnummer gehört bewusst nicht zur
Identität. Dadurch wird derselbe Abbrand nicht mehrfach gespeichert.

`data/` enthält persönliche Laufzeitdaten und wird nicht versioniert.

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

Version 0.6.1 umfasst 93 automatisierte Tests.

## Werkzeuge

- `tools/history_importer_v1_0_1.py`: lokale Historie importieren
- `tools/archive_importer_v1.0.0.py`: Archivdaten untersuchen
- `tools/archive_mapper_v1.0.0.py`: Archivfelder zuordnen
- `tools/endpoint_scanner_v1.0.0.py`: bekannte Endpunkte prüfen
- `tools/reverse_engineering_suite_v1.0.0.py`: Protokollanalyse

## Roadmap

Für eine spätere Version vorgesehen:

- Statistiken aus der lokalen Historie
- Monats- und Saisonvergleiche
- Home-Assistant-Dashboard
- weiter vereinheitlichte Protokollschnittstelle

## Lizenz

Dieses Projekt steht unter der GNU General Public License v3.0 only.
Details enthält die Datei `LICENSE`.

## Haftungsausschluss

Dieses private Hobbyprojekt steht in keiner Verbindung zu FireControls.
Alle Marken- und Produktnamen gehören ihren jeweiligen Inhabern. Die
Nutzung erfolgt auf eigene Verantwortung.
