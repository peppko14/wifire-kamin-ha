# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Kompakte Brennkurven-Momentaufnahme für Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite

from history.curve_analysis import CurveAnalysis
from history.curve_comparison import (
    HistoricalComparisonReason,
    HistoricalComparisonStatus,
    compare_latest_historical_curve,
)
from history.curve_reference import ReferenceCurveCriteria
from history.curve_seasons import (
    HeatingSeasonCurveAnalysis,
    HeatingSeasonCurveReason,
    HeatingSeasonCurveStatus,
    analyze_current_heating_season_curves,
)
from history.curves import SAMPLE_AXIS, BurnCurve
from protocol.quality import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C


DASHBOARD_SCHEMA_VERSION = 2
MAX_DASHBOARD_PAYLOAD_BYTES = 16 * 1024

ROLE_AVERAGE = "average"
ROLE_REPRESENTATIVE = "representative"
ROLE_HOTTEST = "hottest"
ROLE_MEDIAN = "median"
ROLE_MEDIAN_REPRESENTATIVE = "median_representative"
ROLE_LATEST = "latest"
ROLE_SELECTED_REFERENCE = "selected_reference"
SERIES_ROLES = frozenset(
    {
        ROLE_AVERAGE,
        ROLE_REPRESENTATIVE,
        ROLE_HOTTEST,
        ROLE_MEDIAN,
        ROLE_MEDIAN_REPRESENTATIVE,
        ROLE_LATEST,
        ROLE_SELECTED_REFERENCE,
    }
)
AGGREGATE_ROLES = frozenset({ROLE_AVERAGE, ROLE_MEDIAN})
HEX_DIGITS = frozenset("0123456789abcdef")


class DashboardSnapshotError(ValueError):
    """Die kompakte Dashboard-Momentaufnahme ist ungültig."""


class DashboardPayloadTooLargeError(DashboardSnapshotError):
    """Die Momentaufnahme überschreitet die festgelegte Größengrenze."""


