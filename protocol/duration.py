# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zentrale Dauerdefinition für archivierte WiFire-Abbrände."""

from __future__ import annotations

from collections.abc import Iterable



DURATION_SOURCE_STAGE_0 = "stage_0_unwrapped"


class DurationValueError(ValueError):
    """Ein Phasenwert kann nicht zur Dauerberechnung verwendet werden."""


def unwrap_phase_minutes(
    stages: Iterable[int | None],
) -> tuple[int | None, ...]:
    """Entrollt kumulierte 8-Bit-Minutenwerte über 255er-Überläufe."""
    unwrapped: list[int | None] = []
    previous: int | None = None

    for raw_value in stages:
        if raw_value is None:
            unwrapped.append(None)
            continue
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise DurationValueError(
                "Phasenwerte müssen Ganzzahlen oder null sein."
            )
        if not 0 <= raw_value <= 255:
            raise DurationValueError(
                "Phasenwerte müssen zwischen 0 und 255 liegen."
            )

        value = raw_value
        if previous is not None:
            while value < previous:
                value += 256

        unwrapped.append(value)
        previous = value

    return tuple(unwrapped)


def calculate_duration_minutes(
    *,
    stage_90_minute: int | None,
    stage_75_minute: int | None,
    stage_50_minute: int | None,
    stage_25_minute: int | None,
    stage_0_minute: int | None,
) -> int | None:
    """Verwendet ausschließlich den entrollten 0-Prozent-Zeitpunkt."""
    stages = unwrap_phase_minutes((
        stage_90_minute,
        stage_75_minute,
        stage_50_minute,
        stage_25_minute,
        stage_0_minute,
    ))
    return stages[-1]
