# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Robuste Brennkurvenanalyse für drei rollierende Heizsaisons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from history.curve_analysis import (
    CurveAnalysis,
    MedianCurvePoint,
    analyze_curves,
)
from history.curve_reference import (
    ReferenceCurveCriteria,
    ReferenceCurveSelection,
    select_reference_curves,
)
from history.curves import BurnCurve
from history.periods import HeatingSeason


class HeatingSeasonCurveError(ValueError):
    """Heizsaisonkurven können nicht eindeutig verglichen werden."""


class HeatingSeasonCurveStatus(StrEnum):
    """Maschinenlesbarer Zustand einer saisonalen Kurvenanalyse."""

    READY = "ready"
    NOT_EVALUABLE = "not_evaluable"


class HeatingSeasonCurveReason(StrEnum):
    """Grund für eine noch nicht bewertbare Heizsaison."""

    REFERENCE_GROUP_TOO_SMALL = "reference_group_too_small"


@dataclass(frozen=True, slots=True)
class HeatingSeasonCurveAnalysis:
    """Mediankurve und reale Referenz einer einzelnen Heizsaison."""

    season: HeatingSeason
    selection: ReferenceCurveSelection
    analysis: CurveAnalysis | None
    reason: HeatingSeasonCurveReason | None = None

    def __post_init__(self) -> None:
        if self.selection.criteria.heating_season != self.season:
            raise HeatingSeasonCurveError(
                "Auswahl und ausgewiesene Heizsaison widersprechen sich."
            )
        has_analysis = self.analysis is not None
        if has_analysis == (self.reason is not None):
            raise HeatingSeasonCurveError(
                "Analyse und Abbruchgrund sind widersprüchlich."
            )
        if self.analysis is not None:
            if not self.selection.is_evaluable:
                raise HeatingSeasonCurveError(
                    "Eine zu kleine Saison darf keine Analyse besitzen."
                )
            if self.analysis.curves != self.selection.curves:
                raise HeatingSeasonCurveError(
                    "Analyse und saisonale Referenzgruppe widersprechen sich."
                )

    @property
    def status(self) -> HeatingSeasonCurveStatus:
        if self.analysis is None:
            return HeatingSeasonCurveStatus.NOT_EVALUABLE
        return HeatingSeasonCurveStatus.READY

    @property
    def is_evaluable(self) -> bool:
        return self.status is HeatingSeasonCurveStatus.READY

    @property
    def source_curve_count(self) -> int:
        return self.selection.input_curve_count

    @property
    def eligible_curve_count(self) -> int:
        return len(self.selection.curves)

    @property
    def median_points(self) -> tuple[MedianCurvePoint, ...]:
        if self.analysis is None:
            return ()
        return self.analysis.median_points

    @property
    def median_representative_curve(self) -> BurnCurve | None:
        if self.analysis is None:
            return None
        return self.analysis.median_representative_curve


@dataclass(frozen=True, slots=True)
class CurrentHeatingSeasonCurveAnalysis:
    """Aktuelle und zwei vorherige Heizsaisons in fester Reihenfolge."""

    at: datetime
    sample_count: int | None
    seasons: tuple[
        HeatingSeasonCurveAnalysis,
        HeatingSeasonCurveAnalysis,
        HeatingSeasonCurveAnalysis,
    ]

    def __post_init__(self) -> None:
        if not isinstance(self.at, datetime):
            raise HeatingSeasonCurveError("at muss ein Zeitstempel sein.")
        current = HeatingSeason.from_datetime(self.at)
        expected = tuple(
            HeatingSeason(current.start_year - offset)
            for offset in range(3)
        )
        actual = tuple(item.season for item in self.seasons)
        if actual != expected:
            raise HeatingSeasonCurveError(
                "Es müssen aktuelle und zwei vorherige Heizsaisons vorliegen."
            )
        for item in self.seasons:
            selected_count = item.selection.sample_count
            if (
                selected_count is not None
                and self.sample_count is not None
                and selected_count != self.sample_count
            ):
                raise HeatingSeasonCurveError(
                    "Saisonale Messpunktanzahlen sind nicht vergleichbar."
                )

    def season_by_key(self, key: str) -> HeatingSeasonCurveAnalysis | None:
        """Findet eine der drei Heizsaisons über ihren stabilen Schlüssel."""
        return next(
            (item for item in self.seasons if item.season.key == key),
            None,
        )


def _target_seasons(at: datetime) -> tuple[
    HeatingSeason,
    HeatingSeason,
    HeatingSeason,
]:
    current = HeatingSeason.from_datetime(at)
    return (
        current,
        HeatingSeason(current.start_year - 1),
        HeatingSeason(current.start_year - 2),
    )


def _resolve_sample_count(
    curves: tuple[BurnCurve, ...],
    seasons: tuple[HeatingSeason, HeatingSeason, HeatingSeason],
    configured_sample_count: int | None,
) -> int | None:
    if configured_sample_count is not None:
        return configured_sample_count
    target_start_years = {season.start_year for season in seasons}
    sample_counts = {
        curve.sample_count
        for curve in curves
        if curve.quality_status == "valid"
        and HeatingSeason.from_datetime(curve.start).start_year
        in target_start_years
    }
    if len(sample_counts) > 1:
        raise HeatingSeasonCurveError(
            "Heizsaisons besitzen verschiedene Messpunktanzahlen; "
            "sample_count muss explizit gesetzt werden."
        )
    return next(iter(sample_counts), None)


def analyze_current_heating_season_curves(
    curves: Iterable[BurnCurve],
    *,
    at: datetime,
    minimum_curve_count: int = 3,
    sample_count: int | None = None,
) -> CurrentHeatingSeasonCurveAnalysis:
    """Analysiert genau drei rollierende Heizsaisons ohne Ersatzdaten."""
    if not isinstance(at, datetime):
        raise HeatingSeasonCurveError("at muss ein Zeitstempel sein.")
    source = tuple(curves)
    burn_ids = {curve.burn_id for curve in source}
    if len(burn_ids) != len(source):
        raise HeatingSeasonCurveError(
            "Saisonvergleich enthält doppelte Abbrand-IDs."
        )

    seasons = _target_seasons(at)
    resolved_sample_count = _resolve_sample_count(
        source,
        seasons,
        sample_count,
    )
    results: list[HeatingSeasonCurveAnalysis] = []

    for season in seasons:
        season_source = tuple(
            curve
            for curve in source
            if HeatingSeason.from_datetime(curve.start) == season
        )
        criteria = ReferenceCurveCriteria(
            minimum_curve_count=minimum_curve_count,
            heating_season=season,
            sample_count=resolved_sample_count,
        )
        selection = select_reference_curves(season_source, criteria)
        if not selection.is_evaluable:
            results.append(
                HeatingSeasonCurveAnalysis(
                    season=season,
                    selection=selection,
                    analysis=None,
                    reason=(
                        HeatingSeasonCurveReason.REFERENCE_GROUP_TOO_SMALL
                    ),
                )
            )
            continue
        results.append(
            HeatingSeasonCurveAnalysis(
                season=season,
                selection=selection,
                analysis=analyze_curves(
                    selection.curves,
                    include_warnings=False,
                ),
            )
        )

    return CurrentHeatingSeasonCurveAnalysis(
        at=at,
        sample_count=resolved_sample_count,
        seasons=(results[0], results[1], results[2]),
    )
