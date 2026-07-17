# Laufende und historische Brennkurvenvergleiche

Dokumentversion: 1.4.0

Dieses Dokument definiert den fachlichen Zielzustand für v0.13.0. Es ist eine
Spezifikation und nimmt noch keine unbestätigte Zuordnung zwischen Live- und
Archivmesspunkten vorweg.

## Implementierungsstand

Mit den Commits 2 bis 4 von v0.13.0 sind folgende historische Grundlagen
umgesetzt:

- punktweise Mediankurve zusätzlich zum bestehenden Durchschnitt,
- eigener realer Referenzabbrand mit kleinstem RMSE zur Mediankurve,
- reproduzierbare Auswahl ausschließlich gültiger Referenzkurven,
- optionale Filter nach Heizsaison, Starttemperatur und Messpunktanzahl,
- expliziter Zustand `not_evaluable` bei einer zu kleinen Referenzgruppe,
- letzter abgeschlossener Abbrand ohne Selbstbezug in der Referenzgruppe,
- RMSE des letzten Abbrands zur Mediankurve,
- optionaler Vergleich zu einem über `burn_id` ausgewählten Referenzabbrand,
- eigene Mediananalyse für aktuelle und zwei vorherige Heizsaisons,
- sichtbarer Zustand `not_evaluable` für leere oder zu kleine Saisons,
- retained Dashboard-Schema 2 mit Median, letztem Abbrand und Saisonkurven.

Die bisher verwendeten Dashboard-Schlüssel bleiben für bestehende Karten
erhalten. Die laufende Live-Erfassung wird erst in den folgenden Commits
ergänzt.

## Ziele

Version 0.13.0 soll folgende Vergleiche reproduzierbar ermöglichen:

- letzter abgeschlossener Abbrand gegen eine historische Mediankurve,
- letzter Abbrand gegen einen explizit ausgewählten Referenzabbrand,
- Abbrände innerhalb derselben Heizsaison,
- Median- und Kennzahlenvergleich verschiedener Heizsaisons,
- laufende Live-Kurve gegen eine geeignete historische Referenzgruppe,
- Höhe und Position des Temperaturmaximums,
- Abweichung einer Kurve von ihrer Referenz.

Aufheiz- und Abkühlgeschwindigkeit werden erst dann als Wert pro Minute
ausgegeben, wenn das tatsächliche Archivmessintervall verifiziert wurde.

## Historische Referenzgruppe

Eine Kurve darf standardmäßig nur in die Referenzgruppe gelangen, wenn:

- ihr Qualitätsstatus `valid` ist,
- sie vollständig und regulär unter `data/history/` gespeichert ist,
- sie eine ausreichende und mit den anderen Kurven identische
  Messpunktanzahl besitzt,
- sie nicht aus der Diagnoseablage oder einer beschädigten Datei stammt,
- sie alle zusätzlich konfigurierten Filter erfüllt.

Optionale Filter sind:

- eine ausgewählte Heizsaison,
- ein inklusiver frühester Startzeitpunkt,
- eine maximale Abweichung der Starttemperatur,
- eine explizite stabile `burn_id`,
- eine Mindestanzahl geeigneter Kurven.

Sind zu wenige geeignete Kurven vorhanden, lautet das Ergebnis
`noch nicht bewertbar`. Die Auswahl darf nicht stillschweigend auf fachlich
ungeeignete Datensätze erweitert werden.

## Median und Durchschnitt

Für jeden gemeinsamen `sample_index` wird der Median der Temperaturen aller
Referenzkurven berechnet. Diese Mediankurve ist die primäre typische
Referenz, da einzelne ungewöhnliche Abbrände sie weniger stark beeinflussen.

Der bestehende arithmetische Durchschnitt bleibt als zusätzliche
beschreibende Reihe erhalten. Er wird nicht ohne Migration aus bestehenden
Export- oder Dashboard-Schemata entfernt.

Der repräsentative reale Abbrand ist die gespeicherte gültige Kurve mit der
kleinsten deterministisch berechneten Abweichung zur Mediankurve. Gleichstände
werden über Startzeit und anschließend `burn_id` aufgelöst.

## Historische Vergleiche

Für den letzten abgeschlossenen Abbrand werden mindestens dokumentiert:

- stabile `burn_id` und Startzeit,
- verwendete Referenzgruppe und deren Größe,
- RMSE oder eine gleichwertige vollständig dokumentierte Abweichungsmetrik,
- Maximaltemperatur,
- Position des Maximums als `sample_index`,
- Start- und Endtemperatur,
- neutrale Einordnung oder `noch nicht bewertbar`.

