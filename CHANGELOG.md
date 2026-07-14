# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Code-Hardening

- Threadübergreifenden Zugriff auf den letzten MQTT-Live-Status durch
  einen expliziten Lock und stabile Snapshots abgesichert
- GitHub-Actions-Pipeline für Tests mit Python 3.11 und 3.13 sowie verbindliche
  Ruff- und Mypy-Prüfungen ergänzt
- Veralteten und unreferenzierten Top-Level-Archivleser entfernt; produktive
  Archivzugriffe verwenden die getesteten Bridge- und Historienmodule
- Fehlerbehandlung des manuellen History-Importers auf erwartete Netzwerk-
  und Nutzdatenfehler begrenzt; Programmierfehler werden nicht mehr maskiert
- Reproduzierbare, fest versionierte Entwicklungsabhängigkeiten und zentrale
  Werkzeugkonfiguration in `pyproject.toml` aufgenommen
- Bestehende Typverträge für Discovery, Archive, Historie, Diagnose und
  Laufzeitsteuerung an die tatsächlichen Datenflüsse angepasst
- Einheitliche LF-Zeilenenden über `.gitattributes` und `.editorconfig`
  festgelegt
- Bestehende gemischte CRLF-/LF-Dateien für eine einmalige Normalisierung
  vorbereitet
- Ungenutzte lokale Modulversionen entfernt; `VERSION` und `version.py`
  bleiben die einzige Quelle der Projektversion
- Konventionsprüfung für zentrale Projektversion und bewusst separat
  versionierte Werkzeuge ergänzt
- Ein einziges unveränderliches `LiveStatus`-Modell für Bridge, MQTT und
  Betriebsdiagnose
- Zentraler Live-Decoder unter `protocol/live.py`
- Doppelte Live-Status-Dataclass und parallelen dict-basierten Decoder
  entfernt
- MQTT-Payload und Laufzeitverhalten durch direkte Vertragstests abgesichert
- Direkte Regressionstests für vollständige 506-Byte-Archivtelegramme,
  Feld-Offsets, Zeitstempel, Temperaturreihen und Phasenüberläufe

## [0.12.0] - 2026-07-14

### Brennkurven-Dashboard

- Kompakte Brennkurven-Momentaufnahme für Home Assistant
- Genau drei Temperaturreihen: Durchschnitt, repräsentativer Abbrand und
  heißester Abbrand
- Explizite `sample_index`-Achse ohne unbestätigte Zeitannahme
- Temperaturarrays statt einzelner Punktobjekte für kleine MQTT-Payloads
- Feste Größengrenze von 16 KiB mit automatischer Validierung
- Eigenes retained MQTT-Topic für den kompakten Kurvenvergleich
- Eine feste Home-Assistant-Diagnoseentität statt einzelner Kurvensensoren
- Automatische Aktualisierung nach der seltenen Ringpuffer-Synchronisation
- Optionaler, vom Statistikzeitraum unabhängiger Kurvenfilter
- Dokumentiertes Plotly-Dashboard für den interaktiven Vergleich

### Getestet

- 292 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Reale Momentaufnahme aus 16 gefilterten Abbränden mit 121 Messpunkten
- Home-Assistant-Entität mit Schema 1 sowie den Reihen `average`,
  `representative` und `hottest`
- Alle drei Temperaturarrays mit jeweils 121 Werten praktisch verifiziert

## [0.11.0] - 2026-07-14

### Brennkurven

- Unveränderliche Modelle für Messpunkte und historische Brennkurven
- Explizite `sample_index`-Achse ohne unbestätigte Zeitannahme
- Streng validierter Loader für Historien-Schema 2
- Konsistenzprüfung von SHA-256-ID, Messpunkten und abgeleiteten Kennzahlen
- Durchschnittskurve über eine explizite Messpunktachse
- Repräsentativer realer Abbrand über kleinsten RMSE zur Durchschnittskurve
- Getrennte Kennzeichnung der heißesten Kurve ohne qualitative Bewertung
- Atomischer, portabler JSON-Export aller Kurven und Referenzen

### Getestet

