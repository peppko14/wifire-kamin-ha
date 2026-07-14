# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Reproduzierbare Referenzberechnung historischer Brennkurven."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from statistics import fmean
from typing import Iterable

from history.curves import BurnCurve, SAMPLE_AXIS




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
class CurveAnalysis:
    """Durchschnitt sowie reale Referenz- und Höchsttemperaturkurve."""

    curves: tuple[BurnCurve, ...]
    average_points: tuple[AverageCurvePoint, ...]
    representative_curve: BurnCurve
    representative_rmse_c: float
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
    squared_errors = [
        (point.temperature_c - average.average_temperature_c) ** 2
        for point, average in zip(curve.points, average_points, strict=True)
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


def analyze_curves(
    curves: Iterable[BurnCurve],
    *,
    since: datetime | None = None,
    include_warnings: bool = True,
) -> CurveAnalysis:
    """Berechnet Durchschnitt, repräsentative und heißeste reale Kurve."""
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
    distances = {
        curve.burn_id: curve_rmse(curve, average_points)
        for curve in ordered
    }
    representative = min(
        ordered,
        key=lambda curve: (
            distances[curve.burn_id],
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
        representative_curve=representative,
        representative_rmse_c=distances[representative.burn_id],
        hottest_curve=hottest,
        since=since,
        include_warnings=include_warnings,
    )
