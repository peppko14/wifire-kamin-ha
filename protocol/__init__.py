# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Protocol models and decoders for the WiFire-Kamin project."""

from .duration import (
    DURATION_SOURCE_STAGE_0,
    DurationValueError,
    calculate_duration_minutes,
    unwrap_phase_minutes,
)
from .models import BurnRecord, LiveStatus

__all__ = [
    "BurnRecord",
    "DURATION_SOURCE_STAGE_0",
    "DurationValueError",
    "LiveStatus",
    "calculate_duration_minutes",
    "unwrap_phase_minutes",
]
