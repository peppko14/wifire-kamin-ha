# Archivplätze oberhalb 23 untersuchen

Dokumentversion: 1.1.0

Das Werkzeug `tools/archive_slot_probe_v1_0_0.py` untersucht einen ausdrücklich
gewählten kleinen Bereich oberhalb der bislang bestätigten Plätze 1 bis 23.
Es verwendet ausschließlich den fest definierten lesenden Archivrequest aus
`protocol/archive.py`.

Das Werkzeug verändert weder den Kamin noch die lokale Historie und
veröffentlicht keine MQTT-Daten. Die tatsächliche Speichergrenze einer
WiFire-Firmware wird nicht vorausgesetzt.

## Sicherheitsgrenzen

- ausschließlich Plätze 24 bis 255,
- höchstens 16 Plätze pro Lauf,
- strikt sequenzielle Requests,
- mindestens zehn Sekunden Abstand zwischen zwei Plätzen,
- höchstens drei begrenzte Versuche pro Platz,
- keine frei eingebbaren Hex-Befehle,
- keine automatische Ausweitung des Bereichs,
- keine Decodierung oder fachliche Übernahme in `data/history/`.

Der Bereich bis 255 folgt nur aus dem einzelnen Adressbyte im bekannten
Telegramm. Er ist kein Nachweis für 255 tatsächlich vorhandene Speicherplätze.

## Beobachtung vom 17. Juli 2026

Nach Wiederherstellung der WiFire-WLAN-Verbindung wurden die Plätze 24 bis 30
einzeln und mit zehn Sekunden Abstand gelesen. Alle Antworten hatten:

- den erwarteten Paketkopf,
- die bekannte Länge von 506 Bytes,
- die jeweils angefragte Archivnummer,
- keinen Startzeitpunkt,
- keine Temperaturmesspunkte und
- den Zustand aktiv oder unvollständig.

Die Plätze sind damit technisch adressierbar, waren zum Prüfzeitpunkt aber
leer. Platz 23 enthielt gleichzeitig noch einen vollständigen Abbrand. Das
beweist, dass 23 keine feste Protokoll- oder Gerätekapazitätsgrenze ist, aber
nicht, wie viele abgeschlossene Abbrände das Gerät maximal speichert.

Die produktive Synchronisation nutzt diese Beobachtung konservativ: Sie darf
bis zur technischen Ein-Byte-Grenze 255 adressieren, beendet den Scan jedoch
am ersten eindeutig leeren Platz. Der leere Platz wird weder in die Historie
noch in die Diagnoseablage übernommen.

## Voraussetzungen

Der Raspberry muss per WLAN mit dem WiFire verbunden sein. Während der Probe
darf kein zweiter Prozess auf das Gerät zugreifen. Deshalb muss der
Bridge-Dienst vorher gestoppt oder bereits inaktiv sein:

```bash
sudo systemctl stop wifire-kamin.service
sudo systemctl is-active wifire-kamin.service
```

Die zweite Ausgabe muss `inactive` lauten.

## Erster begrenzter Lauf

Für die erste Untersuchung werden nur die Plätze 24 bis 30 gelesen:

```bash
source venv/bin/activate

python3 tools/archive_slot_probe_v1_0_0.py \
  --first 24 \
  --last 30 \
  --delay 10 \
  --retries 1
```

Das Werkzeug zeigt im Terminal nur Platz, Länge und einen verkürzten Hash.
Die vollständigen Antworten werden atomisch unter
`data/archive-probe/archive_probe_*.json` abgelegt. `data/` wird von Git
ignoriert.

## Bericht interpretieren

Jeder Platz erhält einen der Zustände:

- `readable`: Eine syntaktisch gültige Hex-Antwort wurde empfangen.
- `read_error`: Der Platz konnte nach den konfigurierten Versuchen nicht
  gelesen werden.

Zusätzlich werden dokumentiert:

- Byte-Länge,
- SHA-256 des binären Telegramms,
- die ersten acht Bytes,
- Übereinstimmung mit dem bekannten Paketkopf,
- Übereinstimmung mit der bekannten Länge von 506 Bytes,
- identischer Inhalt eines bereits im selben Lauf gelesenen Platzes.

`readable` beweist allein noch keinen eigenständigen gültigen Abbrand. Ein
Gerät könnte beispielsweise leere Daten, eine Spiegelung oder denselben
Datensatz für mehrere Nummern liefern. Erst die Auswertung der gespeicherten
Rohdaten erlaubt eine vorsichtige Aussage.

## Datenschutz und Git

Der JSON-Bericht enthält vollständige Rohtelegramme und damit unter anderem
Zeit- und Temperaturdaten. Er darf nicht ungeprüft in Git aufgenommen werden.
Für ein späteres Golden Fixture wird ein einzelner geeigneter Rohmitschnitt
zuerst fachlich geprüft und anschließend ausdrücklich anonymisiert oder als
zulässiger Testdatensatz freigegeben.

## Weitere Bereiche

Ein weiterer Bereich darf erst nach Auswertung des vorherigen Berichts
untersucht werden. Wegen der Grenze von 16 Plätzen sind beispielsweise
folgende getrennte Läufe möglich:

```text
24–30
31–40
41–50
```

Das Diagnosewerkzeug erweitert seinen Bereich weiterhin niemals automatisch.
Der produktive adaptive Scan verwendet 255 dagegen nur als Sicherheitsgrenze
und erreicht sie im Normalfall nicht, weil der erste leere oder bereits
bekannte Platz den Lauf beendet.
