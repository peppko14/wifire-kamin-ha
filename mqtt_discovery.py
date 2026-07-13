#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Programmeinstieg der WiFire-Kamin MQTT Bridge."""

from __future__ import annotations

from pathlib import Path

import config

from bridge.application import create_application
from version import APP_VERSION


APP_NAME = "WiFire-Kamin MQTT Bridge"


def main() -> None:
    """Erzeugt und startet die Bridge-Anwendung."""
    application = create_application(
        config,
        project_dir=Path(__file__).resolve().parent,
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )
    application.run()


if __name__ == "__main__":
    main()
