# Architektur

Dokumentversion: 1.13.0

Projektstand: WiFire-Kamin Home Assistant Bridge v0.13.0

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
│   ├── statistics.py
│   ├── dashboard.py
│   ├── dashboard_reporter.py
│   ├── logging_setup.py
│   └── application.py
├── history/
│   ├── backup.py
│   ├── diagnostics.py
│   ├── audit.py
│   ├── identifiers.py
│   ├── storage.py
│   ├── manager.py
│   ├── sync.py
│   ├── ring_buffer.py
│   ├── statistics.py
│   ├── periods.py
│   ├── period_statistics.py
│   ├── curves.py
│   ├── curve_analysis.py
│   ├── curve_reference.py
│   ├── curve_comparison.py
│   ├── curve_seasons.py
│   └── curve_export.py
├── operations/
│   └── diagnostics.py
├── protocol/
│   ├── live.py
│   ├── models.py
│   ├── adapters.py
│   ├── duration.py
│   └── quality.py
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

## Protokoll

### `protocol/archive.py`

Kapselt den gemeinsamen, ausschließlich lesenden Transport für rohe
Archivtelegramme. Aufrufer übergeben nur eine Archivnummer; URL und der fest
definierte `/direct/35`-Lesebefehl werden intern erzeugt. Die Schnittstelle
akzeptiert bewusst keine beliebigen Hex-Befehle.

Die Archivnummer besitzt im bekannten Telegramm genau ein Byte. Deshalb
validiert das Modul technisch den Bereich 1 bis 255. Das ist keine Aussage
darüber, wie viele Plätze die konkrete WiFire-Firmware tatsächlich speichert.
Die bislang produktiv verwendete und beobachtete Scan-Grenze bleibt davon
getrennt. Transport- und ungültige Antwortdaten werden begrenzt wiederholt;
Programmierfehler werden nicht als Netzwerkfehler maskiert.

Produktive Ringpuffer-Synchronisation und manueller Vollimport verwenden
dieselbe Implementierung. Die Scanstrategie bleibt davon getrennt: Die Bridge
beendet den inkrementellen Scan bei einem bekannten Abbrand, während der
manuelle Import einen explizit gewählten Bereich vollständig liest.

## Bridge

### `bridge/topics.py`

Erzeugt alle MQTT-Topics zentral aus Geräte-ID und Discovery-Präfix.

### `bridge/discovery.py`

Erzeugt die Home-Assistant-Device-Discovery für Live-Sensoren,
Diagnosewerte, drei veröffentlichte Archivplätze, Gesamtstatistik, aktuellen
Monat, drei rollierende Heizsaisons und den historischen
Brennkurven-Vergleich. Nur Live-Entitäten verwenden Availability und
`expire_after`.

### `bridge/publisher.py`

Kapselt MQTT-Veröffentlichungen für Verfügbarkeit, Live-Zustand,
Archivattribute sowie retained Gesamt-, Perioden- und Brennkurvendaten.

### `bridge/mqtt_client.py`

Kapselt den vollständigen MQTT-Lebenszyklus: Client-Erzeugung, Anmeldung,
Last Will, Reconnect-Einstellungen, Callbacks, Discovery bei einer
Neuverbindung sowie kontrollierten Start und Stopp. Der zwischen Haupt- und
MQTT-Thread geteilte unveränderliche Live-Status wird unter einem Lock als
stabiler Snapshot ausgetauscht.

### `bridge/polling.py`

Liest und dekodiert einen Live-Datensatz und bestimmt das adaptive
Abfrageintervall:

- 10 Sekunden bei aktivem Abbrand,
- 60 Sekunden im Normalbetrieb,
- 300 Sekunden nach Lesefehlern.

### `bridge/archive.py`

Erzeugt ausschließlich die MQTT-Attribute eines bereits dekodierten
Archivdatensatzes. Der rohe Gerätezugriff liegt zentral in
`protocol/archive.py`.

### `bridge/archive_sync.py`

Koordiniert die bekannten Archivbefehle. Ein gültiger Datensatz wird zuerst
über den History Manager lokal gespeichert und erst danach optional per MQTT
veröffentlicht. Nach Abschluss kann eine Statistikaktualisierung ausgeführt
werden.

### `bridge/scheduler.py`

Enthält wiederkehrende Zeitpläne und eine unterbrechbare Wartefunktion,
damit SIGINT und SIGTERM zeitnah wirken.

### `bridge/runtime.py`

Steuert die zyklische Live-Abfrage, Offline-Erkennung, Archivplanung und
Wartezeit. Die Klasse ist unabhängig vom konkreten MQTT-Client testbar.

