# Verifiziertes WiFire-Geräteprofil

Dokumentversion: 1.0.0

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

Die Bridge synchronisiert die Steuerungszeit nicht. Eine Synchronisation darf
nur bewusst über die offizielle App erfolgen. Eine spätere rein lesende
Plausibilitätsprüfung benötigt zunächst den zugehörigen Leseaufruf der App.

## Diagnoseinformationen

Die App besitzt eine Alarmliste sowie getrennte Symbole für Rauchgassauger und
Dunstabzugshaube. Diese Informationen werden erst dann als Home-Assistant-
Entitäten angeboten, wenn die jeweiligen Leseantworten eindeutig ermittelt und
mit reproduzierbaren Tests abgesichert wurden. Der heutige Rohwert `fan_raw`
wird bis dahin nicht fachlich umbenannt.
