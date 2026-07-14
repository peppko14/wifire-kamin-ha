# Betriebsdiagnose

Dokumentversion: 1.0.0

Das Diagnosewerkzeug prüft den Betriebszustand der WiFire-Kamin-Bridge nur
lesend. Es verändert weder Dateien noch Konfiguration oder Dienstzustand und
gibt keine Zugangsdaten aus.

## Vollständige Prüfung

```bash
python3 tools/system_diagnostics_v1_0_0.py
```

Geprüft werden:

- Python-Mindestversion,
- öffentliche Konfigurationsparameter,
- freier Speicherplatz,
- Lesbarkeit von Historie und Diagnoseablage,
- Vorhandensein, Alter und Integrität des neuesten Backups,
- HTTP-Lesetest des WiFire-Live-Endpunkts,
- TCP-Erreichbarkeit des MQTT-Brokers,
- Status von `wifire-kamin.service`.

Die MQTT-Prüfung öffnet nur eine TCP-Verbindung. Benutzername und Passwort
werden dabei weder übertragen noch protokolliert; die erfolgreiche Anmeldung
wird daher ausdrücklich nicht bestätigt.

## Offline-Prüfung

Ohne Netzwerkzugriff auf Kamin und Broker:

```bash
python3 tools/system_diagnostics_v1_0_0.py \
  --offline \
  --skip-service
```

Diese Variante eignet sich für Tests bei ausgeschaltetem Dienst oder nicht
erreichbarem Kamin. Übersprungene Prüfungen werden im Bericht gekennzeichnet.

## JSON-Ausgabe

```bash
python3 tools/system_diagnostics_v1_0_0.py --json
```

Der Exit-Code ist 1, sobald mindestens eine Prüfung einen Fehler meldet.
Warnungen, beispielsweise ein bewusst gestoppter Dienst oder ein älteres
Backup, führen weiterhin zu Exit-Code 0.

Das Werkzeug startet oder stoppt den Dienst niemals selbstständig.