### `bridge/live_curve.py`

Definiert das von der historischen Archivachse getrennte Schema für eine
laufende Brennkurve. Jeder Messpunkt besitzt einen Zeitzonen-Zeitstempel,
Temperatur, Geräte-Abbrennzeit und ausgewählte Statusfelder. Der aktuelle
Zwischenstand wird atomisch unter `data/live-curve/current.json` ersetzt und
kann nach einem Prozessneustart streng validiert wieder geladen werden.
Der Recorder startet an der bestehenden Aktivtemperatur, verwendet mehrere
aufeinanderfolgende kalte Messungen als Ende-Hysterese und verschiebt
abgeschlossene Sitzungen nach `data/live-curve/completed/`. Speicherfehler
werden isoliert; MQTT- und Live-Statusverarbeitung laufen weiter.
Für Home Assistant entsteht eine getrennte, nicht-retained Momentaufnahme
mit Zeitstempelachse. Sie ist auf 121 Punkte und 16 KiB begrenzt und verwendet
die Live-Verfügbarkeit einschließlich Ablaufzeit.

### `bridge/statistics.py`

Liest die lokale Historie, wendet den optionalen inklusiven
`STATISTICS_SINCE`-Filter an und veröffentlicht Gesamtstatistik, aktuellen
Monat sowie aktuelle, vorherige und vorvorherige Heizsaison. Ein Fehler in
diesem nachgelagerten Schritt verändert das Ergebnis der lokalen
Archiv-Synchronisation nicht.

### `bridge/application.py`

Erzeugt und verbindet alle Bridge-Komponenten. Der Application Runner
registriert SIGINT und SIGTERM, startet MQTT und Laufzeitsteuerung und
garantiert den kontrollierten MQTT-Stopp auch bei einem Laufzeitfehler. Eine
zentral konfigurierte Logger-Instanz wird an alle produktiven Komponenten
weitergegeben.

### `mqtt_discovery.py`

Ist nur noch der Programmeinstieg. Die Datei lädt Konfiguration und Version,
erzeugt über `create_application()` den Application Runner und startet ihn.

## Protokoll und Datenmodelle

### `decoder.py`

Liest den rohen Live-Datensatz ausschließlich lesend über `/direct/00`.

### `protocol/live.py`

Dekodiert den rohen Live-Datensatz zentral in das unveränderliche
`LiveStatus`-Modell.

### `wifire_protocol.py`

Dekodiert die Rohdaten der Archivantworten.

### `protocol/models.py`

Definiert unveränderliche Datenmodelle:

- `LiveStatus` für dekodierte Live-Daten,
- `BurnRecord` für vollständige oder unvollständige Abbrände.

### `protocol/adapters.py`

Überführt die bestehende Archivstruktur in das zentrale `BurnRecord`-Modell.

### `protocol/duration.py`

Rekonstruiert die fachliche Abbrenndauer zentral aus dem entrollten
Zeitpunkt der Klappenstellung 0 %. Die Messpunktanzahl ist keine Dauer.

### `protocol/quality.py`

Prüft Temperaturgrenzen, Vollständigkeit, Zeitstempel und weitere fachliche
Plausibilitätsregeln. Warnungen bleiben auswertbar; fehlerhafte Datensätze
gelangen ausschließlich in die getrennte Diagnoseablage.

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

### `history/diagnostics.py`

Speichert unvollständige oder fachlich ungültige, aber bereits dekodierbare
Datensätze getrennt und atomisch unter `data/history-incomplete/`. Diese
Diagnose-Dateien besitzen eine eigene stabile ID, werden nicht von der
Statistik gelesen und verändern die reguläre Historie nicht.

### `history/audit.py`

Prüft reguläre Historie und Diagnoseablage vollständig und ausschließlich
lesend. Das Audit zählt Schema-Versionen, Qualitätsstatus, Warnungs- und
Diagnosegründe sowie strukturell nicht lesbare Dateien. Das zugehörige Werkzeug
`tools/history_audit_v1_0_0.py` unterstützt Text- und JSON-Ausgabe.

### `history/backup.py`

Sichert reguläre Historie und Diagnoseablage unverändert in einer ZIP-Datei.
Ein Manifest enthält Dateigrößen und vollständige SHA-256-Prüfsummen. Jedes
Backup wird vor der Freigabe geprüft; eine Wiederherstellung ist nur in ein
neues Zielverzeichnis zulässig.

### `history/manager.py`

Validiert Datensätze, erkennt vorhandene IDs und speichert nur neue,
vollständige Abbrände.

