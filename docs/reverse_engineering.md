# Reverse Engineering

Alle Werkzeuge arbeiten ausschließlich lesend.

## Vorbereitung

```bash
sudo systemctl stop wifire-kamin.service
cd ~/wifire-reader/wifire-kamin-ha
source ~/wifire-reader/venv/bin/activate
```

## Vollständiger Scan

```bash
python3 -u tools/reverse_engineering_suite_v1.0.0.py
```

Standardumfang:

- GET `/direct/00` bis `/direct/99`
- Archivnummern `0` bis `255`
- drei Versuche pro Anfrage
- drei Sekunden Pause zwischen Anfragen

Der Lauf dauert ungefähr 18 Minuten zuzüglich Wiederholungen.

## Nur Archiv untersuchen

```bash
python3 -u tools/archive_mapper_v1.0.0.py   --max-archive 255   --delay 3
```

## Nur GET-Endpunkte untersuchen

```bash
python3 -u tools/endpoint_scanner_v1.0.0.py   --max-endpoint 99   --delay 2
```

## Dienst anschließend wieder starten

```bash
sudo systemctl start wifire-kamin.service
```

## Ergebnisdateien

Die Werkzeuge speichern Berichte unter:

```text
/home/dennis-wifire/wifire-reader/reverse-engineering/
/home/dennis-wifire/wifire-reader/archive-maps/
/home/dennis-wifire/wifire-reader/endpoint-scans/
```
