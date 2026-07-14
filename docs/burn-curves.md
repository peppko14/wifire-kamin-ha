# Digitale Brennkurven

Dokumentversion: 1.0.0

Die lokale Schema-2-Historie enthält den vollständigen Temperaturverlauf
jeder abgeschlossenen Verbrennung. Version 0.11.0 stellt daraus portable,
reproduzierbare Kurven und historische Referenzen bereit.

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

Die Datei liegt unter `data/` und wird nicht in Git aufgenommen. Sie ist die
Datengrundlage für ein späteres Home-Assistant-Dashboard; v0.11.0 erzeugt
noch keine Lovelace-Karten und vergleicht keine laufende Live-Kurve.
