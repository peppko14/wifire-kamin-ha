# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Dokumentation

- verifiziertes Referenzprofil `UNIVERSAL / UNI-80°C` mit WEB `w3.3.3`,
  MCU `ver.37 B368` und Firmwarestand November 2024 dokumentiert
- WiFire H2O einschließlich Kessel-, Puffertemperaturen und Umwälzpumpe
  ausdrücklich vom unterstützten Geräteprofil abgegrenzt
- Abbrenndauer als gespeicherte S5-/0-%-Phasenmarke präzisiert und vom durch
  die Schließzeitverzögerung möglicherweise späteren mechanischen
  Klappenschluss unterschieden
- Klappenpositionen der Abbrandphasen als heizgeräteprofilabhängig
  dokumentiert; bestehende Archivfeldnamen bleiben vorerst kompatibel

### Datenqualität

- Warnung `timestamp_uncertain` auf eine fehlende belegte
  Zeitsynchronisation der Steuerung präzisiert
- Archiv- und Alarmlisteneinträge mit derselben internen Gerätezeit werden
  nicht mehr als Nachweis eines realen Kalenderjahres interpretiert
- bestehende Zeitstempel bleiben unverändert; es erfolgt keine automatische
  Schätzung oder Verschiebung historischer Datensätze

## [0.14.1] - 2026-07-17

### Zuverlässigkeit

- Archivclient prüft den gemeinsamen Laufzustand vor jedem HTTP-Versuch und
  nach jeder Retry-Wartezeit
- Stoppsignale verhindern weitere Archivrequests und werden als
  kontrollierter Abbruch statt als Lesefehler behandelt
- Ringpuffer-Synchronisation startet nach einem Abbruch keine nachgelagerte
  Statistik- oder Dashboard-Aktualisierung mehr
- Bereits laufende HTTP-Aufrufe bleiben weiterhin durch den konfigurierten
  Request-Timeout begrenzt

### Tests

- Stopp vor dem ersten HTTP-Versuch und während einer Retry-Wartezeit geprüft
- Kontrollierter Abbruch bleibt ohne Lesefehler und ohne nachgelagerte
  Aktualisierung

## [0.14.0] - 2026-07-17

### Archivprotokoll

- Gemeinsamen, ausschließlich lesenden Archivclient unter
  `protocol/archive.py` ergänzt
- Archiv-URL und bekannten `/direct/35`-Lesebefehl zentral aus Live-URL und
  Archivnummer erzeugt
- Beliebige Hex-Befehle aus der öffentlichen Archivschnittstelle
  ausgeschlossen
- JSON- und Hex-Antworten validiert sowie Transportfehler mit begrenzten
  Wiederholungsversuchen behandelt
- Technischen Ein-Byte-Adressraum von 1 bis 255 von der noch zu
  untersuchenden tatsächlichen Gerätegrenze getrennt
- Produktive Ringpuffer-Synchronisation auf den gemeinsamen Archivclient
  umgestellt
- Manuellen Historien-Importer als Version 1.1.0 auf denselben Client
  migriert und auf einen adaptiven Scan umgestellt
- Doppelte HTTP-, Retry- und Befehlslogik aus `history/sync.py`,
  `bridge/archive.py` und dem Importwerkzeug entfernt
- Begrenztes Diagnosewerkzeug `archive_slot_probe_v1_0_0.py` für explizite
  Archivbereiche oberhalb von Platz 23 ergänzt
- Probe auf höchstens 16 sequenzielle Plätze und mindestens zehn Sekunden
  Request-Abstand begrenzt
- Private Rohantworten atomisch ausschließlich unter `data/archive-probe/`
  gespeichert und nicht an Historie oder MQTT weitergegeben
- Archivplätze 24 bis 30 am realen Gerät als adressierbare, syntaktisch
  gültige, aber derzeit leere 506-Byte-Telegramme bestätigt
- Produktiven Scan und Vollimport auf eine technische Sicherheitsgrenze von
  255 erweitert; der erste eindeutig leere Platz oder ein bereits bekannter
  Abbrand beendet den Scan frühzeitig
- Leere Plätze werden weder als unvollständige Abbrände noch als
  Diagnosedateien gespeichert
