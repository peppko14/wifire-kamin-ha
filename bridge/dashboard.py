# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Kompakte Brennkurven-Momentaufnahme für Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite

from history.curve_analysis import CurveAnalysis
from history.curves import SAMPLE_AXIS, BurnCurve
from protocol.quality import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C



DASHBOARD_SCHEMA_VERSION = 1
MAX_DASHBOARD_PAYLOAD_BYTES = 16 * 1024

ROLE_AVERAGE = "average"
ROLE_REPRESENTATIVE = "representative"
ROLE_HOTTEST = "hottest"
SERIES_ROLES = frozenset(
    {
        ROLE_AVERAGE,
        ROLE_REPRESENTATIVE,
        ROLE_HOTTEST,
    }
)
HEX_DIGITS = frozenset("0123456789abcdef")


class DashboardSnapshotError(ValueError):
    """Die kompakte Dashboard-Momentaufnahme ist ungültig."""


class DashboardPayloadTooLargeError(DashboardSnapshotError):
    """Die Momentaufnahme überschreitet die festgelegte Größengrenze."""


@dataclass(frozen=True, slots=True)
class DashboardCurveSeries:
    """Eine kompakte Temperaturreihe mit optionalen Abbrand-Metadaten."""

    role: str
    label: str
    temperatures_c: tuple[int | float, ...]
    burn_id: str | None = None
    start: datetime | None = None
    duration_minutes: int | None = None
    rmse_to_average_c: float | None = None

    def __post_init__(self) -> None:
        if self.role not in SERIES_ROLES:
            raise DashboardSnapshotError("Unbekannte Rolle der Temperaturreihe.")
        if not self.label.strip():
            raise DashboardSnapshotError("Eine Temperaturreihe braucht ein Label.")
        if not self.temperatures_c:
            raise DashboardSnapshotError("Eine Temperaturreihe darf nicht leer sein.")
        for temperature in self.temperatures_c:
            _validate_temperature(temperature)

        if self.role == ROLE_AVERAGE:
            if any(
                value is not None
                for value in (
                    self.burn_id,
                    self.start,
                    self.duration_minutes,
                    self.rmse_to_average_c,
                )
            ):
                raise DashboardSnapshotError(
                    "Die Durchschnittskurve darf keine Abbrand-Metadaten "
                    "besitzen."
                )
            return

        _validate_burn_id(self.burn_id)
        if not isinstance(self.start, datetime):
            raise DashboardSnapshotError(
                "Eine reale Brennkurve braucht einen Startzeitpunkt."
            )
        if self.duration_minutes is not None and (
            isinstance(self.duration_minutes, bool)
            or not isinstance(self.duration_minutes, int)
            or self.duration_minutes < 0
        ):
            raise DashboardSnapshotError(
                "duration_minutes muss nichtnegativ oder null sein."
            )

        if self.role == ROLE_REPRESENTATIVE:
            if (
                isinstance(self.rmse_to_average_c, bool)
                or not isinstance(self.rmse_to_average_c, (int, float))
                or not isfinite(float(self.rmse_to_average_c))
                or self.rmse_to_average_c < 0
            ):
                raise DashboardSnapshotError(
                    "Die Referenzkurve braucht einen nichtnegativen RMSE."
                )
        elif self.rmse_to_average_c is not None:
            raise DashboardSnapshotError(
                "Nur die Referenzkurve darf einen RMSE besitzen."
            )

    @property
    def sample_count(self) -> int:
        return len(self.temperatures_c)

    @property
    def max_temperature_c(self) -> int | float:
        return max(self.temperatures_c)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "role": self.role,
            "label": self.label,
            "max_temperature_c": self.max_temperature_c,
            "temperatures_c": list(self.temperatures_c),
        }
        if self.burn_id is not None:
            result.update(
                {
                    "burn_id": self.burn_id,
                    "start": self.start.isoformat(timespec="seconds"),
                    "duration_minutes": self.duration_minutes,
                }
            )
        if self.rmse_to_average_c is not None:
            result["rmse_to_average_c"] = self.rmse_to_average_c
        return result


