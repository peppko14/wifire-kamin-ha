# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Stabile, reproduzierbare IDs für archivierte Abbrände."""

from __future__ import annotations

import hashlib

from protocol.models import BurnRecord


__version__ = "1.0.0"


def build_canonical_burn_text(record: BurnRecord) -> str:
    """
    Erzeugt die kanonische Darstellung für die Abbrand-ID.

    Die Archivnummer wird bewusst nicht berücksichtigt, da sie sich im
    Ringpuffer der WiFire-Steuerung ändern kann.
    """
    if record.start is None:
        raise ValueError(
            "Für eine stabile Abbrand-ID ist eine Startzeit erforderlich."
        )

    if not record.temperatures_c:
        raise ValueError(
            "Für eine stabile Abbrand-ID sind Temperaturwerte erforderlich."
        )

    start_text = record.start.isoformat(timespec="minutes")
    temperatures_text = ",".join(
        str(value) for value in record.temperatures_c
    )

    return (
        f"{start_text}|"
        f"{record.measurement_count}|"
        f"{temperatures_text}"
    )


def build_burn_id(record: BurnRecord) -> str:
    """Berechnet die vollständige SHA-256-ID eines Abbrands."""
    canonical = build_canonical_burn_text(record)

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
