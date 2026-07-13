# History identifiers v1.0.0

Enthalten:

- `history/__init__.py`
- `history/identifiers.py`
- `tests/test_history_identifiers.py`

Die Abbrand-ID ist ein SHA-256-Hash aus:

- Startzeit
- Anzahl der Temperaturwerte
- vollständiger Temperaturkurve

Die WiFire-Archivnummer wird bewusst nicht einbezogen.
