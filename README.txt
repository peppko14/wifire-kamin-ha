WiFire-Kamin MQTT Bridge
========================

Diese Version verwendet Home Assistants empfohlene MQTT-Geräte-Discovery:
  homeassistant/device/wifire_kamin/config

Ein Eintrag in configuration.yaml ist nicht erforderlich.

BENÖTIGTE DATEIEN
------------------
Für den Betrieb der MQTT-Bridge werden folgende Dateien benötigt:

  config.py             (aus config.example.py erstellen, siehe unten)
  decoder.py
  wifire_protocol.py     <-- wird von mqtt_discovery.py importiert,
                              ohne diese Datei startet der Dienst NICHT
  mqtt_discovery.py
  requirements.txt

Optional (nur für Protokoll-Analyse, nicht für den Regelbetrieb nötig):

  archive_reader.py
  tools/                 (Reverse-Engineering-Werkzeuge, siehe docs/)
  docs/reverse_engineering.md

INSTALLATION
------------
1. Laufendes Skript bzw. laufenden Dienst stoppen:
   sudo systemctl stop wifire-kamin.service
   (oder Strg+C, falls manuell im Vordergrund gestartet)

2. Alle Dateien aus "BENÖTIGTE DATEIEN" oben nach
   /home/dennis-wifire/wifire-reader kopieren und vorhandene Dateien
   ersetzen. Wichtig: wifire_protocol.py nicht vergessen.

3. Falls noch nicht vorhanden: config.example.py nach config.py
   kopieren und anpassen:

   cp config.example.py config.py

4. MQTT-Zugangsdaten und WIFIRE_URL in config.py kontrollieren.
   Empfehlung: Dateirechte einschränken, da dort Zugangsdaten im
   Klartext stehen:

   chmod 600 config.py

5. Ausführen:

   cd ~/wifire-reader
   source venv/bin/activate
   pip install -r requirements.txt
   python3 mqtt_discovery.py

Erwartete Ausgabe:
  Verbinde mit MQTT-Broker ...
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
Unter Einstellungen > Geräte & Dienste > MQTT sollte "WiFire-Kamin"
erscheinen. MQTT Discovery muss aktiviert sein. Standard-Präfix:
homeassistant.

PROTOKOLL-ANALYSE (OPTIONAL)
-----------------------------
Für Reverse-Engineering des lesenden HTTP-Protokolls siehe
docs/reverse_engineering.md. Die dortigen Werkzeuge unter tools/
verändern keine Kaminparameter und werden für den normalen Betrieb
der MQTT-Bridge nicht benötigt.

VERSION
-------
Die aktuelle Version steht in der Datei VERSION im Projekt-Root.