### `history/sync.py`

Stellt die MQTT-unabhängige inkrementelle Ringpuffer-Synchronisation für die
Bridge bereit. Sie verwendet denselben lesenden `ArchiveClient` wie der
manuelle Vollimport. Beide behalten bewusst ihr unterschiedliches
Scanverhalten: inkrementeller Abbruch bei einem bekannten Abbrand gegenüber
vollständigem Lesen eines explizit gewählten Bereichs.

### `history/ring_buffer.py`

Definiert die Strategie für die bekannten Archivplätze 1 bis 23. Der Scan
läuft sequenziell, hält mindestens zehn Sekunden Abstand und kann bei einem
bereits bekannten vollständigen Abbrand frühzeitig enden.

### `history/statistics.py`

Berechnet reproduzierbare Kennzahlen ausschließlich aus den lokal
gespeicherten JSON-Datensätzen. Phasenminuten werden inklusive möglicher
Byte-Überläufe rekonstruiert. Ein optionaler Startzeitpunkt filtert Datensätze
inklusiv, ohne die Quelldateien zu verändern.

### `history/periods.py`

Definiert sortierbare, unveränderliche Zeiträume für Kalendermonate und
Heizsaisons. Eine Heizsaison beginnt inklusiv am 1. Juli und endet exklusiv
am 1. Juli des Folgejahres.

### `history/period_statistics.py`

Gruppiert Datensätze nach Kalendermonat oder Heizsaison und verwendet für
jede Gruppe die bestehende, getestete Statistikberechnung. Für MQTT wird eine
feste Momentaufnahme aus aktuellem Monat und drei aufeinanderfolgenden
Heizsaisons erzeugt. Fehlende Perioden erhalten neutrale Statistiken.

### `history/curves.py`

Überführt streng validierte Schema-2-Datensätze in unveränderliche
Brennkurven. Die Achse heißt `sample_index`, da das tatsächliche
Messintervall nicht als gesicherte Protokolleigenschaft dokumentiert ist.

### `history/curve_analysis.py`

Berechnet parallel die bestehende Durchschnittskurve und eine robuste
punktweise Mediankurve. Zu beiden Lagekurven wird deterministisch der reale
Abbrand mit dem kleinsten RMSE bestimmt; die Kurve mit der höchsten gemessenen
Temperatur bleibt eine getrennte Kennzahl. Alle verglichenen Kurven benötigen
dieselbe Messpunktanzahl.

### `history/curve_reference.py`

Wählt reproduzierbare historische Referenzgruppen aus. Standardmäßig sind nur
Abbrände mit Qualitätsstatus `valid` zugelassen. Optionale Filter begrenzen
die Auswahl auf eine Heizsaison, einen Starttemperaturbereich und eine
Messpunktanzahl. Zu kleine Gruppen werden als `not_evaluable` ausgewiesen;
uneindeutige Gruppen mit gemischten Messpunktanzahlen werden abgewiesen.

### `history/curve_comparison.py`

Bestimmt deterministisch den letzten abgeschlossenen Abbrand und entfernt ihn
vor der Referenzberechnung aus der historischen Vergleichsgruppe. Das Modul
berechnet seinen RMSE zur Mediankurve und optional zu einem über die stabile
`burn_id` ausgewählten realen Referenzabbrand. Ein Abbrand mit Warnstatus oder
eine zu kleine Referenzgruppe ergeben ausdrücklich `not_evaluable`.

### `history/curve_seasons.py`

Erzeugt in fester Reihenfolge die aktuelle und zwei vorherige Heizsaisons.
Jede ausreichend große Saison erhält eine eigene Mediananalyse und einen
realen Median-Referenzabbrand. Leere oder zu kleine Saisons bleiben als
`not_evaluable` sichtbar. Ein gemeinsamer Messpunktfilter verhindert
scheinbar vergleichbare Kurven auf unterschiedlichen Achsen.

### `history/curve_export.py`

Erzeugt und speichert atomisch ein portables JSON-Dokument mit allen
Einzelkurven, Durchschnittskurve, repräsentativer Kurve, heißester Kurve,
Filterinformationen und stabilen Abbrand-IDs.

### `bridge/dashboard.py`

Erzeugt die auf 16 KiB begrenzte retained Kurvenmomentaufnahme nach Schema 2.
Die drei bisherigen Reihenschlüssel bleiben erhalten. Ergänzt werden letzter
Abbrand, historische Medianreferenzen, Vergleichsstatus und drei saisonale
Mediankurven. Nicht auswertbare Gruppen enthalten Status und Grund, aber keine
erfundene Temperaturreihe. Vollständige historische Einzelkurven werden nicht
in Home-Assistant-Attribute kopiert.

