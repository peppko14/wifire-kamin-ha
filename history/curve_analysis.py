# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Reproduzierbare Referenzberechnung historischer Brennkurven."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from statistics import fmean, median
from typing import Iterable, Sequence

from history.curves import BurnCurve



class CurveAnalysisError(ValueError):
    """Brennkurven können nicht verlässlich gemeinsam analysiert werden."""


@dataclass(frozen=True, slots=True)
class AverageCurvePoint:
    """Arithmetischer Mittelwert an einer Messpunktposition."""

    sample_index: int
    average_temperature_c: float
    contributing_curve_count: int

    def to_dict(self) -> dict[str, int | float]:
        return {
            "sample_index": self.sample_index,
            "average_temperature_c": self.average_temperature_c,
            "contributing_curve_count": self.contributing_curve_count,
        }


@dataclass(frozen=True, slots=True)
class MedianCurvePoint:
    """Robuster Median an einer Messpunktposition."""

    sample_index: int
    median_temperature_c: float
    contributing_curve_count: int

    def to_dict(self) -> dict[str, int | float]:
        return {
            "sample_index": self.sample_index,
            "median_temperature_c": self.median_temperature_c,
            "contributing_curve_count": self.contributing_curve_count,
        }


@dataclass(frozen=True, slots=True)
class CurveAnalysis:
    """Historische Lagewerte und reproduzierbare reale Referenzkurven."""

    curves: tuple[BurnCurve, ...]
    average_points: tuple[AverageCurvePoint, ...]
    median_points: tuple[MedianCurvePoint, ...]
    representative_curve: BurnCurve
    representative_rmse_c: float
    median_representative_curve: BurnCurve
    median_representative_rmse_c: float
    hottest_curve: BurnCurve
    since: datetime | None
    include_warnings: bool

    @property
    def source_curve_count(self) -> int:
        return len(self.curves)

    @property
    def sample_count(self) -> int:
        return len(self.average_points)


def curve_rmse(
    curve: BurnCurve,
    average_points: tuple[AverageCurvePoint, ...],
) -> float:
    """Berechnet den RMSE einer realen Kurve zur Durchschnittskurve."""
    if curve.sample_count != len(average_points):
        raise CurveAnalysisError(
            "Kurve und Durchschnitt besitzen verschiedene Messpunktanzahlen."
        )
    reference_temperatures = tuple(
        point.average_temperature_c for point in average_points
    )
    return _curve_rmse_to_temperatures(curve, reference_temperatures)


def curve_rmse_to_median(
    curve: BurnCurve,
    median_points: tuple[MedianCurvePoint, ...],
) -> float:
    """Berechnet den RMSE einer realen Kurve zur Mediankurve."""
    if curve.sample_count != len(median_points):
        raise CurveAnalysisError(
            "Kurve und Median besitzen verschiedene Messpunktanzahlen."
        )
    reference_temperatures = tuple(
        point.median_temperature_c for point in median_points
    )
    return _curve_rmse_to_temperatures(curve, reference_temperatures)


def curve_rmse_between(
    curve: BurnCurve,
    reference_curve: BurnCurve,
) -> float:
    """Berechnet den RMSE zwischen zwei realen historischen Kurven."""
    if curve.sample_count != reference_curve.sample_count:
        raise CurveAnalysisError(
            "Verglichene Kurven besitzen verschiedene Messpunktanzahlen."
        )
    reference_temperatures = tuple(
        float(temperature)
        for temperature in reference_curve.temperatures_c
    )
    return _curve_rmse_to_temperatures(curve, reference_temperatures)


def _curve_rmse_to_temperatures(
    curve: BurnCurve,
    reference_temperatures: Sequence[float],
) -> float:
    squared_errors = [
        (point.temperature_c - reference_temperature) ** 2
        for point, reference_temperature in zip(
            curve.points,
            reference_temperatures,
            strict=True,
        )
    ]
    return round(sqrt(fmean(squared_errors)), 3)


def _average_points(curves: tuple[BurnCurve, ...]) -> tuple[AverageCurvePoint, ...]:
    count = len(curves)
    return tuple(
        AverageCurvePoint(
            sample_index=index,
            average_temperature_c=round(
                fmean(curve.points[index].temperature_c for curve in curves),
                1,
            ),
            contributing_curve_count=count,
        )
        for index in range(curves[0].sample_count)
    )


def _median_points(
    curves: tuple[BurnCurve, ...],
) -> tuple[MedianCurvePoint, ...]:
    count = len(curves)
    return tuple(
        MedianCurvePoint(
            sample_index=index,
            median_temperature_c=round(
                float(
                    median(
                        curve.points[index].temperature_c
                        for curve in curves
                    )
                ),
                1,
            ),
            contributing_curve_count=count,
        )
        for index in range(curves[0].sample_count)
    )


def analyze_curves(
    curves: Iterable[BurnCurve],
    *,
    since: datetime | None = None,
    include_warnings: bool = True,
) -> CurveAnalysis:
    """Berechnet Lagewerte und reproduzierbare reale Referenzkurven."""
    ordered = tuple(sorted(curves, key=lambda curve: (curve.start, curve.burn_id)))
    if not ordered:
        raise CurveAnalysisError("Für die Analyse fehlen Brennkurven.")

    burn_ids = {curve.burn_id for curve in ordered}
    if len(burn_ids) != len(ordered):
        raise CurveAnalysisError("Analyse enthält doppelte Abbrand-IDs.")

    sample_counts = {curve.sample_count for curve in ordered}
    if len(sample_counts) != 1:
        raise CurveAnalysisError(
            "Alle verglichenen Kurven müssen gleich viele Messpunkte besitzen."
        )

    average_points = _average_points(ordered)
    average_distances = {
        curve.burn_id: curve_rmse(curve, average_points)
        for curve in ordered
    }
    representative = min(
        ordered,
        key=lambda curve: (
            average_distances[curve.burn_id],
            curve.start,
            curve.burn_id,
        ),
    )
    median_points = _median_points(ordered)
    median_distances = {
        curve.burn_id: curve_rmse_to_median(curve, median_points)
        for curve in ordered
    }
    median_representative = min(
        ordered,
        key=lambda curve: (
            median_distances[curve.burn_id],
            curve.start,
            curve.burn_id,
        ),
    )
    hottest = min(
        ordered,
        key=lambda curve: (
            -curve.max_temperature_c,
            curve.start,
            curve.burn_id,
        ),
    )
    return CurveAnalysis(
        curves=ordered,
        average_points=average_points,
        median_points=median_points,
        representative_curve=representative,
        representative_rmse_c=average_distances[representative.burn_id],
        median_representative_curve=median_representative,
        median_representative_rmse_c=(
            median_distances[median_representative.burn_id]
        ),
        hottest_curve=hottest,
        since=since,
        include_warnings=include_warnings,
    )
