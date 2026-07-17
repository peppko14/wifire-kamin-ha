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
- verifiziertes Historien-Backup mit sicherem Wiederherstellungstest
- zusammengefasste Offline- und Netzwerk-Betriebsdiagnose
- Import bereits vorhandener Archive
- lokale Abbrandstatistik mit optionalem Datumsfilter
- sechs automatisch erkannte Statistikentitäten in Home Assistant
- Monatsstatistiken und Heizsaisonberichte von Juli bis Juni
- drei rollierende Heizsaisons zum direkten Vergleich in Home Assistant
- retained Historien-, Statistik- und Brennkurvenwerte bleiben auch bei
  ausgeschaltetem Raspberry in Home Assistant verfügbar
- digitale historische Brennkurven mit expliziter Messpunktachse
- Durchschnitt, historischer Median, letzter Abbrand sowie reale Referenzen
- eigene Mediankurven für aktuelle und zwei vorherige Heizsaisons
- portabler JSON-Export als Grundlage für spätere Diagramme
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
python3 -m pip install \
  --require-hashes \
  --only-binary=:all: \
  -r requirements.lock
```

`requirements.in` dokumentiert den erlaubten direkten Versionsbereich.
`requirements.lock` fixiert das tatsächlich installierte Wheel einschließlich
SHA-256-Prüfsumme. Dadurch schlägt die Installation fehl, wenn Paketversion,
Dateiformat oder Inhalt vom geprüften Lockfile abweichen.

Private Konfiguration anlegen:

```bash
cp config.example.py config.py
chmod 600 config.py
nano config.py
```

Mindestens MQTT-Adresse, Benutzername und Passwort anpassen. Der optionale
inklusive Statistikfilter kann beispielsweise so gesetzt werden:

```python
LOG_LEVEL = "INFO"
LIVE_EXPIRE_AFTER = 180
STATISTICS_SINCE = "2026-01-01"
```

Mit `None` wird die gesamte lokale Historie berücksichtigt. `config.py` ist
von Git ausgeschlossen. Für `LOG_LEVEL` sind `DEBUG`, `INFO`, `WARNING`,
`ERROR` und `CRITICAL` zulässig.

`LIVE_EXPIRE_AFTER` gibt in Sekunden an, wann Home Assistant einen Live-Wert
ohne neue MQTT-Nachricht als nicht verfügbar kennzeichnet. Der öffentliche
Standard entspricht dem Dreifachen des normalen Abfrageintervalls. Mit
`LIVE_EXPIRE_AFTER = None` lässt sich diese zusätzliche Überwachung
deaktivieren.

Die lokale Live-Brennkurve beginnt, sobald
`ACTIVE_FIRE_TEMPERATURE_C` erreicht ist. Sie endet erst nach mehreren
aufeinanderfolgenden kälteren Messungen, damit ein kurzer Ausschlag die
Sitzung nicht zerteilt. Die Anzahl ist optional konfigurierbar:

```python
LIVE_CURVE_END_AFTER_INACTIVE_SAMPLES = 3
```

Der aktuelle Zwischenstand liegt atomisch unter
`data/live-curve/current.json`. Nach einem Neustart wird er fortgesetzt.
Abgeschlossene Live-Sitzungen werden getrennt unter
`data/live-curve/completed/` aufbewahrt. Sie werden noch nicht automatisch
mit einem später importierten Archiv-Abbrand gleichgesetzt.

### Optionale MQTT-Verschlüsselung

Im vertrauten Heimnetz bleibt die bisherige unverschlüsselte Verbindung
standardmäßig aktiv. Für einen TLS-fähigen Broker kann die private
`config.py` beispielsweise so ergänzt werden:

```python
MQTT_PORT = 8883
MQTT_TLS_ENABLED = True
MQTT_TLS_CA_CERT = "/etc/mosquitto/certs/ca.crt"
MQTT_TLS_CLIENT_CERT = None
MQTT_TLS_CLIENT_KEY = None
MQTT_TLS_INSECURE = False
```

Ohne eigenen CA-Pfad verwendet Python die vertrauenswürdigen
Systemzertifikate. Ein Client-Zertifikat und sein Schlüssel müssen immer
gemeinsam gesetzt werden. Der Brokername in `MQTT_HOST` muss zum Zertifikat
passen; bei einer IP-Adresse muss das Zertifikat diese IP als alternativen
Namen enthalten.

`MQTT_TLS_INSECURE = True` deaktiviert die Prüfung der Brokeridentität. Diese
Option ist ausschließlich für eine kurze Fehlersuche gedacht und erzeugt
beim Start eine Warnung.

## Manueller Start

```bash
source venv/bin/activate
python3 -u mqtt_discovery.py
```

Mit `Strg+C` wird die Beendigung der Bridge angefordert. Bereits laufende
Archivabfragen und deren Wiederholungsversuche können derzeit noch bis zum
Ende des aktuellen Synchronisationslaufs weiterlaufen.

## systemd-Dienst

```bash
chmod +x systemd/install_service_v0.12.4.sh
chmod +x systemd/uninstall_service_v0.12.4.sh
sudo systemd/install_service_v0.12.4.sh
```

Der Installer erkennt Benutzer, Projektpfad und Python-Umgebung, setzt
`config.py` auf Modus `600`, legt den privaten Schreibpfad `data/` an und
prüft die gerenderte Unit vor der Installation. Das Betriebssystem und das
Projekt bleiben für den Dienst schreibgeschützt; nur `data/` ist beschreibbar.

Status und Sandbox prüfen:

```bash
sudo systemctl status wifire-kamin.service --no-pager -l
sudo systemd-analyze verify \
  /etc/systemd/system/wifire-kamin.service
