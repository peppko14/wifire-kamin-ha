# Home-Assistant-Dashboard für Brennkurven

Dokumentversion: 1.3.0

## Datenquelle

Die Bridge veröffentlicht nach jeder seltenen Ringpuffer-Synchronisation eine
retained Momentaufnahme unter:

```text
wifire_kamin/<device_id>/dashboard_curves
```

MQTT Discovery erzeugt daraus genau eine Diagnoseentität
`Brennkurven-Vergleich`. Ihr Zustand ist der Erstellungszeitpunkt. Ihre
Attribute nach Schema 2 enthalten:

- die Durchschnittskurve,
- den repräsentativen realen Abbrand,
- den heißesten realen Abbrand,
- den letzten abgeschlossenen Abbrand,
- die historische Mediankurve und ihren realen Referenzabbrand,
- Status, Größe und Abweichung des historischen Vergleichs,
- Mediankurven der aktuellen und zwei vorherigen Heizsaisons.

Bei einer zu kleinen Referenzgruppe bleibt der Zustand `not_evaluable`
sichtbar. In diesem Fall wird keine Mediankurve erfunden.

Jede Reihe verwendet ein kompaktes Temperaturarray. Die Achse ist
`sample_index`; sie wird nicht ohne Protokollnachweis als Minute bezeichnet.
Der gesamte Payload ist auf 16 KiB begrenzt. Die vollständigen historischen
Einzelkurven bleiben ausschließlich in der lokalen Historie und im portablen
JSON-Export.

## Betrieb bei ausgeschaltetem Raspberry

Die Dashboard-Momentaufnahme wird retained beim MQTT-Broker gespeichert und
ist nicht an den Online-Status der Bridge gebunden. Sie bleibt deshalb in
Home Assistant verfügbar, bis die Bridge eine neue Momentaufnahme
veröffentlicht. Das gilt ebenso für Archive, historische Gesamtstatistiken,
Monatswerte und die drei Heizsaisons.

Temperatur, Luftklappe, Tür, Abbrenndauer und der optionale Lüfter bleiben
dagegen Live-Entitäten. Sie werden bei beendeter Bridge oder ausgeschaltetem
Raspberry bewusst als nicht verfügbar angezeigt, damit alte Messwerte nicht
als aktueller Kaminzustand erscheinen.

Das gilt ebenso für die getrennte Entität `Laufende Brennkurve`. Ihr
nicht-retained Zustand verwendet Live-Verfügbarkeit und Ablaufzeit. Die
vollständige Sitzung bleibt lokal gespeichert; die Home-Assistant-Darstellung
ist auf höchstens 121 gleichmäßig ausgewählte Messpunkte begrenzt.

Für eine mehrmonatige Sommerpause kann der Raspberry nach einer letzten
erfolgreichen Veröffentlichung ausgeschaltet werden. Home Assistant und der
MQTT-Broker müssen weiterlaufen. Nach einem Home-Assistant- oder Broker-
Neustart werden Discovery und Zustände aus den retained MQTT-Nachrichten
wiederhergestellt.

Nach dem Upgrade auf Version 0.12.2 muss die Bridge einmal mit dem
MQTT-Broker verbunden werden, damit sie die aktualisierte Discovery-
Konfiguration retained veröffentlicht. Danach kann sie wieder beendet werden.

## Filter

Optional kann in der privaten `config.py` ein eigener Zeitraum gesetzt werden:

```python
DASHBOARD_CURVES_SINCE = "2026-01-01"
DASHBOARD_INCLUDE_WARNINGS = True
```

Fehlt `DASHBOARD_CURVES_SINCE`, verwendet die Bridge den bestehenden Wert von
`STATISTICS_SINCE`. `None` berücksichtigt die vollständige lokale Historie.
Ungültige Datensätze gelangen unabhängig davon nie in die Kurvenanalyse.

## Diagramm mit Plotly Graph Card

Home Assistant zeigt die Entität und ihre Attribute ohne zusätzliche
Konfiguration an. Für das interaktive Liniendiagramm wird optional die
[Plotly Graph Card](https://github.com/dbuezas/lovelace-plotly-graph-card)
verwendet. Das Projekt empfiehlt die Installation über HACS.

Die tatsächliche Entitäts-ID wird unter **Einstellungen → Geräte & Dienste →
MQTT → WiFire-Kamin** geprüft. Falls sie abweicht, muss sie im folgenden
Beispiel in allen Vorkommen ersetzt werden.

```yaml
type: custom:plotly-graph
title: WiFire-Kamin Brennkurven
refresh_interval: auto
raw_plotly_config: true
entities:
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Historischer Median
    mode: lines
    line:
      width: 4
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.series?.median?.temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.series?.median?.temperatures_c ?? []
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Letzter Abbrand
    mode: lines
    line:
      width: 3
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.series?.latest?.temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.series?.latest?.temperatures_c ?? []
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Vorherige Heizsaison
    mode: lines
    line:
      width: 2
      dash: dash
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.heating_seasons?.[1]
          ?.median_temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.heating_seasons?.[1]?.median_temperatures_c ?? []
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Durchschnitt
    mode: lines
    line:
      width: 4
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.series?.average?.temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.series?.average?.temperatures_c ?? []
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Repräsentativer Abbrand
    mode: lines
    line:
      width: 2
      dash: dot
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.series?.representative?.temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.series?.representative?.temperatures_c ?? []
  - entity: sensor.wifire_kamin_brennkurven_vergleich
    name: Heißester Abbrand
    mode: lines
    line:
      width: 2
      dash: dash
    x: |
      $fn ({hass}) => {
        const values = hass.states[
          "sensor.wifire_kamin_brennkurven_vergleich"
        ]?.attributes?.series?.hottest?.temperatures_c ?? [];
        return values.map((_, index) => index);
      }
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_brennkurven_vergleich"
      ]?.attributes?.series?.hottest?.temperatures_c ?? []
layout:
  height: 420
  margin:
    l: 55
    r: 20
    t: 45
    b: 55
  xaxis:
    title:
      text: Messpunkt
  yaxis:
    title:
      text: Temperatur °C
config:
  displaylogo: false
  scrollZoom: true
```

Die Karte liest nur den aktuellen retained MQTT-Zustand. Sie erzeugt keine
zusätzlichen WiFire-Abfragen und verändert keine Daten am Kamin.

## Getrenntes Diagramm der laufenden Brennkurve

Die Live-Kurve besitzt echte Zeitzonen-Zeitstempel und wird deshalb nicht
stillschweigend mit dem historischen `sample_index` auf dieselbe X-Achse
gelegt. Eine separate Plotly-Karte kann sie so darstellen:

```yaml
type: custom:plotly-graph
title: WiFire-Kamin laufende Brennkurve
refresh_interval: auto
raw_plotly_config: true
entities:
  - entity: sensor.wifire_kamin_live_curve
    name: Laufender Abbrand
    mode: lines
    line:
      width: 4
    x: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_live_curve"
      ]?.attributes?.observed_at ?? []
    y: |
      $fn ({hass}) => hass.states[
        "sensor.wifire_kamin_live_curve"
      ]?.attributes?.temperatures_c ?? []
layout:
  height: 360
  xaxis:
    title:
      text: Beobachtungszeit
  yaxis:
    title:
      text: Temperatur °C
config:
  displaylogo: false
  scrollZoom: true
```

Der Zustand der Entität lautet `active` oder `inactive`. Eine automatische
Einordnung als typisch oder auffällig erfolgt vor der praktischen
Verifizierung der Live-/Archivachsen bewusst noch nicht.
