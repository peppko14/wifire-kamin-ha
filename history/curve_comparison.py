# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Reproduzierbarer Vergleich des letzten historischen Abbrands."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Iterable

from history.curve_analysis import (
    CurveAnalysis,
    MedianCurvePoint,
    analyze_curves,
    curve_rmse_between,
    curve_rmse_to_median,
)
from history.curve_reference import (
    ReferenceCurveCriteria,
    ReferenceCurveSelection,
    select_reference_curves,
)
from history.curves import BurnCurve


class HistoricalComparisonError(ValueError):
    """Ein historischer Vergleich ist widersprüchlich konfiguriert."""


class HistoricalComparisonStatus(StrEnum):
    """Maschinenlesbarer Zustand eines historischen Vergleichs."""

    READY = "ready"
    NOT_EVALUABLE = "not_evaluable"


class HistoricalComparisonReason(StrEnum):
    """Transparenter Grund für einen noch nicht bewertbaren Vergleich."""

    SUBJECT_QUALITY_NOT_VALID = "subject_quality_not_valid"
    REFERENCE_GROUP_TOO_SMALL = "reference_group_too_small"


@dataclass(frozen=True, slots=True)
class HistoricalCurveComparison:
    """Letzter Abbrand und seine ausschließlich historischen Vergleiche."""

    subject_curve: BurnCurve
    reference_selection: ReferenceCurveSelection
    reference_analysis: CurveAnalysis | None
    subject_median_rmse_c: float | None
    selected_reference_curve: BurnCurve | None = None
    subject_selected_reference_rmse_c: float | None = None
    reason: HistoricalComparisonReason | None = None

    def __post_init__(self) -> None:
        if self.reference_selection.curve_by_burn_id(
            self.subject_curve.burn_id
        ) is not None:
            raise HistoricalComparisonError(
                "Der letzte Abbrand darf nicht Teil seiner Referenzgruppe sein."
            )
        has_analysis = self.reference_analysis is not None
        has_median_distance = self.subject_median_rmse_c is not None
        if has_analysis != has_median_distance:
            raise HistoricalComparisonError(
                "Analyse und Medianabstand müssen gemeinsam gesetzt sein."
            )
        has_selected_curve = self.selected_reference_curve is not None
        has_selected_distance = (
            self.subject_selected_reference_rmse_c is not None
        )
        if has_selected_curve != has_selected_distance:
            raise HistoricalComparisonError(
                "Ausgewählte Referenz und Abstand müssen gemeinsam gesetzt sein."
            )
        if has_analysis == (self.reason is not None):
            raise HistoricalComparisonError(
                "Ein fertiger Vergleich darf keinen Abbruchgrund besitzen."
            )
        if self.reference_analysis is not None:
            if not self.reference_selection.is_evaluable:
                raise HistoricalComparisonError(
                    "Eine zu kleine Referenzgruppe darf keine Analyse besitzen."
                )
            if (
                self.reference_analysis.curves
                != self.reference_selection.curves
            ):
                raise HistoricalComparisonError(
                    "Analyse und ausgewählte Referenzgruppe widersprechen sich."
                )
        if (
            self.selected_reference_curve is not None
            and self.reference_selection.curve_by_burn_id(
                self.selected_reference_curve.burn_id
            ) is None
        ):
            raise HistoricalComparisonError(
                "Ausgewählte Referenz gehört nicht zur Referenzgruppe."
            )

    @property
    def status(self) -> HistoricalComparisonStatus:
        if self.reference_analysis is None:
            return HistoricalComparisonStatus.NOT_EVALUABLE
        return HistoricalComparisonStatus.READY

    @property
    def is_evaluable(self) -> bool:
        return self.status is HistoricalComparisonStatus.READY

    @property
    def reference_curve_count(self) -> int:
        return len(self.reference_selection.curves)

    @property
    def median_points(self) -> tuple[MedianCurvePoint, ...]:
        if self.reference_analysis is None:
            return ()
        return self.reference_analysis.median_points

    @property
    def median_representative_curve(self) -> BurnCurve | None:
        if self.reference_analysis is None:
            return None
        return self.reference_analysis.median_representative_curve


def _validate_unique_curves(curves: tuple[BurnCurve, ...]) -> None:
    burn_ids = {curve.burn_id for curve in curves}
    if len(burn_ids) != len(curves):
        raise HistoricalComparisonError(
            "Historischer Vergleich enthält doppelte Abbrand-IDs."
        )


def _effective_criteria(
    criteria: ReferenceCurveCriteria,
    subject_curve: BurnCurve,
) -> ReferenceCurveCriteria:
    if criteria.sample_count is not None:
        if criteria.sample_count != subject_curve.sample_count:
            raise HistoricalComparisonError(
                "Konfigurierte Messpunktanzahl passt nicht zum letzten Abbrand."
            )
        return criteria
    return replace(criteria, sample_count=subject_curve.sample_count)


def compare_latest_historical_curve(
    curves: Iterable[BurnCurve],
    *,
    criteria: ReferenceCurveCriteria | None = None,
    selected_reference_burn_id: str | None = None,
) -> HistoricalCurveComparison:
    """Vergleicht den letzten Abbrand ohne Selbstbezug mit seiner Historie."""
    source = tuple(curves)
    if not source:
        raise HistoricalComparisonError(
            "Für den historischen Vergleich fehlen Brennkurven."
        )
    _validate_unique_curves(source)

    subject = max(source, key=lambda curve: (curve.start, curve.burn_id))
    selected_criteria = _effective_criteria(
        criteria or ReferenceCurveCriteria(),
        subject,
    )
    reference_source = tuple(
        curve for curve in source if curve.burn_id != subject.burn_id
    )
    selection = select_reference_curves(
        reference_source,
        selected_criteria,
    )

    if selected_reference_burn_id == subject.burn_id:
        raise HistoricalComparisonError(
            "Der letzte Abbrand kann nicht seine eigene Referenz sein."
        )
    selected_reference = None
    if selected_reference_burn_id is not None:
        selected_reference = selection.curve_by_burn_id(
            selected_reference_burn_id
        )
        if selected_reference is None:
            raise HistoricalComparisonError(
                "Ausgewählte burn_id gehört nicht zur Referenzgruppe."
            )

    if subject.quality_status != "valid":
        return HistoricalCurveComparison(
            subject_curve=subject,
            reference_selection=selection,
            reference_analysis=None,
            subject_median_rmse_c=None,
            reason=(
                HistoricalComparisonReason.SUBJECT_QUALITY_NOT_VALID
            ),
        )
    selected_distance = None
    if selected_reference is not None:
        selected_distance = curve_rmse_between(subject, selected_reference)
    if not selection.is_evaluable:
        return HistoricalCurveComparison(
            subject_curve=subject,
            reference_selection=selection,
            reference_analysis=None,
            subject_median_rmse_c=None,
            selected_reference_curve=selected_reference,
            subject_selected_reference_rmse_c=selected_distance,
            reason=HistoricalComparisonReason.REFERENCE_GROUP_TOO_SMALL,
        )

    analysis = analyze_curves(
        selection.curves,
        include_warnings=False,
    )
    return HistoricalCurveComparison(
        subject_curve=subject,
        reference_selection=selection,
        reference_analysis=analysis,
        subject_median_rmse_c=curve_rmse_to_median(
            subject,
            analysis.median_points,
        ),
        selected_reference_curve=selected_reference,
        subject_selected_reference_rmse_c=selected_distance,
    )
