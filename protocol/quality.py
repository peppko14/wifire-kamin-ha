# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Fachliche Qualitätsprüfung historischer WiFire-Abbrände."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from protocol.models import BurnRecord



MIN_TEMPERATURE_C = -40
MAX_TEMPERATURE_C = 1200
MIN_MEASUREMENT_COUNT = 2
EXPECTED_MEASUREMENT_COUNT = 121
FIRST_RELIABLE_TIMESTAMP_YEAR = 2020
MIN_ARCHIVE_NUMBER = 1

PHASE_FIELDS = (
    "stage_90_minute",
    "stage_75_minute",
    "stage_50_minute",
    "stage_25_minute",
    "stage_0_minute",
)


class QualitySeverity(StrEnum):
    """Schweregrad eines Qualitätsmerkmals."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """Ein reproduzierbares Qualitätsmerkmal eines Abbrands."""

    code: str
    severity: QualitySeverity
    message: str

    def to_dict(self) -> dict[str, str]:
        """Erzeugt eine serialisierbare Darstellung."""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Gesamtergebnis der fachlichen Prüfung."""

    issues: tuple[QualityIssue, ...]

    @property
    def errors(self) -> tuple[QualityIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity is QualitySeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[QualityIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity is QualitySeverity.WARNING
        )

    @property
    def is_valid(self) -> bool:
        """True, wenn kein Merkmal mit Schweregrad Fehler vorliegt."""
        return not self.errors

    @property
    def status(self) -> str:
        """Kompakter Status für JSON und spätere Auswertungen."""
        if self.errors:
            return "invalid"
        if self.warnings:
            return "warning"
        return "valid"

    def to_dict(self) -> dict[str, object]:
        """Erzeugt eine serialisierbare Darstellung."""
        return {
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(
    code: str,
    severity: QualitySeverity,
    message: str,
) -> QualityIssue:
    return QualityIssue(code=code, severity=severity, message=message)


def validate_burn_record(record: BurnRecord) -> QualityReport:
    """Prüft einen Abbrand deterministisch auf Fehler und Auffälligkeiten."""
    issues: list[QualityIssue] = []

    if record.start is None:
        issues.append(
            _issue(
                "start_missing",
                QualitySeverity.ERROR,
                "Der Startzeitpunkt fehlt.",
            )
        )
    elif record.start.year < FIRST_RELIABLE_TIMESTAMP_YEAR:
        issues.append(
            _issue(
                "timestamp_uncertain",
                QualitySeverity.WARNING,
                (
                    "Der Zeitstempel stammt aus einem Zeitraum ohne "
                    "belegte Zeitsynchronisation der Steuerung."
                ),
            )
        )

    if record.active_or_incomplete:
        issues.append(
            _issue(
                "record_incomplete",
                QualitySeverity.ERROR,
                "Der Abbrand ist aktiv oder unvollständig.",
            )
        )

    if record.measurement_count < MIN_MEASUREMENT_COUNT:
        issues.append(
            _issue(
                "measurement_count_too_low",
                QualitySeverity.ERROR,
                "Der Datensatz enthält zu wenige Temperaturmesspunkte.",
            )
        )
    elif record.measurement_count != EXPECTED_MEASUREMENT_COUNT:
        issues.append(
            _issue(
                "measurement_count_unexpected",
                QualitySeverity.WARNING,
                "Die Anzahl der Messpunkte weicht vom Archivformat ab.",
            )
        )

    for index, temperature in enumerate(record.temperatures_c):
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, int)
            or not MIN_TEMPERATURE_C <= temperature <= MAX_TEMPERATURE_C
        ):
            issues.append(
                _issue(
                    "temperature_out_of_range",
                    QualitySeverity.ERROR,
                    f"Temperaturmesspunkt {index} ist nicht plausibel.",
                )
            )

    archive_number = record.source_archive_number
    if archive_number is not None and (
        isinstance(archive_number, bool)
        or not isinstance(archive_number, int)
        or archive_number < MIN_ARCHIVE_NUMBER
    ):
        issues.append(
            _issue(
                "archive_number_invalid",
                QualitySeverity.ERROR,
                "Die Quell-Archivnummer muss eine positive Ganzzahl sein.",
            )
        )

    for field in PHASE_FIELDS:
        value = getattr(record, field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 255
        ):
            issues.append(
                _issue(
                    "phase_value_invalid",
                    QualitySeverity.ERROR,
                    f"Der Phasenwert {field} liegt außerhalb von 0 bis 255.",
                )
            )

    if record.stage_0_minute is None:
        issues.append(
            _issue(
                "duration_unknown",
                QualitySeverity.WARNING,
                "Ohne stage_0_minute ist die Abbrenndauer unbekannt.",
            )
        )

    return QualityReport(issues=tuple(issues))