@dataclass(frozen=True, slots=True)
class DashboardCurveSnapshot:
    """Genau drei Kurven fuer eine begrenzte Dashboard-Nachricht."""

    generated_at: datetime
    source_curve_count: int
    sample_count: int
    average: DashboardCurveSeries
    representative: DashboardCurveSeries
    hottest: DashboardCurveSeries
    since: datetime | None
    include_warnings: bool
    sample_axis: str = SAMPLE_AXIS
    schema_version: int = DASHBOARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.generated_at, datetime):
            raise DashboardSnapshotError("generated_at muss ein Zeitstempel sein.")
        if (
            isinstance(self.source_curve_count, bool)
            or not isinstance(self.source_curve_count, int)
            or self.source_curve_count < 1
        ):
            raise DashboardSnapshotError(
                "source_curve_count muss mindestens 1 sein."
            )
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count < 1
        ):
            raise DashboardSnapshotError("sample_count muss mindestens 1 sein.")
        if self.sample_axis != SAMPLE_AXIS:
            raise DashboardSnapshotError("Unbekannte Achse der Brennkurven.")
        if self.schema_version != DASHBOARD_SCHEMA_VERSION:
            raise DashboardSnapshotError(
                "Nicht unterstuetzte Dashboard-Schema-Version."
            )
        if self.since is not None and not isinstance(self.since, datetime):
            raise DashboardSnapshotError("since muss ein Zeitstempel oder null sein.")
        if not isinstance(self.include_warnings, bool):
            raise DashboardSnapshotError("include_warnings muss boolesch sein.")

        series = (self.average, self.representative, self.hottest)
        if tuple(item.role for item in series) != (
            ROLE_AVERAGE,
            ROLE_REPRESENTATIVE,
            ROLE_HOTTEST,
        ):
            raise DashboardSnapshotError(
                "Die Momentaufnahme braucht Durchschnitt, Referenz und "
                "Höchsttemperaturkurve."
            )
        if any(item.sample_count != self.sample_count for item in series):
            raise DashboardSnapshotError(
                "Alle Dashboard-Kurven müssen gleich viele Messpunkte besitzen."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "sample_axis": self.sample_axis,
            "source_curve_count": self.source_curve_count,
            "sample_count": self.sample_count,
            "filters": {
                "since": (
                    self.since.isoformat(timespec="seconds")
                    if self.since is not None
                    else None
                ),
                "include_warnings": self.include_warnings,
            },
            "series": {
                ROLE_AVERAGE: self.average.to_dict(),
                ROLE_REPRESENTATIVE: self.representative.to_dict(),
                ROLE_HOTTEST: self.hottest.to_dict(),
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @property
    def payload_size_bytes(self) -> int:
        return len(self.to_json().encode("utf-8"))


def _validate_temperature(temperature: int | float) -> None:
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not isfinite(float(temperature))
        or not MIN_TEMPERATURE_C <= temperature <= MAX_TEMPERATURE_C
    ):
        raise DashboardSnapshotError(
            "Temperaturwert liegt außerhalb der Qualitätsgrenzen."
        )


def _validate_burn_id(burn_id: str | None) -> None:
    if (
        not isinstance(burn_id, str)
        or len(burn_id) != 64
        or any(character not in HEX_DIGITS for character in burn_id)
    ):
        raise DashboardSnapshotError("burn_id muss ein SHA-256-Hash sein.")


def _series_from_curve(
    curve: BurnCurve,
    *,
    role: str,
    label: str,
    rmse_to_average_c: float | None = None,
) -> DashboardCurveSeries:
    return DashboardCurveSeries(
        role=role,
        label=label,
        temperatures_c=curve.temperatures_c,
        burn_id=curve.burn_id,
        start=curve.start,
        duration_minutes=curve.duration_minutes,
        rmse_to_average_c=rmse_to_average_c,
    )


def build_dashboard_snapshot(
    analysis: CurveAnalysis,
    *,
    generated_at: datetime | None = None,
    maximum_payload_bytes: int = MAX_DASHBOARD_PAYLOAD_BYTES,
) -> DashboardCurveSnapshot:
    """Verdichtet eine Analyse auf drei begrenzte Temperaturreihen."""
    if (
        isinstance(maximum_payload_bytes, bool)
        or not isinstance(maximum_payload_bytes, int)
        or maximum_payload_bytes < 1
    ):
        raise DashboardSnapshotError(
            "maximum_payload_bytes muss mindestens 1 sein."
        )

    snapshot = DashboardCurveSnapshot(
        generated_at=generated_at or datetime.now(timezone.utc),
        source_curve_count=analysis.source_curve_count,
        sample_count=analysis.sample_count,
        average=DashboardCurveSeries(
            role=ROLE_AVERAGE,
            label="Durchschnitt",
            temperatures_c=tuple(
                point.average_temperature_c
                for point in analysis.average_points
            ),
        ),
        representative=_series_from_curve(
            analysis.representative_curve,
            role=ROLE_REPRESENTATIVE,
            label="Repräsentativer Abbrand",
            rmse_to_average_c=analysis.representative_rmse_c,
        ),
        hottest=_series_from_curve(
            analysis.hottest_curve,
            role=ROLE_HOTTEST,
            label="Heißester Abbrand",
        ),
        since=analysis.since,
        include_warnings=analysis.include_warnings,
    )
    if snapshot.payload_size_bytes > maximum_payload_bytes:
        raise DashboardPayloadTooLargeError(
            "Dashboard-Payload ist mit "
            f"{snapshot.payload_size_bytes} Bytes größer als die Grenze "
            f"von {maximum_payload_bytes} Bytes."
        )
    return snapshot
