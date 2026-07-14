# Historien-Backup und Wiederherstellung

Dokumentversion: 1.0.0

Das Backup umfasst die reguläre Historie aus `data/history/` und die
Diagnoseablage aus `data/history-incomplete/`. Die ZIP-Datei enthält alle
JSON-Dateien unverändert sowie ein Manifest mit Dateigröße und vollständiger
SHA-256-Prüfsumme.

## Backup erstellen

```bash
python3 tools/history_backup_v1_0_0.py create
```

Das Standardziel liegt unter `data/backups/`. Nach dem Schreiben wird das
Backup automatisch vollständig geprüft. Ein bestehender Zielpfad wird nur
mit der ausdrücklich angegebenen Option `--overwrite` ersetzt.

Ein eigener Zielpfad kann angegeben werden:

```bash
python3 tools/history_backup_v1_0_0.py create \
  --output /mnt/backup/wifire-history.zip
```

Ein Backup auf derselben SD-Karte schützt nicht vor einem Ausfall der Karte.
Für eine belastbare Sicherung muss die erzeugte ZIP-Datei anschließend auf
einen anderen Datenträger oder ein anderes System kopiert werden.

## Backup später prüfen

```bash
python3 tools/history_backup_v1_0_0.py verify \
  /mnt/backup/wifire-history.zip
```

Die Prüfung kontrolliert:

- ein eindeutiges und unterstütztes Manifest,
- eine sichere interne Verzeichnisstruktur,
- Vollständigkeit ohne zusätzliche oder fehlende Dateien,
- Dateigrößen,
- SHA-256-Prüfsummen jeder Datei.

## Wiederherstellung testen

```bash
python3 tools/history_backup_v1_0_0.py restore \
  /mnt/backup/wifire-history.zip \
  --target /tmp/wifire-history-restore-test
```

Das Backup wird vor der Wiederherstellung erneut geprüft. Das Ziel darf noch
nicht existieren. Dadurch werden weder die produktive Historie noch andere
vorhandene Dateien überschrieben.

Nach einem erfolgreichen Test kann das Testverzeichnis gelöscht werden. Eine
produktive Wiederherstellung erfolgt bewusst manuell: vorhandenes `data/`
sichern oder umbenennen, das Backup in ein neues Ziel restaurieren und erst
nach einer Kontrolle an die endgültige Stelle verschieben.

Der WiFire-Kamin und der MQTT-Broker werden für alle drei Befehle nicht
benötigt.
