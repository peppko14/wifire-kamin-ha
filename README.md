# WiFire-Kamin Home Assistant Bridge

> Eine rein **lesende MQTT-Bridge** für die FireControls
> WiFire-Kaminsteuerung zur Integration in Home Assistant.

## Projektziel

Dieses Projekt ermöglicht die Einbindung einer **FireControls
WiFire**-Kaminsteuerung in Home Assistant.

Der Schwerpunkt liegt auf:

-   Live-Daten per MQTT
-   automatischer Home-Assistant-Discovery
-   Archivierung historischer Abbrände
-   langfristiger Historisierung
-   statistischer Auswertung
-   Reverse Engineering des WiFire-Protokolls

Das Projekt ist **kein Ersatz für die originale FireControls-App** und
verändert **keine Einstellungen** der Kaminsteuerung.

------------------------------------------------------------------------

# Funktionen

-   MQTT-Bridge für Home Assistant
-   MQTT Discovery
-   Temperatur, Türstatus, Luftklappenstellung und Restlaufzeit
-   Dynamische Abfrageintervalle
    -   10 Sekunden während eines Abbrands
    -   60 Sekunden im Normalbetrieb
    -   5 Minuten bei Kommunikationsfehlern
-   Archivauslese
-   Import historischer Abbrände
-   Reverse-Engineering-Werkzeuge
-   Portabler systemd-Installer

------------------------------------------------------------------------

# Unterstützte Hardware

## Raspberry Pi

Entwickelt und getestet mit:

-   Raspberry Pi 3 Model B+

Andere Raspberry-Pi-Modelle sollten grundsätzlich funktionieren, wurden
bisher jedoch nicht getestet.

## Kaminsteuerung

Unterstützt:

-   FireControls **WiFire**

Nicht unterstützt:

-   FireControls **WiFire NET**
-   FireControls **WiFire H2O** (wassergeführte Kaminsteuerung)

------------------------------------------------------------------------

# Projektumfang

Das Projekt stellt ausschließlich **lesende Funktionen** bereit.

Es können unter anderem folgende Informationen ausgelesen werden:

-   aktuelle Temperatur
-   Türstatus
-   Luftklappenstellung
-   Restlaufzeit
-   archivierte Abbrände
-   Temperaturverläufe

Es werden **keine Daten zur Kaminsteuerung zurückgeschrieben**.

------------------------------------------------------------------------

# Nicht im Projektumfang (Out of Scope)

Bewusst nicht vorgesehen sind:

-   Ändern von Einstellungen der Kaminsteuerung
-   Schließzeitverzögerung ändern
-   Anpassung der Abbrandparameter
-   Firmware-Updates
-   sonstige Schreibzugriffe

Für Konfiguration und Parametrierung ist weiterhin die originale
FireControls-App vorgesehen.

------------------------------------------------------------------------

# Bekannte Einschränkungen

Die FireControls WiFire unterstützt optionale Zusatzfunktionen.

Folgende Funktion konnte bisher nicht getestet werden:

-   Lüftersteuerung (z. B. Abluftsteuerung für ein Kochfeld)

Da diese Hardware an meiner Anlage nicht vorhanden ist, kann hierfür
derzeit keine Unterstützung zugesichert werden.

------------------------------------------------------------------------

# Projektstruktur

``` text
wifire-kamin-ha/
├── docs/
├── systemd/
├── tools/
├── data/
├── mqtt_discovery.py
├── wifire_protocol.py
├── version.py
├── config.example.py
├── VERSION
├── CHANGELOG.md
└── README.md
```

------------------------------------------------------------------------

# Installation

Repository klonen:

``` bash
git clone <repository-url>
cd wifire-kamin-ha
```

Virtuelle Umgebung erstellen:

``` bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Konfiguration anlegen:

``` bash
cp config.example.py config.py
```

`config.py` an die eigene Umgebung anpassen.

## systemd installieren

``` bash
chmod +x systemd/install_service_v0.5.1.sh
sudo systemd/install_service_v0.5.1.sh
```

Der Installer erkennt automatisch:

-   Linux-Benutzer
-   Projektpfad
-   Python-Interpreter
-   virtuelle Umgebung

------------------------------------------------------------------------

# Home Assistant

Die MQTT-Discovery erzeugt automatisch das Gerät **WiFire-Kamin**.

Bereitgestellt werden unter anderem:

-   Temperatur
-   Luftklappenstellung
-   Türstatus
-   Restlaufzeit
-   Diagnoseinformationen

------------------------------------------------------------------------

# Werkzeuge

## Reverse Engineering

``` bash
python3 tools/reverse_engineering_suite_v1.0.0.py
```

## Archiv-Mapper

``` bash
python3 tools/archive_mapper_v1.0.0.py
```

## Endpunkt-Scanner

``` bash
python3 tools/endpoint_scanner_v1.0.0.py
```

## Archiv-Importer

``` bash
python3 tools/archive_importer_v1.0.0.py
```

------------------------------------------------------------------------

# Saisonbetrieb

Empfohlener Betrieb:

-   Oktober bis April: Raspberry Pi eingeschaltet
-   Mai bis September: Raspberry sauber herunterfahren oder stromlos
    schalten

------------------------------------------------------------------------

# Roadmap

-   Dauerhafte lokale Historienverwaltung
-   Automatische Sicherung neuer Abbrände
-   Statistikfunktionen
-   Lovelace-Dashboard

------------------------------------------------------------------------

# Lizenz

Die Lizenz wird mit einem zukünftigen Release ergänzt.

------------------------------------------------------------------------

# Haftungsausschluss

Dieses Projekt ist ein privates Hobbyprojekt und steht in keiner
Verbindung zur FireControls GmbH.

Alle genannten Marken- und Produktnamen sind Eigentum ihrer jeweiligen
Inhaber.
