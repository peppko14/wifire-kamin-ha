# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Protocol models and decoders for the WiFire-Kamin project."""

from .device_diagnostics import (
    AlarmEntry,
    AlarmList,
    ControllerTime,
    DeviceDiagnosticsClient,
    DeviceDiagnosticsReadError,
    decode_alarm_list,
    decode_controller_time,
)
from .duration import (
    DURATION_SOURCE_STAGE_0,
    DurationValueError,
    calculate_duration_minutes,
    unwrap_phase_minutes,
)
from .live import decode_live_status
from .models import BurnRecord, LiveStatus
from .quality import (
    EXPECTED_MEASUREMENT_COUNT,
    FIRST_RELIABLE_TIMESTAMP_YEAR,
    MAX_TEMPERATURE_C,
    MIN_MEASUREMENT_COUNT,
    MIN_TEMPERATURE_C,
    QualityIssue,
    QualityReport,
    QualitySeverity,
    validate_burn_record,
)

__all__ = [
    "AlarmEntry",
    "AlarmList",
    "BurnRecord",
    "ControllerTime",
    "DURATION_SOURCE_STAGE_0",
    "DeviceDiagnosticsClient",
    "DeviceDiagnosticsReadError",
    "DurationValueError",
    "EXPECTED_MEASUREMENT_COUNT",
    "FIRST_RELIABLE_TIMESTAMP_YEAR",
    "LiveStatus",
    "MAX_TEMPERATURE_C",
    "MIN_MEASUREMENT_COUNT",
    "MIN_TEMPERATURE_C",
    "QualityIssue",
    "QualityReport",
    "QualitySeverity",
    "calculate_duration_minutes",
    "decode_alarm_list",
    "decode_controller_time",
    "decode_live_status",
    "unwrap_phase_minutes",
    "validate_burn_record",
]
