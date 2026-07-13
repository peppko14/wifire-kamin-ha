# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).

## [0.6.0] - 2026-07-13

### Hinzugefügt

- Modulare Bridge-Pakete für MQTT-Topics, Discovery, Publishing,
  Live-Polling, Archivzugriff, Archiv-Synchronisation, Zeitplanung und
  Laufzeitsteuerung
- Zentrale Datenmodelle `LiveStatus` und `BurnRecord`
- Stabile SHA-256-ID für jeden abgeschlossenen Abbrand
- Atomische lokale Speicherung unter `data/history/`
- Duplikaterkennung unabhängig von der rotierenden Archivnummer
- History Manager für Import und automatische Synchronisation
- Versioniertes Importwerkzeug `tools/history_importer_v1_0_1.py`
- Automatische Übernahme neuer Archivdatensätze in die lokale Historie
- Umfangreiche Unit-Tests für Bridge, Protokolladapter und Historie

### Geändert

- Große Teile der bisherigen Logik aus `mqtt_discovery.py` in klar
  getrennte, testbare Module ausgelagert
- Archivzugriffe werden mit begrenzten Wiederholungen und kontrollierten
  Pausen ausgeführt
- Zeitplanung und unterbrechbare Wartezeiten sind zentral gekapselt
- Dokumentation und Beispielkonfiguration an den Stand von v0.6.0
  angepasst
- Hardwareabgrenzung zwischen WiFire, WiFire NET und WiFire H2O präzisiert

### Getestet

- 79 automatisierte Tests
- Import von 22 abgeschlossenen historischen Abbränden
- Erkennung und Überspringen eines unvollständigen Archivdatensatzes
- Stabiler Betrieb mit konservativen Pausen für den eingebetteten
  WiFire-Webserver

### Verschoben

- Statistikberechnungen und ein Home-Assistant-Dashboard sind für eine
  spätere Version vorgesehen.

## [0.5.1] - 2026-07-13

### Hinzugefügt

- Portabler systemd-Installer `systemd/install_service_v0.5.1.sh`
- Deinstallationsskript `systemd/uninstall_service_v0.5.1.sh`
- Portierbare Service-Vorlage `systemd/wifire-kamin.service.template`
- Archiv-Importer `tools/archive_importer_v1.0.0.py`
- Vollständig überarbeitete Projekt-README
- Dokumentation zur portablen Installation
- Unterstützung für relative Ausgabeordner innerhalb des Projekts
- Vorbereitungen für eine lokale Historienverwaltung mit stabilen, eindeutigen Abbrand-IDs

### Geändert

- Benutzerspezifische Pfade aus dem Repository entfernt
- systemd-Service wird bei der Installation automatisch an Benutzer, Projektpfad und Python-Umgebung angepasst
- Ausgabeordner der Analysewerkzeuge nach `data/` innerhalb des Projekts verschoben
- `README.txt` in `README.md` umbenannt
- Reverse-Engineering-Dokumentation auf portable Pfade umgestellt
- Projektbeschreibung und unterstützte Hardware präzisiert
- Projektumfang ausdrücklich auf rein lesenden Zugriff begrenzt

### Dokumentiert

- Unterstützte Hardware:
  - Raspberry Pi 3 Model B+
  - FireControls WiFire
- Nicht unterstützte Varianten:
  - FireControls WiFire NET
  - FireControls WiFire H2O
- Bekannte Einschränkung:
  - optionale Lüftersteuerung wurde nicht getestet
- Schreibende Funktionen und Einstellungen wie Schließzeitverzögerungen sind nicht Bestandteil des Projekts

## [0.5.0] - 2026-07-11

### Hinzugefügt

- Reverse-Engineering-Suite `tools/reverse_engineering_suite_v1.0.0.py`
- Archiv-Mapper `tools/archive_mapper_v1.0.0.py`
- Endpunkt-Scanner `tools/endpoint_scanner_v1.0.0.py`
- Dokumentation zur lesenden Protokollanalyse
- Zentrale Versionsdatei `VERSION`
- Versionszugriff über `version.py`

### Ermittelt

- 20 gültige GET-Endpunkte unter `/direct/`
- Archivzugriff über POST `/direct/35`
- 22 abgeschlossene historische Abbrände
- 1 unvollständiger Archivdatensatz
- Temperaturkurven und Archivmetadaten vollständig dekodierbar

## [0.4.1] - 2026-07-11

### Hinzugefügt

- Home Assistant MQTT Discovery
- Live-Datenübertragung per MQTT
- Archivierte Abbrände als MQTT-Diagnoseentitäten
- Wiederholungslogik für instabile WiFire-WLAN-Verbindungen
- Dynamische Abfrageintervalle:
  - 10 Sekunden bei aktivem Abbrand
  - 60 Sekunden im Normalbetrieb
  - 5 Minuten nach Lesefehlern

### Unterstützte Live-Daten

- Temperatur
- Luftklappenstellung
- Türstatus
- Abbrenndauer
- Verfügbarkeitsstatus

## [0.1.0] - 2026-07-10

### Hinzugefügt

- Erste lesende Kommunikation mit der FireControls WiFire-Steuerung
- Auslesen von `/direct/00`
- Dekodierung von Temperatur, Luftklappe, Türstatus und Abbrenndauer
- Erste MQTT-Anbindung