- Scan nach drei aufeinanderfolgenden Lesefehlern begrenzt, damit ein
  getrenntes WiFire-WLAN keinen stundenlangen Lauf bis zur Sicherheitsgrenze
  auslöst

### Tests

- URL-Ableitung, Befehlsbildung und vollständigen HTTP-Request geprüft
- Antwortvalidierung, Retry-Verhalten und enge Exception-Grenzen getestet
- Ungültige Archivnummern werden vor einem Netzwerkzugriff abgewiesen
- Bridge-Synchronisation und Importer-Client gegen die gemeinsame
  Archivschnittstelle geprüft
- Sicherheitsgrenzen, Reihenfolge, Pausen, Fehlerisolation, Hashvergleich und
  atomische Berichtsausgabe der Archivplatz-Probe getestet
- Leerer-Platz-Erkennung, adaptiven Scanabbruch, fehlende Historien- und
  Diagnoseausgabe sowie technische Lesefehlergrenze getestet
- Vollständiges reales 506-Byte-Archivtelegramm als unveränderliches Golden
  Fixture mit fester SHA-256-Prüfsumme aufgenommen
- Reale Byte-Offsets, Zeitstempel, fünf Phasenwerte, 121 Temperaturen,
  Maximum, Dauer und stabile Burn-ID gegen das Golden Fixture abgesichert

## [0.13.0] - 2026-07-17

### Brennkurvenanalyse

- Versioniertes Datenmodell für zeitgestempelte Messpunkte und laufende
  Brennkurven-Sitzungen ergänzt
- Laufenden Zwischenstand atomisch unter `data/live-curve/current.json`
  gespeichert und nach einem Prozessneustart wieder ladbar gemacht
- Live-Temperatur, Geräte-Abbrennzeit, Statusbyte, Klappenstellung und
  Türzustand je Messpunkt getrennt von der historischen Archivachse erfasst
- Lokale Live-Sitzung ab der bestehenden Aktivtemperatur automatisch
  gestartet und nach konfigurierbar vielen kalten Messungen abgeschlossen
- Laufende Sitzung nach Prozessneustart fortgesetzt und abgeschlossene
  Live-Sitzungen getrennt unter `data/live-curve/completed/` aufbewahrt
- Live-Messpunkte vor der MQTT-Veröffentlichung lokal gespeichert, sodass ein
  MQTT-Ausfall die laufende Kurve nicht verhindert
- Aktuelle und zwei vorherige Heizsaisons als feste, vergleichbare
  Kurvenmomentaufnahme ergänzt
- Für jede ausreichend große Heizsaison eine eigene Mediankurve und einen
  realen Median-Referenzabbrand berechnet
- Leere und zu kleine Saisons als `not_evaluable` beibehalten, ohne Daten aus
  anderen Zeiträumen einzusetzen
- Gemeinsame Messpunktanzahl über alle Saisonkurven erzwungen und uneindeutige
  Achsen ohne expliziten Filter abgewiesen
- Qualitätswarnungen aus den saisonalen Referenzgruppen ausgeschlossen und
  Quell- sowie Eignungsanzahl getrennt offengelegt
- Letzten abgeschlossenen Abbrand deterministisch bestimmt und vor der
  Referenzberechnung aus seiner eigenen Vergleichsgruppe entfernt
- RMSE des letzten Abbrands zur historischen Mediankurve berechnet
- Optionalen realen Referenzabbrand ausschließlich über seine stabile
  `burn_id` ausgewählt und mit getrenntem RMSE verglichen
- Warnstatus des letzten Abbrands und zu kleine Referenzgruppen transparent
  als `not_evaluable` statt als scheinbar belastbares Ergebnis behandelt
- Messpunktanzahl des letzten Abbrands automatisch als Kompatibilitätsfilter
  für seine Referenzgruppe verwendet
- Punktweise Mediankurve als robuste Ergänzung zur bestehenden
  Durchschnittskurve implementiert
- Realen Referenzabbrand getrennt und deterministisch über den kleinsten RMSE
  zur Mediankurve bestimmt
- Referenzgruppen standardmäßig auf Abbrände mit Qualitätsstatus `valid`
  begrenzt und optional nach Heizsaison, Starttemperatur sowie Messpunktanzahl
  filterbar gemacht
