# Gehärteter systemd-Dienst v0.12.4

Die Vorlagendatei enthält keine benutzerspezifischen Pfade. Der Installer
ermittelt Benutzer, Projektpfad und Python-Umgebung, rendert daraus die lokale
Unit und prüft sie vor der Installation.

## Installation

Vom Repository-Hauptordner aus:

```bash
chmod +x systemd/install_service_v0.12.4.sh
chmod +x systemd/uninstall_service_v0.12.4.sh
sudo systemd/install_service_v0.12.4.sh
```

Der Installer:

- setzt `config.py` auf Modus `600`,
- legt `data/` mit Modus `700` für den Dienstbenutzer an,
- prüft die gerenderte Unit mit `systemd-analyze verify`,
- sichert eine vorhandene Unit als
  `/etc/systemd/system/wifire-kamin.service.backup`,
- installiert und startet den gehärteten Dienst.

Das Projekt und das Betriebssystem sind für den Prozess schreibgeschützt.
Nur `<Projektpfad>/data` bleibt beschreibbar. Die Netzwerkverbindungen zum
WiFire und zum MQTT-Broker bleiben verfügbar.

## Diagnose

```bash
sudo systemd-analyze verify \
  /etc/systemd/system/wifire-kamin.service

sudo systemd-analyze security \
  wifire-kamin.service

sudo journalctl \
  -u wifire-kamin.service \
  --no-pager \
  -n 100
```

Bei einem Sandbox-bedingten Fehler nennt das Journal üblicherweise die
betroffene Schutzdirektive. Sie sollte nur vorübergehend in der installierten
Unit auskommentiert werden, um die Ursache einzugrenzen. Anschließend muss die
notwendige Ausnahme möglichst eng in der Vorlage dokumentiert werden.

## Deinstallation

```bash
sudo systemd/uninstall_service_v0.12.4.sh
```

Projektdateien, private Konfiguration und Historie werden nicht gelöscht.
