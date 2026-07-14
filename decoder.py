#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Nur lesender HTTP-Zugriff auf den Live-Datensatz."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from config import REQUEST_TIMEOUT, WIFIRE_URL
from protocol.live import decode_live_status


__version__ = "2.0.0"


def read_live_data() -> str:
    """Liest den hexadezimalen Live-Datensatz vom WiFire-Gerät."""
    request = Request(
        WIFIRE_URL,
        headers={
            "Accept": "application/json",
            "Connection": "close",
        },
        method="GET",
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))

    raw = result.get("raw")
    if not isinstance(raw, str):
        raise ValueError(
            "Die Antwort enthält kein gültiges Feld 'raw'."
        )
    return raw


if __name__ == "__main__":
    status = decode_live_status(read_live_data())
    print("WiFire-Kamin Livedaten")
    print("----------------------")
    print(f"Temperatur:   {status.temperature_c} °C")
    print(f"Luftklappe:   {status.flap_percent} %")
    print(f"Abbrenndauer: {status.burn_time}")
    print(f"Tür:          {status.door_state}")
