# Home-Assistant-Dashboard für Brennkurven

Dokumentversion: 1.0.0

## Datenquelle

Die Bridge veröffentlicht nach jeder seltenen Ringpuffer-Synchronisation eine
retained Momentaufnahme unter:

```text
wifire_kamin/<device_id>/dashboard_curves
```

MQTT Discovery erzeugt daraus genau eine Diagnoseentität
`Brennkurven-Vergleich`. Ihr Zustand ist der Erstellungszeitpunkt. Ihre
Attribute enthalten ausschließlich:

- die Durchschnittskurve,
- den repräsentativen realen Abbrand,
- den heißesten realen Abbrand.

Jede Reihe verwendet ein kompaktes Temperaturarray. Die Achse ist
`sample_index`; sie wird nicht ohne Protokollnachweis als Minute bezeichnet.
Der gesamte Payload ist auf 16 KiB begrenzt. Die vollständigen historischen
Einzelkurven bleiben ausschließlich in der lokalen Historie und im portablen
JSON-Export.

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