def _validate_optional_rmse(value: float | None, field: str) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or value < 0
    ):
        raise DashboardSnapshotError(
            f"{field} muss nichtnegativ, endlich oder null sein."
        )


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
    rmse_to_median_c: float | None = None
    rmse_to_subject_c: float | None = None

    def __post_init__(self) -> None:
        if self.role not in SERIES_ROLES:
            raise DashboardSnapshotError("Unbekannte Rolle der Temperaturreihe.")
        if not self.label.strip():
            raise DashboardSnapshotError("Eine Temperaturreihe braucht ein Label.")
        if not self.temperatures_c:
            raise DashboardSnapshotError("Eine Temperaturreihe darf nicht leer sein.")
        for temperature in self.temperatures_c:
            _validate_temperature(temperature)

        rmse_values = (
            self.rmse_to_average_c,
            self.rmse_to_median_c,
            self.rmse_to_subject_c,
        )
        for field, value in zip(
            (
                "rmse_to_average_c",
                "rmse_to_median_c",
                "rmse_to_subject_c",
            ),
            rmse_values,
            strict=True,
        ):
            _validate_optional_rmse(value, field)

        if self.role in AGGREGATE_ROLES:
            if any(
                value is not None
                for value in (
                    self.burn_id,
                    self.start,
                    self.duration_minutes,
                    *rmse_values,
                )
            ):
                raise DashboardSnapshotError(
                    "Aggregierte Kurven dürfen keine Abbrand-Metadaten besitzen."
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
            if self.rmse_to_average_c is None or any(
                value is not None for value in rmse_values[1:]
            ):
                raise DashboardSnapshotError(
                    "Die Durchschnittsreferenz braucht ausschließlich "
                    "rmse_to_average_c."
                )
        elif self.role == ROLE_MEDIAN_REPRESENTATIVE:
            if (
                self.rmse_to_median_c is None
                or self.rmse_to_average_c is not None
                or self.rmse_to_subject_c is not None
            ):
                raise DashboardSnapshotError(
                    "Die Medianreferenz braucht ausschließlich rmse_to_median_c."
                )
        elif self.role == ROLE_SELECTED_REFERENCE:
            if (
                self.rmse_to_subject_c is None
                or self.rmse_to_average_c is not None
                or self.rmse_to_median_c is not None
            ):
                raise DashboardSnapshotError(
                    "Die ausgewählte Referenz braucht ausschließlich "
                    "rmse_to_subject_c."
                )
        elif self.role == ROLE_LATEST:
            if (
                self.rmse_to_average_c is not None
                or self.rmse_to_subject_c is not None
            ):
                raise DashboardSnapshotError(
                    "Der letzte Abbrand darf nur rmse_to_median_c besitzen."
                )
        elif any(value is not None for value in rmse_values):
            raise DashboardSnapshotError(
                "Die Höchsttemperaturkurve darf keinen RMSE besitzen."
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
            if self.start is None:
                raise DashboardSnapshotError(
                    "Reale Brennkurve besitzt keinen Startzeitpunkt."
                )
            result.update(
                {
                    "burn_id": self.burn_id,
                    "start": self.start.isoformat(timespec="seconds"),
                    "duration_minutes": self.duration_minutes,
                }
            )
        for field, value in (
            ("rmse_to_average_c", self.rmse_to_average_c),
            ("rmse_to_median_c", self.rmse_to_median_c),
            ("rmse_to_subject_c", self.rmse_to_subject_c),
        ):
            if value is not None:
                result[field] = value
        return result


@dataclass(frozen=True, slots=True)
class DashboardHeatingSeason:
    """Kompakte Mediankurve einer Heizsaison oder transparenter Leerstand."""

    period: str
    label: str
    status: HeatingSeasonCurveStatus
    reason: HeatingSeasonCurveReason | None
    source_curve_count: int
    eligible_curve_count: int
    median_temperatures_c: tuple[float, ...] | None
    representative_burn_id: str | None

    def __post_init__(self) -> None:
        if not self.period or not self.label:
            raise DashboardSnapshotError("Heizsaison braucht Zeitraum und Label.")
        for field, value in (
            ("source_curve_count", self.source_curve_count),
            ("eligible_curve_count", self.eligible_curve_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DashboardSnapshotError(
                    f"{field} muss eine nichtnegative Ganzzahl sein."
                )
        if self.eligible_curve_count > self.source_curve_count:
            raise DashboardSnapshotError(
                "Geeignete Saisonkurven dürfen die Quellanzahl nicht übersteigen."
            )
        if self.status is HeatingSeasonCurveStatus.READY:
            if self.reason is not None or not self.median_temperatures_c:
                raise DashboardSnapshotError(
                    "Auswertbare Saison braucht eine Mediankurve ohne Fehlergrund."
                )
            _validate_burn_id(self.representative_burn_id)
            for temperature in self.median_temperatures_c:
                _validate_temperature(temperature)
        elif (
            self.reason is None
            or self.median_temperatures_c is not None
            or self.representative_burn_id is not None
        ):
            raise DashboardSnapshotError(
                "Nicht auswertbare Saison darf keine erfundene Kurve besitzen."
            )

    @property
    def sample_count(self) -> int | None:
        if self.median_temperatures_c is None:
            return None
        return len(self.median_temperatures_c)

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.period,
            "label": self.label,
            "status": self.status.value,
            "reason": self.reason.value if self.reason is not None else None,
            "source_curve_count": self.source_curve_count,
            "eligible_curve_count": self.eligible_curve_count,
            "sample_count": self.sample_count,
            "median_temperatures_c": (
                list(self.median_temperatures_c)
                if self.median_temperatures_c is not None
                else None
            ),
            "representative_burn_id": self.representative_burn_id,
        }


@dataclass(frozen=True, slots=True)
class DashboardCurveSnapshot:
    """Begrenzte historische Brennkurven-Momentaufnahme nach Schema 2."""

    generated_at: datetime
    source_curve_count: int
    sample_count: int
    average: DashboardCurveSeries
    representative: DashboardCurveSeries
    hottest: DashboardCurveSeries
    median: DashboardCurveSeries | None
    median_representative: DashboardCurveSeries | None
    latest: DashboardCurveSeries
    selected_reference: DashboardCurveSeries | None
    heating_seasons: tuple[
        DashboardHeatingSeason,
        DashboardHeatingSeason,
        DashboardHeatingSeason,
    ]
    comparison_status: HistoricalComparisonStatus
    comparison_reason: HistoricalComparisonReason | None
    reference_curve_count: int
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
                "Nicht unterstützte Dashboard-Schema-Version."
            )
        if self.since is not None and not isinstance(self.since, datetime):
            raise DashboardSnapshotError("since muss ein Zeitstempel oder null sein.")
        if not isinstance(self.include_warnings, bool):
            raise DashboardSnapshotError("include_warnings muss boolesch sein.")
        if (
            isinstance(self.reference_curve_count, bool)
            or not isinstance(self.reference_curve_count, int)
            or self.reference_curve_count < 0
        ):
            raise DashboardSnapshotError(
                "reference_curve_count muss nichtnegativ sein."
            )

        fixed_series = (
            (self.average, ROLE_AVERAGE),
            (self.representative, ROLE_REPRESENTATIVE),
            (self.hottest, ROLE_HOTTEST),
            (self.latest, ROLE_LATEST),
        )
        if any(series.role != role for series, role in fixed_series):
            raise DashboardSnapshotError(
                "Dashboard-Reihen besitzen eine unerwartete Rolle."
            )
        if self.comparison_status is HistoricalComparisonStatus.READY:
            if (
                self.comparison_reason is not None
                or self.median is None
                or self.median_representative is None
            ):
                raise DashboardSnapshotError(
                    "Auswertbarer Vergleich braucht Median und Referenz."
                )
        elif (
            self.comparison_reason is None
            or self.median is not None
            or self.median_representative is not None
        ):
            raise DashboardSnapshotError(
                "Nicht auswertbarer Vergleich darf keine Medianreihe erfinden."
            )
        if self.median is not None and self.median.role != ROLE_MEDIAN:
            raise DashboardSnapshotError("Mediankurve besitzt falsche Rolle.")
        if (
            self.median_representative is not None
            and self.median_representative.role
            != ROLE_MEDIAN_REPRESENTATIVE
        ):
            raise DashboardSnapshotError(
                "Medianreferenz besitzt falsche Rolle."
            )
        if (
            self.selected_reference is not None
            and self.selected_reference.role != ROLE_SELECTED_REFERENCE
        ):
            raise DashboardSnapshotError(
                "Ausgewählte Referenz besitzt falsche Rolle."
            )

        series = [item for item, _ in fixed_series]
        series.extend(
            item
            for item in (
                self.median,
                self.median_representative,
                self.selected_reference,
            )
            if item is not None
        )
        if any(item.sample_count != self.sample_count for item in series):
            raise DashboardSnapshotError(
                "Alle Dashboard-Kurven müssen gleich viele Messpunkte besitzen."
            )
        if len(self.heating_seasons) != 3:
            raise DashboardSnapshotError(
                "Dashboard braucht genau drei Heizsaisons."
            )
        if any(
            item.sample_count not in (None, self.sample_count)
            for item in self.heating_seasons
        ):
            raise DashboardSnapshotError(
                "Saisonkurven besitzen eine abweichende Messpunktanzahl."
            )

    def to_dict(self) -> dict[str, object]:
        series = {
            ROLE_AVERAGE: self.average.to_dict(),
            ROLE_REPRESENTATIVE: self.representative.to_dict(),
            ROLE_HOTTEST: self.hottest.to_dict(),
            ROLE_LATEST: self.latest.to_dict(),
        }
        for item in (
            self.median,
            self.median_representative,
            self.selected_reference,
        ):
            if item is not None:
                series[item.role] = item.to_dict()

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
            "comparison": {
                "status": self.comparison_status.value,
                "reason": (
                    self.comparison_reason.value
                    if self.comparison_reason is not None
                    else None
                ),
                "reference_curve_count": self.reference_curve_count,
                "latest_burn_id": self.latest.burn_id,
                "rmse_to_median_c": self.latest.rmse_to_median_c,
                "selected_reference_burn_id": (
                    self.selected_reference.burn_id
                    if self.selected_reference is not None
                    else None
                ),
                "rmse_to_selected_reference_c": (
                    self.selected_reference.rmse_to_subject_c
                    if self.selected_reference is not None
                    else None
                ),
            },
            "series": series,
            "heating_seasons": [
                item.to_dict() for item in self.heating_seasons
            ],
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
    rmse_to_median_c: float | None = None,
    rmse_to_subject_c: float | None = None,
) -> DashboardCurveSeries:
    return DashboardCurveSeries(
        role=role,
        label=label,
        temperatures_c=curve.temperatures_c,
        burn_id=curve.burn_id,
        start=curve.start,
        duration_minutes=curve.duration_minutes,
        rmse_to_average_c=rmse_to_average_c,
        rmse_to_median_c=rmse_to_median_c,
        rmse_to_subject_c=rmse_to_subject_c,
    )


def _dashboard_season(
    item: HeatingSeasonCurveAnalysis,
) -> DashboardHeatingSeason:
    representative = item.median_representative_curve
    return DashboardHeatingSeason(
        period=item.season.key,
        label=item.season.label,
        status=item.status,
        reason=item.reason,
        source_curve_count=item.source_curve_count,
        eligible_curve_count=item.eligible_curve_count,
        median_temperatures_c=(
            tuple(point.median_temperature_c for point in item.median_points)
            if item.is_evaluable
            else None
        ),
        representative_burn_id=(
            representative.burn_id if representative is not None else None
        ),
    )


def build_dashboard_snapshot(
    analysis: CurveAnalysis,
    *,
    generated_at: datetime | None = None,
    maximum_payload_bytes: int = MAX_DASHBOARD_PAYLOAD_BYTES,
    minimum_reference_curve_count: int = 3,
    selected_reference_burn_id: str | None = None,
) -> DashboardCurveSnapshot:
    """Verdichtet historische Vergleiche auf ein begrenztes Schema 2."""
    if (
        isinstance(maximum_payload_bytes, bool)
        or not isinstance(maximum_payload_bytes, int)
        or maximum_payload_bytes < 1
    ):
        raise DashboardSnapshotError(
            "maximum_payload_bytes muss mindestens 1 sein."
        )

    timestamp = generated_at or datetime.now(timezone.utc)
    criteria = ReferenceCurveCriteria(
        minimum_curve_count=minimum_reference_curve_count,
        sample_count=analysis.sample_count,
    )
    comparison = compare_latest_historical_curve(
        analysis.curves,
        criteria=criteria,
        selected_reference_burn_id=selected_reference_burn_id,
    )
    season_analysis = analyze_current_heating_season_curves(
        analysis.curves,
        at=timestamp,
        minimum_curve_count=minimum_reference_curve_count,
        sample_count=analysis.sample_count,
    )

    median = None
    median_representative = None
    if comparison.is_evaluable:
        representative_curve = comparison.median_representative_curve
        if representative_curve is None or comparison.reference_analysis is None:
            raise DashboardSnapshotError(
                "Auswertbarer Vergleich besitzt keine Medianreferenz."
            )
        median = DashboardCurveSeries(
            role=ROLE_MEDIAN,
            label="Historischer Median",
            temperatures_c=tuple(
                point.median_temperature_c
                for point in comparison.median_points
            ),
        )
        median_representative = _series_from_curve(
            representative_curve,
            role=ROLE_MEDIAN_REPRESENTATIVE,
            label="Realer Median-Referenzabbrand",
            rmse_to_median_c=(
                comparison.reference_analysis.median_representative_rmse_c
            ),
        )

    selected_reference = None
    if comparison.selected_reference_curve is not None:
        selected_reference = _series_from_curve(
            comparison.selected_reference_curve,
            role=ROLE_SELECTED_REFERENCE,
            label="Ausgewählter Referenzabbrand",
            rmse_to_subject_c=(
                comparison.subject_selected_reference_rmse_c
            ),
        )

    snapshot = DashboardCurveSnapshot(
        generated_at=timestamp,
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
        median=median,
        median_representative=median_representative,
        latest=_series_from_curve(
            comparison.subject_curve,
            role=ROLE_LATEST,
            label="Letzter Abbrand",
            rmse_to_median_c=comparison.subject_median_rmse_c,
        ),
        selected_reference=selected_reference,
        heating_seasons=(
            _dashboard_season(season_analysis.seasons[0]),
            _dashboard_season(season_analysis.seasons[1]),
            _dashboard_season(season_analysis.seasons[2]),
        ),
        comparison_status=comparison.status,
        comparison_reason=comparison.reason,
        reference_curve_count=comparison.reference_curve_count,
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
