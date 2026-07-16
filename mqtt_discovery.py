#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Programmeinstieg der WiFire-Kamin MQTT Bridge."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType

from version import APP_VERSION


APP_NAME = "WiFire-Kamin MQTT Bridge"
CONFIG_SETUP_MESSAGE = """\
Private Konfiguration fehlt: config.py

Bitte im Projektverzeichnis ausführen:
  cp config.example.py config.py
  chmod 600 config.py
  nano config.py

Danach MQTT-Adresse und Zugangsdaten in config.py eintragen.
"""


def load_config() -> ModuleType | None:
    """Lädt die private Konfiguration oder erklärt deren Ersteinrichtung."""
    try:
        return import_module("config")
    except ModuleNotFoundError as error:
        if error.name != "config":
            raise

        print(CONFIG_SETUP_MESSAGE, file=sys.stderr, end="")
        return None


def main() -> int:
    """Erzeugt und startet die Bridge-Anwendung."""
    config = load_config()
    if config is None:
        return 2

    # Erst nach erfolgreicher Konfiguration importieren: decoder.py benötigt
    # dieselben privaten Verbindungsparameter bereits beim Modulimport.
    from bridge.application import create_application

    application = create_application(
        config,
        project_dir=Path(__file__).resolve().parent,
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
