# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Dekodierung des Live-Status der WiFire-Steuerung."""

from __future__ import annotations

from protocol.models import LiveStatus




PACKET_HEADER = bytes.fromhex("aacc3355")
LIVE_MIN_LENGTH = 19


def decode_live_status(raw: str) -> LiveStatus:
    """Dekodiert einen hexadezimalen Live-Datensatz."""
    try:
        data = bytes.fromhex(raw)
    except ValueError as error:
        raise ValueError("Ungültiger Hex-Datensatz.") from error

    if len(data) < LIVE_MIN_LENGTH:
        raise ValueError(
            f"Live-Datensatz zu kurz: {len(data)} Bytes."
        )
    if data[:4] != PACKET_HEADER:
        raise ValueError("Unbekannter Paketkopf.")

    door_open = bool(data[6] & 0x10)
    temperature_c = int.from_bytes(
        data[7:9],
        byteorder="big",
        signed=False,
    )
    flap_raw = data[9]

    if flap_raw > 100:
        flap_percent = max(0, min(100, flap_raw - 150))
        flap_moving = True
    else:
        flap_percent = flap_raw
        flap_moving = False

    burn_hours = data[10]
    burn_minutes = data[11]

    return LiveStatus(
        temperature_c=temperature_c,
        flap_percent=flap_percent,
        flap_moving=flap_moving,
        burn_hours=burn_hours,
        burn_minutes=burn_minutes,
        burn_total_minutes=burn_hours * 60 + burn_minutes,
        door_open=door_open,
        fan_raw=data[18],
        status_raw=data[6],
        raw=raw,
    )