- 273 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Strenges Laden aller 22 vorhandenen Schema-2-Brennkurven
- JSON-Export mit 22 Einzelkurven und jeweils 121 Messpunkten
- Separater Zeitraumexport der 16 Abbrände ab 2026

## [0.10.0] - 2026-07-14

### Entwicklungsqualität

- `slots=True` ist für alle Dataclasses verbindlich
- Repositoryweiter AST-Konventionstest verhindert neue Dataclasses ohne
  `slots=True`
- Bestehende Protokollmodelle auf speichersparende Slots umgestellt

### Datensicherung

- Verifiziertes ZIP-Backup für reguläre Historie und Diagnoseablage
- Manifest mit Dateigrößen und SHA-256-Prüfsummen
- Sichere Wiederherstellung ausschließlich in ein neues Zielverzeichnis
- Versioniertes Werkzeug zum Erstellen, Prüfen und testweisen Restaurieren

### Betriebsdiagnose

- Zusammengefasster, nur lesender Zustandsbericht für Konfiguration,
  Speicherplatz, Historie, Backup, WiFire, MQTT und systemd-Dienst
- Offline-Modus und maschinenlesbare JSON-Ausgabe
- Keine Ausgabe oder Übertragung privater MQTT-Zugangsdaten

### Getestet

- 239 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Backup und Wiederherstellung von 22 Historien- und einer Diagnosedatei
- Offline- und vollständige Betriebsdiagnose auf dem Raspberry Pi
- Erfolgreicher WiFire-HTTP-Lesetest und MQTT-TCP-Verbindungstest

## [0.9.0] - 2026-07-14

### Hinzugefügt

- Zentrale Dauerdefinition in `protocol/duration.py`
- Fachliche Qualitätsprüfung in `protocol/quality.py`
- Verpflichtender Qualitätsblock für reguläre Historien-Dateien
- Getrennte, atomische Diagnoseablage unter `data/history-incomplete/`
- Lesendes Historien-Audit mit Text- und JSON-Ausgabe
- Vollständige Schema- und Qualitätsdokumentation in
  `docs/history-schema.md`

### Geändert

- Historienformat auf Schema 2 umgestellt
- Abbrenndauer wird ausschließlich aus dem entrollten Zeitpunkt der
  Klappenstellung 0 % bestimmt
- Messpunktanzahl und Abbrenndauer sind fachlich getrennt
- Schema 1 wurde durch einen vollständigen Neuimport aus dem Ringpuffer
  ersetzt und wird nicht mehr unterstützt
- Bekannte Ringpufferplätze 1 bis 23 sind als Scan-Strategie und nicht als
  feste Protokollgrenze dokumentiert

### Datenqualität

- Temperaturen außerhalb von −40 bis 1200 °C werden abgewiesen
- Unvollständige und ungültige Datensätze gelangen nicht in die Statistik
- Zeitstempel vor 2020 bleiben verwendbar und werden mit
  `timestamp_uncertain` gekennzeichnet
- Archivnummern oberhalb von 23 bleiben zulässig

### Getestet

- 215 automatisierte Tests
- Audit von 22 lesbaren Schema-2-Dateien
- 16 unauffällige und 6 zeitlich unsichere historische Abbrände
- Ein getrennt gespeicherter, unvollständiger Diagnose-Datensatz

## [0.8.0] - 2026-07-13

### Hinzugefügt

- Stabile Kalendermonats- und Heizsaisonmodelle in `history/periods.py`
- Monats- und Saisonaggregation in `history/period_statistics.py`
- Heizsaison vom 1. Juli bis zum 30. Juni des Folgejahres
- Text- und JSON-Berichte für Monate und Heizsaisons im Werkzeug
  `tools/history_statistics_v1_2_0.py`
- Vier feste Home-Assistant-Entitäten für den aktuellen Statistikmonat
- Drei automatisch rollierende Heizsaisons mit jeweils Saisonbezeichnung,
  Anzahl, gesamter und mittlerer Dauer, mittlerer Maximaltemperatur und
  Höchsttemperatur
- Eigenes retained MQTT-Topic für aktuelle Periodenstatistiken

### Geändert