- Zu kleine Referenzgruppen als `not_evaluable` ausgewiesen, ohne fachlich
  ungeeignete Datensätze ersatzweise aufzunehmen
- Gemischte Messpunktanzahlen ohne expliziten Filter als uneindeutig
  abgewiesen
- Bestehende Durchschnitts-, Export- und Home-Assistant-Strukturen für eine
  versionierte Migration weiterhin unter ihren bisherigen Schlüsseln erhalten

### Home Assistant

- Eigene Diagnoseentität `Laufende Brennkurve` auf einem getrennten
  nicht-retained MQTT-Topic ergänzt
- Laufende Kurve an Live-Verfügbarkeit und `LIVE_EXPIRE_AFTER` gebunden,
  damit eine alte Sitzung nicht als aktueller Kaminzustand erscheint
- Zeitgestempelte Live-Kurve gleichmäßig auf höchstens 121 veröffentlichte
  Punkte und insgesamt 16 KiB begrenzt
- Inaktiven Zustand ausdrücklich mit leeren Kurvenarrays veröffentlicht
- Retained Brennkurven-Momentaufnahme auf Dashboard-Schema 2 angehoben
- Bestehende Reihen `average`, `representative` und `hottest` kompatibel
  beibehalten
- Letzten Abbrand, historische Mediankurve und realen Median-Referenzabbrand
  als kompakte Temperaturreihen ergänzt
- Historischen Vergleichsstatus, Referenzgruppengröße und RMSE zum Median
  veröffentlicht
- Aktuelle und zwei vorherige Heizsaisons mit Status, Quellanzahl,
  Eignungsanzahl und optionaler Mediankurve ergänzt
- Nicht auswertbare Gruppen ohne erfundene Temperaturwerte dargestellt
- Gesamtgröße der erweiterten retained Nachricht weiterhin auf 16 KiB begrenzt

### Getestet

- Eigenes Live-Kurven-Topic, Discovery-Availability, Ablaufzeit und
  nicht-retained Veröffentlichung
- Begrenzung langer Live-Sitzungen auf 121 Punkte bei Erhalt des ersten und
  letzten Messpunkts sowie Einhaltung der 16-KiB-Grenze
- Roundtrip, Schema-Validierung und atomischer Austausch laufender
  Brennkurven-Zwischenstände
- Wiederaufnahme nach Neustart sowie erkennbare beschädigte und inkonsistente
  Live-Kurven-Dateien
- Start an der Temperaturschwelle, Hysterese durch mehrere kalte Messungen,
  Fortsetzung einer gespeicherten Sitzung und getrennte Finalisierung
- Speicherfehler deaktivieren nur die Kurvenerfassung und überschreiben keine
  beschädigte Zwischenstandsdatei
- Abwärtskompatible Schlüssel und Dashboard-Schema-Version 2
- Median-, letzter-Abbrand- und optionale Referenzreihen
- Drei saisonale Einträge einschließlich `not_evaluable`
- Maximale Payload-Größe auch mit 121 Messpunkten und allen Vergleichsreihen
- Feste Reihenfolge von aktueller und zwei vorherigen Heizsaisons
- Eigene Medianberechnung je Saison und korrekte Grenze am 1. Juli
- Leere, zu kleine und durch Qualitätswarnungen unzureichende Saisons
- Gemeinsame sowie explizit gefilterte Messpunktanzahlen über Saisonkurven
- Stabile Saisonabfrage und Ablehnung doppelter Abbrand-IDs
- Ausschluss des letzten Abbrands aus seiner eigenen Referenzgruppe
- Vergleich mit Median und explizit ausgewähltem realen Referenzabbrand
- Ablehnung unbekannter, ungeeigneter und selbstreferenzierender `burn_id`
- Nicht bewertbare Vergleiche bei Warnstatus oder zu kleiner Referenzgruppe
- Automatische Begrenzung auf kompatible Messpunktanzahlen
- Medianberechnung für gerade und ungerade Gruppengrößen sowie Ausreißer
- Deterministische Auswahl des realen Median-Referenzabbrands
- Qualitäts-, Heizsaison-, Starttemperatur- und Messpunktfilter
- Zu kleine, doppelte und nicht eindeutig vergleichbare Referenzgruppen

