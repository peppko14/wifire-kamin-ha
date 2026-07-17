#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-Attribute für dekodierte WiFire-Archivdaten."""

from __future__ import annotations

from typing import Any

from protocol.duration import (
    DURATION_SOURCE_STAGE_0,
    calculate_duration_minutes,
)


def build_archive_attributes(
    record: Any,
) -> dict[str, object]:
    """Erzeugt die MQTT-Attribute eines Archivdatensatzes."""
    timestamp = (
        record.timestamp.isoformat(timespec="minutes")
        if record.timestamp
        else None
    )
    duration = calculate_duration_minutes(
        stage_90_minute=record.stage_90_minute,
        stage_75_minute=record.stage_75_minute,
        stage_50_minute=record.stage_50_minute,
        stage_25_minute=record.stage_25_minute,
        stage_0_minute=record.stage_0_minute,
    )

    return {
        "archive_number": record.archive_number,
        "start": timestamp,
        "measurement_count": record.measurement_count,
        "duration_minutes": duration,
        "duration_source": (
            DURATION_SOURCE_STAGE_0 if duration is not None else None
        ),
        "start_temperature_c": record.start_temperature_c,
        "end_temperature_c": record.end_temperature_c,
        "max_temperature_c": record.max_temperature_c,
        "max_temperature_minute": (
            record.max_temperature_minute
        ),
        "stage_90_minute": record.stage_90_minute,
        "stage_75_minute": record.stage_75_minute,
        "stage_50_minute": record.stage_50_minute,
        "stage_25_minute": record.stage_25_minute,
        "stage_0_minute": record.stage_0_minute,
        "temperatures_c": record.temperatures,
    }