sudo systemd-analyze security wifire-kamin.service
```

Bei einem Startfehler zeigt das Journal die Ursache:

```bash
sudo journalctl \
  -u wifire-kamin.service \
  --no-pager \
  -n 100
```

Nur Warnungen und Fehler anzeigen:

```bash
sudo journalctl \
  -u wifire-kamin.service \
  -p warning \
  --no-pager
```

Weitere Hinweise einschließlich Rückfall- und Deinstallationsweg stehen in
[`systemd/README_service_v0.12.4.md`](systemd/README_service_v0.12.4.md).

## Home Assistant

MQTT Discovery erzeugt automatisch das Gerät **WiFire-Kamin** mit
Entitäten für:

- Temperatur
- Luftklappenstellung und Bewegung
- Türstatus
- Abbrenndauer
- laufende, zeitgestempelte Brennkurve als Diagnoseentität
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

Nur die Live-Entitäten verwenden die MQTT-Verfügbarkeit der Bridge. Wird die
Bridge beendet oder der Raspberry ausgeschaltet, zeigt Home Assistant daher
Temperatur, Luftklappe, Tür, Abbrenndauer, laufende Brennkurve und den
optionalen Lüfter als **nicht verfügbar** an.

Zusätzlich besitzen diese Live-Entitäten eine Ablaufzeit. Bleibt eine neue
Live-Nachricht aus, markiert Home Assistant die Werte nach standardmäßig drei
normalen Abfrageintervallen als nicht verfügbar. So werden auch festgefahrene
Live-Werte erkannt, wenn die MQTT-Verbindung selbst noch besteht. Die Frist
kann über `LIVE_EXPIRE_AFTER` angepasst oder mit `None` deaktiviert werden.

Archive, historische Gesamt- und Periodenstatistiken sowie der
Brennkurven-Vergleich besitzen bewusst keine Bindung an den Online-Status der
Bridge. Ihre MQTT-Zustände werden retained veröffentlicht und bleiben deshalb
sichtbar, bis die Bridge einen neuen Wert sendet. Dadurch können insbesondere
die zuletzt veröffentlichten Heizsaisons und Brennkurven auch während einer
vollständig abgeschalteten Sommerpause des Raspberry angezeigt werden. Der
MQTT-Broker und Home Assistant müssen dafür weiterlaufen.

Alle Discovery-Komponenten besitzen neben ihrer stabilen `unique_id` eine
deterministische `default_entity_id`. Damit bleiben die vorgeschlagenen
Entity-IDs auch bei künftigen Änderungen der sichtbaren Namen stabil. Bereits
in Home Assistant registrierte Entity-IDs werden dadurch nicht umbenannt.

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
python3 -u tools/history_importer_v1_0_3.py \
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

Die produktive Ringpuffer-Synchronisation und der manuelle Vollimport nutzen
gemeinsam `protocol/archive.py`. Die Schnittstelle nimmt nur eine
Archivnummer entgegen und erzeugt daraus selbst den fest definierten lesenden
`/direct/35`-Request. Beliebige Hex-Befehle können darüber nicht gesendet
werden. Der technisch mögliche Ein-Byte-Bereich 1 bis 255 ist dabei keine
bestätigte Aussage zur tatsächlichen Anzahl der Archivplätze. Die produktive
Scan-Grenze bleibt bis zur kontrollierten Untersuchung unverändert.

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

## Historien-Backup

Die reguläre Historie und die Diagnoseablage können gemeinsam in einer
verifizierten ZIP-Datei gesichert werden:

```bash
python3 tools/history_backup_v1_0_0.py create
```

Das enthaltene Manifest dokumentiert jede Datei mit Größe und vollständiger
SHA-256-Prüfsumme. Backups können später erneut geprüft und ausschließlich in
ein neues Zielverzeichnis testweise wiederhergestellt werden. Der Kamin und
der MQTT-Broker werden dafür nicht benötigt. Der vollständige Ablauf ist in
[`docs/history-backup.md`](docs/history-backup.md) beschrieben.

## Betriebsdiagnose

Eine zusammengefasste, nur lesende Prüfung steht als versioniertes Werkzeug
bereit:

```bash
python3 tools/system_diagnostics_v1_0_0.py
```

Mit `--offline --skip-service` werden Netzwerk und Dienststatus bewusst
übersprungen. Der Bericht enthält niemals MQTT-Zugangsdaten. Details sind in
[`docs/operations-diagnostics.md`](docs/operations-diagnostics.md)
dokumentiert.

## Digitale Brennkurven

Die vollständigen Temperaturverläufe der lokalen Historie können gemeinsam
analysiert und als portables JSON exportiert werden:

```bash
python3 tools/burn_curve_export_v1_0_0.py
```

Der Export enthält alle Einzelkurven, die Durchschnittskurve, den realen
Abbrand mit dem kleinsten RMSE zur Durchschnittskurve und getrennt den
Abbrand mit der höchsten Einzeltemperatur. Die Achse bleibt bewusst ein
`sample_index` und wird nicht ohne Protokollnachweis als Minute bezeichnet.
Details stehen in [`docs/burn-curves.md`](docs/burn-curves.md).

Für Home Assistant verdichtet die Bridge die Historie in einem begrenzten
Schema 2. Die bisherigen Reihen Durchschnitt, repräsentativer Abbrand und
heißester Abbrand bleiben erhalten. Hinzu kommen letzter Abbrand,
Medianreferenz und drei saisonale Mediankurven. MQTT Discovery stellt sie als
eine gemeinsame retained Diagnoseentität bereit. Ein Beispiel für ein
interaktives Diagramm steht in
[`docs/home-assistant-dashboard.md`](docs/home-assistant-dashboard.md).

Die lokale Erfassung laufender Brennkurven ist in die erfolgreichen
Live-Abfragen eingebunden. Home Assistant erhält dafür eine getrennte
nicht-retained Diagnoseentität mit Zeitzonen-Zeitstempeln und Temperaturen.
Lange Sitzungen werden gleichmäßig auf höchstens 121 veröffentlichte Punkte
verdichtet; die vollständige lokale Sitzung bleibt unverändert. Die noch
folgenden Live-Vergleiche und neutralen Bewertungsbegriffe sind in
[`docs/live-curve-comparison.md`](docs/live-curve-comparison.md) spezifiziert.

## Betriebsresilienz

Beschädigte JSON-Dateien blockieren die Historienauswertung nicht. Die Bridge
protokolliert jede betroffene Datei, verarbeitet alle lesbaren Datensätze
weiter und verändert die beschädigten Dateien nicht. Wenn keine einzige Datei
lesbar ist, bleiben die zuletzt retained veröffentlichten Auswertungen in
Home Assistant unverändert.

Kurze Aussetzer des WiFire-WLANs werden innerhalb eines Live-Zyklus begrenzt
wiederholt. Die optionale private Konfiguration lautet:

```python
LIVE_RETRY_COUNT = 2
LIVE_RETRY_DELAY = 2
```

`LIVE_RETRY_COUNT` bezeichnet die Gesamtzahl der Versuche. Der Wert `1`
stellt das Verhalten ohne Wiederholung wieder her.

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

Die vollständige Testsuite ist ohne echten Kamin, MQTT-Broker und Home
Assistant ausführbar. Version 0.13.0 umfasst 424 automatisierte Tests.

## Werkzeuge

- `tools/history_importer_v1_0_3.py`: lokale Historie importieren
- `tools/history_statistics_v1_2_0.py`: Gesamt-, Monats- und Saisonstatistik
- `tools/history_audit_v1_0_0.py`: Historie und Diagnoseablage prüfen
- `tools/history_backup_v1_0_0.py`: Historie sichern, prüfen und restaurieren
- `tools/system_diagnostics_v1_0_0.py`: Betriebszustand zusammengefasst prüfen
- `tools/burn_curve_export_v1_0_0.py`: Brennkurven und Referenzen exportieren
- `tools/archive_slot_probe_v1_0_0.py`: kleine explizite Bereiche oberhalb
  von Archivplatz 23 ausschließlich lesend untersuchen
- `tools/archive_importer_v1.0.0.py`: Archivdaten untersuchen
- `tools/archive_mapper_v1.0.0.py`: Archivfelder zuordnen
- `tools/endpoint_scanner_v1.0.0.py`: bekannte Endpunkte prüfen
- `tools/reverse_engineering_suite_v1.0.0.py`: Protokollanalyse

## Roadmap

Mit v0.13.0 umgesetzt:

- robuste Medianreferenz und saisonale Kurvenvergleiche
- Vergleich des letzten abgeschlossenen Abbrands mit historischen Referenzen
- getrennte laufende Brennkurve mit atomischem Zwischenstand und eigener
  Home-Assistant-Live-Entität

Für spätere Versionen vorgesehen:

- v0.14: gemeinsame ausschließlich lesende Archivschnittstelle, danach Bridge
  und Vollimport darauf umstellen, Archivplätze oberhalb 23 kontrolliert
  untersuchen und einen realen Rohmitschnitt als Golden Fixture aufnehmen
- Backlog: laufende Archivabfragen und Retry-Wartezeiten bei einem
  Beendigungssignal unmittelbar abbrechen

Die Sicherheitsgrenzen und der Ablauf der Untersuchung oberhalb von Platz 23
sind in [`docs/archive-slot-probe.md`](docs/archive-slot-probe.md)
dokumentiert. Ein lesbarer Platz wird erst nach Auswertung der privaten
Rohdaten als tatsächlicher zusätzlicher Archivplatz bewertet.

## Lizenz

Dieses Projekt steht unter der GNU General Public License v3.0 only.
Details enthält die Datei `LICENSE`.

## Haftungsausschluss

Dieses private Hobbyprojekt steht in keiner Verbindung zu FireControls.
Alle Marken- und Produktnamen gehören ihren jeweiligen Inhabern. Die
Nutzung erfolgt auf eigene Verantwortung.
