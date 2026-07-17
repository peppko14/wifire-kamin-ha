# Verifiziertes WiFire-Geräteprofil

Dokumentversion: 1.1.0

Dieses Dokument beschreibt die konkrete WiFire-Variante, gegen die die
WiFire-Kamin Home Assistant Bridge entwickelt und geprüft wird. Die Angaben
stammen aus der Informations- und Einstellungsanzeige der offiziellen App.

## Referenzgerät

- Gerätefamilie: FireControls WiFire
- Heizgeräteprofil: `UNIVERSAL`
- Profilkennung: `UNI-80°C`
- WEB-Version: `w3.3.3`
- MCU-Version: `ver.37 B368`
- Firmwaredatum: November 2024
- AP-Neustartmodus der geprüften Installation: `NORMAL`

Die Profilkennung und Firmwaredaten dokumentieren die geprüfte Variante. Sie
werden nicht als universelle Eigenschaften aller WiFire-Steuerungen behandelt.

Nicht unterstützt werden:

- die modernere FireControls WiFire NET-Variante,
- WiFire H2O,
- H2O-spezifische Kessel- und Puffertemperaturen,
- die H2O-spezifische Umwälzpumpe.

## Ausschließlich lesender Betrieb

Das Projekt liest Live- und Archivdaten. Es verändert keine Einstellungen der
Steuerung. Insbesondere werden folgende App-Funktionen nicht automatisiert:

- Zeitsynchronisation,
- Schließzeitverzögerung,
- AP-Neustart,
- System- und Heizgeräteparameter.

## Abbrandphasen und Klappenpositionen

Die in der Bedienungsanleitung abgebildeten Klappenpositionen gehören zu einem
anderen Beispiel-Heizgeräteprofil. Daraus dürfen keine festen Prozentwerte für
das Profil `UNIVERSAL / UNI-80°C` abgeleitet werden.

Die bisher reverse-engineerten Archivfelder bleiben deshalb kompatibel
erhalten. Eine spätere fachliche Umbenennung setzt voraus, dass die in der App
angezeigten Phasenübergänge des Referenzprofils kontrolliert mit den Bytes eines
realen Archivtelegramms verglichen wurden.

## Abbranddauer und Schließzeitverzögerung

Die Bedienungsanleitung definiert die Brenndauer als Zeitraum vom Anzünden bis
zum Übergang in die fünfte Abbrandstufe S5. In der geprüften Installation ist
eine Schließzeitverzögerung von 60 Minuten eingestellt.

Die gespeicherte S5-/0-%-Phasenmarke ist daher der fachliche Endpunkt des
aktiven Abbrands. Sie beweist nicht ohne zusätzliche Protokollprüfung den
Zeitpunkt, zu dem die Luftklappe mechanisch vollständig geschlossen ist. Eine
konfigurierte Verzögerung kann den tatsächlichen Klappenschluss hinausschieben.

Die Schließzeitverzögerung ist eine installationsabhängige Einstellung. Der
Wert von 60 Minuten wird weder im Decoder fest codiert noch automatisch an die
Steuerung zurückgeschrieben.

## Steuerungszeit

Archiv- und Alarmzeitpunkte stammen von der internen Steuerungsuhr. Diese Uhr
kann nach einem Stromausfall oder bei fehlender Synchronisation von der
Raspberry- beziehungsweise Handyzeit abweichen. Eine Zeitabweichung verändert
nicht die Temperaturkurve, kann aber den gespeicherten Startzeitpunkt
verschieben.

Für die geprüfte Installation wurde bestätigt, dass die Zeitsynchronisation
für die alten Einträge nicht durchgeführt wurde. Die Archiv- und Alarmliste
teilen deshalb zwar dieselbe interne Zeitbasis, belegen aber nicht, dass die
angezeigten Kalenderdaten aus 2017 real sind. Die zugehörigen Temperaturkurven
bleiben fachlich nutzbar; ihre zeitliche Zuordnung bleibt mit
`timestamp_uncertain` gekennzeichnet.

Die Bridge synchronisiert die Steuerungszeit nicht. Eine Synchronisation darf
nur bewusst über die offizielle App erfolgen. Die nachfolgend dokumentierte
Diagnose liest die interne Uhr lediglich zur Plausibilitätsprüfung aus.

## Verifizierte Diagnoseendpunkte

Ein PCAP-Mitschnitt der offiziellen App gegen das Referenzgerät bestätigt zwei
ausschließlich lesende HTTP-GET-Endpunkte:

- `/direct/22` liefert die interne Steuerungszeit,
- `/direct/04` liefert mehrere Alarmblöcke; der letzte Block enthält die zehn
  in der App sichtbaren Heizfehler-Plätze.

