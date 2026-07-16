# Digitale Brennkurven

Dokumentversion: 1.1.0

Die lokale Schema-2-Historie enthält den vollständigen Temperaturverlauf
jeder abgeschlossenen Verbrennung. Seit Version 0.12.0 stellt die Bridge
daraus portable, reproduzierbare Kurven, historische Referenzen und eine
retained Home-Assistant-Momentaufnahme bereit.

## Messpunktachse

Die Achse heißt ausdrücklich `sample_index`. Sie beginnt bei 0 und ist für
jede Kurve lückenlos. Das Projekt bezeichnet einen Messpunkt nicht als
Minute, solange das tatsächliche Messintervall der Gerätefirmware nicht
verlässlich bestätigt ist.

Alle gemeinsam analysierten Kurven müssen gleich viele Messpunkte besitzen.
Dadurch werden Durchschnitt und Abstände nicht durch stilles Auffüllen,
Abschneiden oder eine unbestätigte zeitliche Interpolation verfälscht.

## Durchschnittskurve

Für jeden `sample_index` wird das arithmetische Mittel aller ausgewählten
Kurven berechnet und auf eine Nachkommastelle gerundet. Der Export nennt
zusätzlich die Anzahl der beitragenden Kurven.

Der Durchschnitt bleibt als bestehende beschreibende Kennzahl erhalten. Für
v0.13.0 ist zusätzlich eine punktweise Mediankurve als robustere typische
Referenz vorgesehen. Ungewöhnliche Einzelabbrände beeinflussen den Median
weniger stark.

## Repräsentativer Abbrand

Der repräsentative Abbrand ist eine tatsächlich gespeicherte Kurve. Für jede
Kurve wird die mittlere quadratische Abweichung zur Durchschnittskurve als
RMSE in Grad Celsius berechnet. Die Kurve mit dem kleinsten RMSE wird als
`representative_curve` ausgegeben.

Bei gleichem Abstand entscheidet zuerst der frühere Startzeitpunkt und danach
die stabile `burn_id`. Das Ergebnis ist dadurch reproduzierbar.

## Heißester Abbrand

Die Kurve mit der höchsten Einzeltemperatur wird getrennt als
`hottest_curve` ausgegeben. Sie wird ausdrücklich nicht als bester oder
gesündester Abbrand bewertet. Bei gleicher Höchsttemperatur wird der frühere
Abbrand verwendet.

## Export erstellen

```bash
python3 tools/burn_curve_export_v1_0_0.py
```

Standardziel:

```text
data/exports/burn-curves.json
```

Vorhandene Dateien werden nicht automatisch überschrieben. Für eine bewusst
aktualisierte Datei:

```bash
python3 tools/burn_curve_export_v1_0_0.py --overwrite
```

Optionale Filter:

```bash
python3 tools/burn_curve_export_v1_0_0.py \
  --since 2026-01-01 \
  --exclude-warnings \
  --overwrite
```

Der Export enthält:

- Schema-Version und Erstellungszeit,
- verwendete Filter,
- Durchschnittskurve,
- repräsentative reale Kurve inklusive RMSE,
- heißeste reale Kurve,
- sämtliche berücksichtigten Einzelkurven mit vollständiger `burn_id`,
  Qualitätsstatus und Temperaturpunkten.

Die Datei liegt unter `data/` und wird nicht in Git aufgenommen.

## Home Assistant

Die Bridge veröffentlicht Durchschnitt, repräsentativen realen Abbrand und
heißesten Abbrand als eine kompakte retained Diagnoseentität. Ein
Plotly-Beispiel steht in
[`home-assistant-dashboard.md`](home-assistant-dashboard.md). Die Werte bleiben
auch bei ausgeschaltetem Raspberry verfügbar, solange MQTT-Broker und Home
Assistant weiterlaufen.

## Geplanter Live-Vergleich

Version 0.13.0 erweitert die Analyse um Medianreferenzen, saisonale Gruppen,
den letzten abgeschlossenen Abbrand und eine getrennte laufende Live-Kurve.
Die Live-Reihe besitzt eigene Beobachtungszeitpunkte und darf nicht
stillschweigend mit dem historischen `sample_index` gleichgesetzt werden.
Details und Freigaberegeln stehen in
[`live-curve-comparison.md`](live-curve-comparison.md).