### Dokumentation

- Fachliches Zielmodell für Medianreferenz, saisonale Kurvenvergleiche,
  letzten Abbrand und eine getrennte laufende Brennkurve festgelegt
- Referenzauswahl auf gültige, vergleichbare Datensätze mit expliziten Filtern
  und Mindestgruppengröße begrenzt
- Neutrale Bewertungstexte definiert und unbelegte Aussagen über einen
  gesunden, optimalen oder besten Abbrand ausgeschlossen
- Zeitgestempelte Live-Reihe ausdrücklich vom unbestätigten historischen
  `sample_index` getrennt; Live-Bewertung bis zur realen Achsenvalidierung als
  `noch nicht bewertbar` vorgesehen
- Architektur-, Brennkurven- und Roadmap-Dokumentation auf den Stand v0.13.0
  sowie die nächste geplante Ausbaustufe v0.14 aktualisiert

## [0.12.5] - 2026-07-16

### Wartbarkeit

- Fehlende private `config.py` wird beim Programmstart mit konkreten
  Einrichtungsschritten und definiertem Rückgabecode gemeldet
- Importfehler innerhalb einer vorhandenen Konfiguration bleiben als echte
  Programmfehler sichtbar und werden nicht fälschlich als Ersteinrichtung
  behandelt
- Zentrale, konfigurierbare Protokollierung mit Zeitstempel sowie den Stufen
  DEBUG, INFO, WARNING, ERROR und CRITICAL ergänzt
- Eine gemeinsame Logger-Instanz an Live-Polling, MQTT, Laufzeitsteuerung,
  Ringpufferabgleich, Historienablage, Statistik und Brennkurvenausgabe
  weitergegeben
- Warnungen und Fehler getrennt von normalen Statusmeldungen ausgegeben,
  damit systemd-Journale nach Priorität gefiltert werden können

### Home Assistant

- Live-Entitäten werden nach einer konfigurierbaren Frist ohne neuen
  Zustandswert als nicht verfügbar gekennzeichnet
- Standardfrist auf das Dreifache des normalen Live-Abfrageintervalls gesetzt;
  bestehende private Konfigurationen erhalten den sicheren Standard automatisch
- Archive, Historienstatistiken und Brennkurven bleiben von der Ablaufzeit
  ausgenommen und damit während der Sommerabschaltung dauerhaft sichtbar
- Aktuelles `default_entity_id` für alle MQTT-Entitäten ergänzt; bestehende
  `unique_id`-Werte und registrierte Entity-IDs bleiben unverändert

### Getestet

- 361 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Verständliche Ersteinrichtungsdiagnose bei fehlender privater `config.py`
- Zentrale Protokollierung, gültige und ungültige Log-Level sowie Weitergabe
  derselben Logger-Instanz an alle produktiven Komponenten
- Standardmäßige, angepasste und deaktivierte Ablaufzeit für sämtliche
  Live-Entitäten einschließlich optionalem Lüfter
- Dauerhafte Verfügbarkeit retained veröffentlichter Archive, Statistiken und
  Brennkurven ohne `expire_after`
- Deterministische `default_entity_id` für alle Discovery-Komponenten
- Ruff-, Mypy- und Whitespace-Prüfungen ohne Befund

## [0.12.4] - 2026-07-16

### Sicherheit

- Optionale TLS-Verschlüsselung und Broker-Zertifikatsprüfung für MQTT ergänzt
- Systemvertrauensspeicher, eigene CA und optionale gegenseitige
  TLS-Authentifizierung werden unterstützt
- Bestehende Installationen bleiben standardmäßig beim bisherigen
  unverschlüsselten MQTT-Transport
- Unvollständige TLS-Konfigurationen werden vor dem Verbindungsaufbau
  abgewiesen; deaktivierte Hostnamenprüfung erzeugt eine deutliche Warnung
- systemd-Dienst durch eingeschränkte Dateisystem-, Geräte-, Prozess-,
  Capability- und Netzwerkadressfamilien-Rechte gehärtet
- Projektdateien werden im Dienst nur noch gelesen; ausschließlich `data/`
  bleibt als privater Laufzeitpfad beschreibbar
