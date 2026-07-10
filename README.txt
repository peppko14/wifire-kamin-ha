WiFire-Kamin MQTT Bridge 0.2.0
================================

Diese Version verwendet Home Assistants empfohlene MQTT-Geräte-Discovery:
  homeassistant/device/wifire_kamin/config

Ein Eintrag in configuration.yaml ist nicht erforderlich.

INSTALLATION
------------
1. Laufendes Skript mit Strg+C stoppen.
2. config.py, decoder.py, mqtt_discovery.py und requirements.txt nach
   /home/dennis-wifire/wifire-reader kopieren und vorhandene Dateien ersetzen.
3. MQTT-Zugangsdaten in config.py kontrollieren.
4. Ausführen:

   cd ~/wifire-reader
   source venv/bin/activate
   pip install -r requirements.txt
   python3 mqtt_discovery.py

Erwartete Ausgabe:
  Mit MQTT verbunden.
  Home-Assistant-Geräte-Discovery für "WiFire-Kamin" veröffentlicht.

Discovery prüfen:
  mosquitto_sub -h 192.168.1.99 -u 'BENUTZER' -P 'PASSWORT' \
    -t 'homeassistant/device/wifire_kamin/config' -v

Status prüfen:
  mosquitto_sub -h 192.168.1.99 -u 'BENUTZER' -P 'PASSWORT' \
    -t 'wifire_kamin/#' -v

AUTOSTART
---------
  sudo cp wifire-kamin.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now wifire-kamin.service

  sudo systemctl status wifire-kamin.service
  journalctl -u wifire-kamin.service -f

HOME ASSISTANT
--------------
Unter Einstellungen > Geräte & Dienste > MQTT sollte "WiFire-Kamin" erscheinen.
MQTT Discovery muss aktiviert sein. Standard-Präfix: homeassistant.
