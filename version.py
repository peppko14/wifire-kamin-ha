#!/usr/bin/env python3
"""Zentrale Versionsermittlung für die WiFire-Kamin MQTT Bridge.

Liest die Projektversion aus der VERSION-Datei im Projekt-Root, damit
README, CHANGELOG und die laufende Anwendung (u. a. das MQTT-Discovery-
Payload) dieselbe, einzige Quelle der Wahrheit verwenden. Vorher stand
die Versionsnummer zusätzlich hartcodiert in mqtt_discovery.py und lief
dort aus dem Takt mit CHANGELOG.md/VERSION.
"""

from __future__ import annotations

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"
_FALLBACK_VERSION = "0.0.0-unbekannt"


def _read_version() -> str:
    try:
        content = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        # VERSION-Datei fehlt (z. B. unvollständige Installation) –
        # lieber ein klar erkennbarer Platzhalter als ein Absturz.
        return _FALLBACK_VERSION

    return content or _FALLBACK_VERSION


APP_VERSION: str = _read_version()


if __name__ == "__main__":
    print(APP_VERSION)