- Installer prüft die gerenderte Unit vor der Installation und sichert eine
  vorhandene Dienstdatei als Rückfallmöglichkeit
- Private `config.py` wird bei der Installation auf Dateimodus `600` gesetzt
- Direkte Laufzeitabhängigkeiten und reproduzierbares Lockfile getrennt
- Paho-MQTT auf eine geprüfte Version und dessen SHA-256-Wheel-Prüfsumme
  festgelegt
- Produktive Installation und CI erzwingen Hash-Prüfung und lehnen
  Quellpakete sowie nicht freigegebene Paketdateien ab

### Getestet

- 344 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- MQTT-Verbindungen ohne TLS, mit Systemvertrauensspeicher, eigener CA und
  optionalem Client-Zertifikat
- Ablehnung widersprüchlicher TLS-Konfigurationen vor dem Verbindungsaufbau
- systemd-Unit mit `systemd-analyze verify` geprüft und mit einem
  Gesamtexpositionswert von 2,9 als `OK` bewertet
- Hash-verifizierter Download des freigegebenen Paho-MQTT-Wheels
- Ruff-, Mypy-, Shell-Syntax- und Whitespace-Prüfungen ohne Befund

## [0.12.3] - 2026-07-16

### Resilienz

- Beschädigte Historien-Dateien werden bei Sammelauswertungen einzeln
  protokolliert und übersprungen
- Lesbare Datensätze liefern weiterhin Statistiken und Brennkurven, ohne
  beschädigte Dateien zu löschen oder zu verändern
- Ausschließlich beschädigte Bestände überschreiben retained MQTT-Werte
  nicht mit leeren Auswertungen
- Statistik und Brennkurven-Vergleich werden unabhängig voneinander
  aktualisiert
- Live-Abfragen werden bei kurzen WLAN- oder Nutzdatenfehlern standardmäßig
  einmal nach einer kontrollierten Pause wiederholt
- Anzahl und Abstand der Live-Leseversuche sind konfigurierbar; ein einzelner
  Versuch stellt das bisherige Verhalten wieder her
- Veralteten, ausschließlich von eigenen Tests referenzierten
  `ArchiveSynchronizer` entfernt; die produktive Ringpuffer-Synchronisation
  bleibt die einzige Archivkoordination der Bridge

### Getestet

- 329 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Mischbestand aus lesbarer und beschädigter Historien-Datei
- Schutz retained Auswertungen bei ausschließlich beschädigten Dateien
- Erfolgreicher zweiter Live-Leseversuch nach simuliertem WLAN-Aussetzer
- Begrenzung, Abbruchverhalten und enge Exception-Auswahl der Live-Retries
- Ruff-, Mypy- und Whitespace-Prüfungen ohne Befund

## [0.12.2] - 2026-07-16

### Home Assistant

- Gemeinsame Geräteverfügbarkeit auf die tatsächlichen Live-Entitäten
  begrenzt
- Temperatur, Luftklappe, Tür, Abbrenndauer und optionaler Lüfter werden bei
  ausgeschaltetem Raspberry weiterhin als nicht verfügbar gekennzeichnet
- Retained Archive, Gesamt- und Periodenstatistiken sowie der
  Brennkurven-Vergleich bleiben unabhängig vom Bridge-Online-Status sichtbar
- Anzeige der zuletzt veröffentlichten Heizsaisons und Brennkurven während
  einer vollständig abgeschalteten Sommerpause ermöglicht

### Dokumentiert

- Unterschied zwischen flüchtigen Live-Werten und dauerhaft gespeicherten
  Auswertungen erläutert
- Verzögerte Programmbeendigung während laufender Archiv-Retries als
  Backlog-Punkt aufgenommen

### Getestet

- 325 automatisierte Tests ohne Kamin, MQTT-Broker oder Home Assistant
- Produktive Trennung der Verfügbarkeit in Home Assistant geprüft
- Historienstatistik und Brennkurven trotz nicht erreichbarer
  WiFire-Steuerung erfolgreich aus der lokalen Historie veröffentlicht

## [0.12.1] - 2026-07-15

### Code-Hardening

- Optionale MQTT-TLS-Unterstützung als offener Backlog-Punkt dokumentiert

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
