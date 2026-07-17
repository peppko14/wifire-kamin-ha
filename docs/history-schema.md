# Historienmodell und Datenqualität

Dokumentversion: 1.0.0

Dieses Dokument beschreibt das ab WiFire-Kamin Home Assistant Bridge v0.9.0
verwendete Historienmodell. Die Historien-Schema-Version ist unabhängig von
der Projektversion.

## Reguläre Historie

Abgeschlossene und fachlich gültige Abbrände werden unter folgendem Pfad
gespeichert:

```text
data/history/<startzeit>_<erste-12-Zeichen-der-burn-id>.json
```

Der Dateiname enthält nur eine verkürzte ID. Im JSON-Dokument steht immer die
vollständige SHA-256-ID. Die ID basiert auf Startzeit, Messpunktanzahl und
vollständiger Temperaturkurve. Die rotierende Archivplatznummer gehört nicht
zur Identität eines Abbrands.

## Schema 2

Neue reguläre Dateien verwenden ausschließlich Schema 2. Beispiel:

```json
{
  "schema_version": 2,
  "burn_id": "vollständiger SHA-256-Hash",
  "start": "2026-04-22T21:23:00",
  "source_archive_number": 1,
  "measurement_count": 121,
  "duration_minutes": 169,
  "duration_source": "stage_0_unwrapped",
  "start_temperature_c": 24,
  "end_temperature_c": 205,
  "max_temperature_c": 453,
  "max_temperature_minute": 42,
  "stage_90_minute": 7,
  "stage_75_minute": 36,
  "stage_50_minute": 57,
  "stage_25_minute": 109,
  "stage_0_minute": 169,
  "temperatures_c": [24, 25, 30],
  "active_or_incomplete": false,
  "quality": {
    "status": "valid",
    "issues": []
  },
  "imported_at": "2026-07-13T20:00:00+00:00"
}
```

Schema 1 wird nicht mehr unterstützt. Da die Historie aus dem WiFire-
Ringpuffer erneut gelesen werden konnte, wurden vorhandene Schema-1-Dateien
durch neu erzeugte Schema-2-Dateien ersetzt.

## Dauerdefinition

`measurement_count` und `duration_minutes` besitzen unterschiedliche
Bedeutungen:

- `measurement_count` ist ausschließlich die Anzahl der Temperaturmesspunkte.
- `duration_minutes` ist der rekonstruierte Zeitpunkt, an dem die Luftklappe
  0 % erreicht.
- `duration_source` lautet `stage_0_unwrapped`.
- Überläufe der als Byte gespeicherten Phasenminuten werden entrollt.
- Fehlt `stage_0_minute`, ist die Dauer unbekannt und bleibt `null`.

Der letzte Temperaturmesspunkt definiert nicht die Abbrenndauer.

## Qualitätsstatus

Jede reguläre Schema-2-Datei besitzt einen verpflichtenden `quality`-Block.

`valid` bedeutet, dass keine Auffälligkeit erkannt wurde. `warning` bedeutet,
dass der Datensatz weiterhin verwendet werden darf, aber einen dokumentierten
Hinweis besitzt. Datensätze mit Qualitätsfehlern werden nicht unter
`data/history/` gespeichert.

### Fehler

- fehlender Startzeitpunkt,
- aktiver oder unvollständiger Abbrand,
- weniger als zwei Temperaturmesspunkte,
- Temperatur außerhalb von −40 bis 1200 °C,
- Archivnummer 0, negativ oder kein zulässiger Ganzzahlwert,
- Phasenwert außerhalb von 0 bis 255.

Archivnummern oberhalb von 23 sind zulässig. Der produktive Scan verwendet
255 lediglich als technische Sicherheitsgrenze und beendet sich am ersten
eindeutig leeren Platz. Ein leerer Platz wird nicht als unvollständiger
Abbrand und nicht als Diagnose gespeichert. Die Archivnummer bleibt damit
eine Transportinformation und keine fachliche Grenze des Historienmodells.

### Warnungen

- eine von 121 abweichende Messpunktanzahl,
- fehlender `stage_0_minute` und damit unbekannte Dauer,
- Startzeitpunkt vor 2020 (`timestamp_uncertain`).

Die sechs vorhandenen Datensätze aus 2017 bleiben auswertbar. Da nicht sicher
unterschieden werden kann, ob sie echte historische Zeiten oder eine damals
falsch eingestellte Geräteuhr darstellen, werden sie nicht verändert und nur
als zeitlich unsicher gekennzeichnet.

## Diagnoseablage

Bereits dekodierbare, aber unvollständige oder fachlich ungültige Datensätze
werden getrennt gespeichert:

```text
data/history-incomplete/
```

Diagnose-Dateien besitzen ihr eigenes Schema 1 und eine eigene stabile
`diagnostic_id`. Sie enthalten Qualitätsgründe und Rohdaten, werden niemals
von der regulären Historienstatistik gelesen und erzeugen bei einem erneuten
Scan keine Duplikate.

Nicht dekodierbare Netzwerk- oder Protokollantworten werden nur als Lesefehler
protokolliert, da daraus kein verlässlicher Datensatz erzeugt werden kann.

## Qualitäts-Audit

Das Audit arbeitet ausschließlich lesend:

```bash
python3 tools/history_audit_v1_0_0.py
```

Maschinenlesbare Ausgabe:

```bash
python3 tools/history_audit_v1_0_0.py --json
```

Es zählt reguläre und diagnostische Dateien, Schema-Versionen,
Qualitätsstatus, Warnungs- und Diagnosegründe sowie strukturell nicht lesbare
Dateien. Ein fehlerfreier Speicherzustand wird mit Exit-Code 0 beendet.

## Referenz-Audit vom 13. Juli 2026

```text
Speicherzustand:           OK
Historien-Dateien:         22
Davon lesbar:              22
Davon nicht lesbar:        0
Qualität gültig:           16
Qualität mit Warnung:      6
Schema-Versionen:          2: 22
Warnungsgründe:            timestamp_uncertain: 6
Diagnose-Dateien:          1
Diagnosen nicht lesbar:    0
Diagnosegründe:            measurement_count_unexpected: 1,
                           record_incomplete: 1
```