### `bridge/dashboard_reporter.py`

Lädt die streng validierten Brennkurven nach einer seltenen
Ringpuffer-Synchronisation, wendet den konfigurierten Zeitraumfilter an und
veröffentlicht die kompakte Momentaufnahme. Bei leerer Historie wird keine
unvollständige Entität erzeugt.

## Betriebsdiagnose

### `operations/diagnostics.py`

Erzeugt einen zusammengefassten, nur lesenden Bericht zu Python-Version,
Konfiguration, Speicherplatz, Historie, Backup, WiFire-Erreichbarkeit,
MQTT-TCP-Port und systemd-Dienst. Netzwerk- und Dienstprüfungen können
übersprungen werden. Private Zugangsdaten sind kein Bestandteil des Berichts.

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
                                                              │
                                                             └──> Statistik
                                                                       │
                                                                       ├──> Gesamt
                                                                       ├──> Monat
                                                                       ├──> 3 Saisons
                                                                       └──> MQTT
```

Alle Zugriffe erfolgen nacheinander innerhalb derselben Laufzeitsteuerung.
Das schützt den eingebetteten Webserver vor parallelen Anfragen.

## Historienformat

Jede JSON-Datei enthält unter anderem:

```json
{
  "schema_version": 2,
  "burn_id": "vollständiger SHA-256-Hash",
  "start": "2026-04-22T21:23:00",
  "source_archive_number": 1,
  "measurement_count": 121,
  "duration_minutes": 169,
  "duration_source": "stage_0_unwrapped",
  "quality": {
    "status": "valid",
    "issues": []
  },
  "max_temperature_c": 453,
  "max_temperature_minute": 26,
  "temperatures_c": [22, 24, 30],
  "active_or_incomplete": false,
  "imported_at": "2026-07-13T12:00:00+00:00"
}
```

Die Historien-Schema-Version ist unabhängig von der Projektversion. Ab
Version 0.9.0 wird ausschließlich Schema 2 unterstützt. Frühere lokale
Schema-1-Dateien werden einmalig durch einen vollständigen, lesenden Neuimport
aus dem WiFire-Ringpuffer ersetzt.

Der Qualitätsblock ist in Schema 2 verpflichtend. `valid` kennzeichnet einen
unauffälligen Datensatz, `warning` einen weiterhin nutzbaren Datensatz mit
Hinweisen wie einem unsicheren Zeitstempel. Datensätze mit Qualitätsfehlern
werden nicht in der regulären Historie gespeichert.

## Fehlerbehandlung

- Live-Fehler führen zu einem längeren Abfrageintervall.
- Nach mehreren Live-Fehlern wird das MQTT-Gerät als offline gemeldet.
- Archivzugriffe besitzen begrenzte Wiederholungsversuche.
- Zwischen Archivanforderungen werden kontrollierte Pausen eingehalten.
- Fehlerhafte Archive verhindern nicht die Verarbeitung weiterer Plätze.
- Vorhandene Historieneinträge werden weder überschrieben noch gelöscht.
- Neue Abbrände werden vor nachgelagerten MQTT-Aktionen lokal gespeichert.
- MQTT- oder Statistikfehler machen eine erfolgreiche lokale Speicherung
  nicht rückgängig.
- Ein gestoppter Dienst setzt ausschließlich die Live-Verfügbarkeit auf
  offline. Retained Archive, Statistiken und historische Brennkurven bleiben
  während einer Sommerabschaltung sichtbar.

## Tests

Version 0.12.5 umfasst 361 Unit-Tests. Netzwerk, MQTT-Broker und Kamin sind
für diese Tests nicht erforderlich.

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## Nächste Ausbaustufen

Für v0.13.0 sind robuste historische Medianreferenzen, saisonale Vergleiche,
die Erfassung einer laufenden Brennkurve und eine getrennte Live-Darstellung
geplant. Eine Live-Bewertung bleibt gesperrt, bis die Zuordnung zwischen der
zeitgestempelten Live-Reihe und dem historischen `sample_index` durch einen
echten Abbrand bestätigt ist. Die fachlichen Regeln stehen in
[`live-curve-comparison.md`](live-curve-comparison.md).

Für v0.14.0 bleiben die weitere Vereinheitlichung der Protokollschnittstelle,
ein reales Golden Fixture, die lesende Untersuchung von Archivplätzen über 23
und die gemeinsame Archivleselogik für Bridge und Vollimport vorgesehen.