- Statistikwerkzeug von Version 1.1.0 auf 1.2.0 aktualisiert
- `--monthly` und `--seasons` als gegenseitig exklusive Berichtsarten ergänzt
- Der inklusive `--since`-Filter gilt auch für Monats- und Saisonberichte
- Periodenstatistiken werden gemeinsam mit der bestehenden Historienstatistik
  nach einer Archiv-Synchronisation aktualisiert
- Home Assistant verwendet feste Saisonplätze statt dynamisch wachsender
  Entitäten pro historischem Zeitraum

### Getestet

- 173 automatisierte Tests
- Reale Monatsauswertung mit 16 Abbränden aus Februar bis April 2026
- Reale Saison `2025/2026` mit 16 Abbränden, 3298 Minuten Gesamtdauer,
  206,1 Minuten mittlerer Dauer und 665 °C Höchsttemperatur
- Produktive MQTT-Discovery und Darstellung der drei Saisonzeiträume in
  Home Assistant

## [0.7.0] - 2026-07-13

### Hinzugefügt

- Schonende Synchronisation des vollständigen WiFire-Ringpuffers mit den
  bekannten Archivplätzen 1 bis 23
- Lokale Historienstatistik in `history/statistics.py`
- Kommandozeilenwerkzeug `tools/history_statistics_v1_1_0.py` mit Text-,
  JSON- und inklusiver `--since`-Ausgabe
- Sechs Home-Assistant-Entitäten für Anzahl, neuesten Abbrand, gesamte und
  mittlere Dauer sowie mittlere und höchste Temperatur
- Konfigurationswert `STATISTICS_SINCE` für den optionalen Statistikzeitraum
- Tests für Ringpuffer, lokale Speicherung, Statistikberechnung,
  MQTT-Discovery und produktive Integration

### Geändert

- Neue Abbrände werden vor jeder MQTT-Veröffentlichung lokal gespeichert
- Bereits bekannte Abbrände beenden den Ringpuffer-Scan frühzeitig
- Archivzugriffe erfolgen ausschließlich nacheinander und mit mindestens
  zehn Sekunden Abstand
- Abbrenndauern berücksichtigen Überläufe der gespeicherten Phasenminuten
- Statistiken werden nach einer seltenen Archiv-Synchronisation ausschließlich
  aus der lokalen Historie neu berechnet
- MQTT- und Statistikfehler verändern keine bereits gespeicherten Abbrände

### Dokumentiert

- Gemeinsame MQTT-Verfügbarkeit: Bei gestoppter Bridge zeigt Home Assistant
  auch retained Statistikwerte als nicht verfügbar an
- Abgrenzung zwischen gespeicherten Historienwerten und dem Online-Status der
  Bridge

### Getestet

- 141 automatisierte Tests
- Duplikatfreier zweiter Synchronisationslauf
- Statistik mit 22 gespeicherten Datensätzen und Filter ab 2026-01-01
- Produktive MQTT-Veröffentlichung von 16 berücksichtigten und 6
  ausgefilterten Abbränden

## [0.6.1] - 2026-07-13

### Hinzugefügt

- Zentrale MQTT-Verbindungsverwaltung in `bridge/mqtt_client.py`
- Vollständiger Application Runner in `bridge/application.py`
- Unit-Tests für MQTT-Client, Callbacks, Last Will und Reconnect
- Unit-Tests für Anwendungslebenszyklus und Signalbehandlung

### Geändert

- Client-Erzeugung, Login, Last Will, Reconnect und MQTT-Callbacks aus
  `mqtt_discovery.py` ausgelagert
- Komponentenaufbau, Start, Stopp und Signalbehandlung in den Application
  Runner verschoben
- `mqtt_discovery.py` auf einen minimalen Programmeinstieg reduziert

### Getestet

- 93 automatisierte Tests
- MQTT-Verbindung und Home-Assistant-Discovery im Vordergrundbetrieb
- kontrolliertes Beenden mit SIGINT

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
- Archiv-URL wird portabel aus der konfigurierten Live-URL abgeleitet
- Stabile Pausen von zehn Sekunden sind Standard für Archivzugriffe
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
