# Portabilitätsdateien v0.5.1

Diese Dateien entfernen benutzerspezifische Pfade aus dem Repository.

## Zielstruktur im Repository

```text
systemd/
├── install_service_v0.5.1.sh
├── uninstall_service_v0.5.1.sh
└── wifire-kamin.service.template
```

## Installation

Vom Repository-Hauptordner aus:

```bash
chmod +x systemd/install_service_v0.5.1.sh
chmod +x systemd/uninstall_service_v0.5.1.sh
sudo systemd/install_service_v0.5.1.sh
```

Das Installationsskript erkennt automatisch:

- den aktuellen Linux-Benutzer,
- den tatsächlichen Repository-Pfad,
- eine virtuelle Python-Umgebung im Repository oder im übergeordneten Ordner,
- andernfalls `python3`.

## Alte Service-Datei entfernen

Die bisherige Datei `wifire-kamin.service` im Repository wird anschließend gelöscht.
Die installierte Datei unter `/etc/systemd/system/` wird durch das Skript neu erzeugt.