Die Antwort von `/direct/22` enthält Jahr, Monat, Tag, Stunde und Minute. Das
Monatsbyte besitzt zusätzliche, noch nicht vollständig benannte Bits; für den
Kalendermonat werden nur die unteren vier Bits verwendet. Im Mitschnitt vom
17. Juli 2026 folgten zwei Antworten mit 12:57 und 12:58 aufeinander. Gegenüber
der Aufnahmezeit des Handys lag die interne Steuerungsuhr rund 51 Minuten
zurück. Damit ist die zuvor dokumentierte mögliche Zeitabweichung praktisch
bestätigt.

Die Antwort von `/direct/04` enthält sieben Blöcke zu je zehn sechs Byte langen
Datensätzen. Nur die letzten 60 Nutzbytes stimmen vollständig mit den zehn in
der App sichtbaren Einträgen überein. Für diesen Block sind Datum und Alarmcode
`1` eindeutig mit der App-Anzeige `Heizfehler` abgeglichen. Zwei andere Blöcke
enthalten wiederholte Werte, die auf der geprüften App-Seite nicht angezeigt
werden. Sie werden deshalb nicht als reale Alarme interpretiert. Weitere Bytes
und bisher nicht beobachtete Alarmcodes bleiben neutrale Rohwerte.

Das versionierte Werkzeug

```bash
python3 tools/device_diagnostics_v1_0_0.py
```

liest beide Endpunkte ohne schreibende Nutzlast. Mit `--json` ist eine
maschinenlesbare Ausgabe möglich. Der PCAP-Mitschnitt selbst enthält private
Geräte- und Zeitdaten und gehört nicht in Git.

Ein realer Diagnoselauf am 17. Juli 2026 bestätigte alle zehn in der App
sichtbaren Heizfehler einschließlich Reihenfolge und doppelter Tageswerte. Die
Steuerungszeit betrug 13:28 bei einer Raspberry-Zeit von 14:19:26 und lag damit
rund 51,4 Minuten zurück. Der erste Zugriff auf `/direct/04` wurde vom Gerät
ohne Antwort geschlossen; der begrenzte zweite Versuch war erfolgreich. Damit
ist auch das Retry-Verhalten gegen einen typischen kurzen WiFire-Aussetzer am
Referenzgerät praktisch bestätigt.

## Home-Assistant-Diagnose

Die Bridge aktualisiert die verifizierten Diagnosewerte gemeinsam mit dem
seltenen Archivzyklus. Damit werden keine häufigen zusätzlichen Abfragen an
das schwache WiFire-Webmodul gestellt. Zwischen `/direct/22` und `/direct/04`
liegt außerdem eine kurze konfigurierbare Pause.

Home Assistant erhält vier Diagnoseentitäten:

- `Steuerungszeit`,
- `Zeitabweichung Steuerung`,
- `Letzter Heizfehler`,
- `Gespeicherte Heizfehler`.

Die Zeitabweichung ist `Steuerungszeit minus Raspberry-Zeit` in Minuten. Ein
negativer Wert bedeutet somit, dass die Steuerungsuhr zurückliegt. Die Liste
der sichtbaren Heizfehler wird als Attribute der Entität `Letzter Heizfehler`
mitgegeben. Unbekannte Rohbytes werden nicht an Home Assistant veröffentlicht.

Beide Diagnose-Payloads werden retained und bewusst nicht an die
Live-Verfügbarkeit oder `expire_after` gebunden. Die zuletzt erfolgreich
gelesenen Werte bleiben daher sichtbar, wenn der Raspberry saisonal
ausgeschaltet ist oder eine spätere Diagnoseabfrage fehlschlägt. Uhr und
Heizfehler werden unabhängig behandelt: Der Fehler eines Endpunkts löscht oder
blockiert nicht den zuletzt gültigen Wert des anderen Endpunkts.

Zusätzlich beobachtet wurden `/direct/24`, `/direct/36` und `/direct/37`.
Teilwerte passen zu Firmware-, Profil- und Herstellerinformationen. Ihre
vollständige Bytebedeutung ist noch nicht reproduzierbar belegt. Insbesondere
wird aus den mehrfach vorkommenden Werten `0x3c` in `/direct/36` nicht
vorschnell eine Schließzeitverzögerung abgeleitet.

## Diagnoseinformationen

Die App besitzt eine Alarmliste sowie getrennte Symbole für Rauchgassauger und
Dunstabzugshaube. Steuerungszeit und sichtbare Heizfehler wurden manuell gegen
App und Diagnosewerkzeug abgeglichen und werden als Home-Assistant-Entitäten
angeboten. Rauchgassauger und Dunstabzugshaube sind weiterhin nicht eindeutig
zugeordnet. Der heutige Rohwert `fan_raw` wird bis dahin nicht fachlich
umbenannt.