Der letzte Abbrand wird nicht in seine eigene Medianreferenz aufgenommen.
Eine optional ausgewählte reale Referenz muss nach allen Filtern zur
Referenzgruppe gehören und darf nicht der letzte Abbrand selbst sein.

Saisonvergleiche verwenden die bestehende Heizsaison vom 1. Juli bis zum
30. Juni des Folgejahres. Jede Saison erhält ihre eigene Mediankurve und
offengelegte Anzahl beitragender Abbrände. Leere Saisons erzeugen keine
erfundene Kurve. Die Momentaufnahme umfasst immer aktuelle, vorherige und
vorvorherige Heizsaison in dieser Reihenfolge.

## Laufende Live-Kurve

Jeder Live-Messpunkt wird mindestens mit diesen Angaben erfasst:

- Beobachtungszeitpunkt mit Zeitzone,
- aktuelle Temperatur,
- vom Gerät gemeldete Abbrennzeit,
- Statusinformation, die für Start oder Ende der Sitzung verwendet wurde.

Der Zwischenstand wird atomisch unter `data/` gespeichert, damit ein
Prozessneustart nicht automatisch die gesamte laufende Beobachtung verliert.
Die endgültige Verzeichnis- und Schemabezeichnung wird mit dem Datenmodell
festgelegt.

Eine Live-Sitzung und ein später aus dem Ringpuffer importierter Abbrand sind
zunächst getrennte Datensätze. Eine automatische Zusammenführung benötigt
eine deterministische Zuordnungsregel und passende Tests.

## Achsengrenze

Historische Kurven verwenden `sample_index`. Live-Messpunkte entstehen im
adaptiven Polling mit eigenen Zeitstempeln. Diese Achsen sind nicht
automatisch gleichwertig.

Bis ein echter Abbrand gleichzeitig live aufgezeichnet und anschließend aus
dem Ringpuffer gelesen wurde, gilt:

- kein stilles Gleichsetzen beider Indizes,
- keine Bezeichnung des historischen Messpunkts als Minute,
- keine Aufheiz- oder Abkühlrate in Grad Celsius pro Minute,
- keine klassifizierte Live-Abweichung auf unbestätigter Achse,
- Ergebnis `noch nicht bewertbar`, wenn keine verlässliche Ausrichtung
  möglich ist.

Der spätere Praxistest muss Live-Zeitstempel, Geräte-Abbrennzeit und den
resultierenden Archivverlauf gemeinsam auswerten.

## Neutrale Ergebnisbegriffe

Zulässige Einordnungen sind:

- `typisch`,
- `auffällig`,
- `deutlich abweichend`,
- `noch nicht bewertbar`.

Grenzwerte müssen transparent, getestet und konfigurierbar sein. Ohne solche
Grenzwerte werden ausschließlich numerische Abweichungen veröffentlicht.

Nicht zulässig sind unbelegte Aussagen wie:

- gesund oder ungesund,
- sicher oder unsicher,
- optimal,
- guter, schlechter oder bester Abbrand.

Ein späteres konfiguriertes Zielprofil muss seine Einzelkriterien, Gewichte
und Teilwerte offenlegen und darf nicht als objektive Wahrheit dargestellt
werden.

## Home Assistant und MQTT

Der historische Vergleich bleibt eine retained Entität ohne Live-
Availability. Dadurch bleibt die letzte vollständige Auswertung während einer
Sommerabschaltung sichtbar.

Die laufende Kurve wird als getrennte Live-Entität veröffentlicht. Sie
verwendet Live-Availability und eine Ablaufzeit, damit eine alte laufende
Kurve nicht als aktueller Kaminzustand erscheint.

Vollständige historische Einzelkurven werden weiterhin nicht als unbegrenzt
wachsende Entity-Attribute veröffentlicht. Payload-Größe und Anzahl der
Dashboardreihen bleiben begrenzt und automatisiert getestet.

## Abnahmekriterien

Die Funktion gilt automatisiert als vorbereitet, wenn:

- Median und Referenzauswahl deterministisch getestet sind,
- ungültige und nicht vergleichbare Kurven ausgeschlossen werden,
- leere oder zu kleine Referenzgruppen `noch nicht bewertbar` ergeben,
- Zwischenstände atomisch gespeichert und nach Neustart geladen werden,
- MQTT-Ausfall die lokale Erfassung nicht verhindert,
- Payload-Grenzen und Availability-Regeln getestet sind.

Die Live-Bewertung gilt erst praktisch als bestätigt, wenn in der Heizperiode:

1. ein echter Abbrand live aufgezeichnet wurde,
2. genau ein zugehöriger neuer Archivdatensatz entstand,
3. ein zweiter Ringpufferlauf kein Duplikat erzeugte,
4. Live- und Archivachse nachvollziehbar zugeordnet wurden.
