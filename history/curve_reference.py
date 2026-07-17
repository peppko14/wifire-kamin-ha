# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Reproduzierbare Auswahl geeigneter historischer Referenzkurven."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from history.curves import BurnCurve
from history.periods import HeatingSeason
from protocol.quality import (
    MAX_TEMPERATURE_C,
    MIN_MEASUREMENT_COUNT,
    MIN_TEMPERATURE_C,
)


class ReferenceSelectionError(ValueError):
    """Eine Referenzgruppe kann nicht eindeutig bestimmt werden."""


class ReferenceSelectionStatus(StrEnum):
    """Maschinenlesbarer Zustand einer Referenzgruppenauswahl."""

    READY = "ready"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ReferenceCurveCriteria:
    """Explizite, reproduzierbare Filter für historische Referenzkurven."""

    minimum_curve_count: int = 3
    heating_season: HeatingSeason | None = None
    target_start_temperature_c: int | None = None
    start_temperature_tolerance_c: int | None = None
    sample_count: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_curve_count, bool)
            or not isinstance(self.minimum_curve_count, int)
            or self.minimum_curve_count < 1
        ):
            raise ReferenceSelectionError(
                "minimum_curve_count muss eine positive Ganzzahl sein."
            )
        if self.heating_season is not None and not isinstance(
            self.heating_season,
            HeatingSeason,
        ):
            raise ReferenceSelectionError(
                "heating_season muss eine Heizsaison oder null sein."
            )
        if (self.target_start_temperature_c is None) != (
            self.start_temperature_tolerance_c is None
        ):
            raise ReferenceSelectionError(
                "Starttemperatur und Toleranz müssen gemeinsam gesetzt sein."
            )
        if self.target_start_temperature_c is not None:
            if (
                isinstance(self.target_start_temperature_c, bool)
                or not isinstance(self.target_start_temperature_c, int)
                or not MIN_TEMPERATURE_C
                <= self.target_start_temperature_c
                <= MAX_TEMPERATURE_C
            ):
                raise ReferenceSelectionError(
                    "target_start_temperature_c ist nicht plausibel."
                )
            tolerance = self.start_temperature_tolerance_c
            if (
                isinstance(tolerance, bool)
                or not isinstance(tolerance, int)
                or tolerance < 0
            ):
                raise ReferenceSelectionError(
                    "start_temperature_tolerance_c muss nichtnegativ sein."
                )
        if self.sample_count is not None and (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count < MIN_MEASUREMENT_COUNT
        ):
            raise ReferenceSelectionError(
                "sample_count liegt unter der Mindestanzahl."
            )


@dataclass(frozen=True, slots=True)
class ReferenceCurveSelection:
    """Gefilterte Referenzgruppe mit nachvollziehbarer Eignung."""

    criteria: ReferenceCurveCriteria
    curves: tuple[BurnCurve, ...]
    input_curve_count: int

    @property
    def rejected_curve_count(self) -> int:
        return self.input_curve_count - len(self.curves)

    @property
    def status(self) -> ReferenceSelectionStatus:
        if len(self.curves) >= self.criteria.minimum_curve_count:
            return ReferenceSelectionStatus.READY
        return ReferenceSelectionStatus.NOT_EVALUABLE

    @property
    def is_evaluable(self) -> bool:
        return self.status is ReferenceSelectionStatus.READY

    @property
    def sample_count(self) -> int | None:
        if not self.curves:
            return self.criteria.sample_count
        return self.curves[0].sample_count

    def curve_by_burn_id(self, burn_id: str) -> BurnCurve | None:
        """Findet eine explizite Referenz ausschließlich in dieser Gruppe."""
        return next(
            (curve for curve in self.curves if curve.burn_id == burn_id),
            None,
        )


def _matches_criteria(
    curve: BurnCurve,
    criteria: ReferenceCurveCriteria,
) -> bool:
    if curve.quality_status != "valid":
        return False
    if (
        criteria.heating_season is not None
        and not criteria.heating_season.contains(curve.start)
    ):
        return False
    if (
        criteria.sample_count is not None
        and curve.sample_count != criteria.sample_count
    ):
        return False
    if criteria.target_start_temperature_c is not None:
        tolerance = criteria.start_temperature_tolerance_c
        if tolerance is None:
            raise ReferenceSelectionError(
                "Validierte Starttemperaturtoleranz fehlt."
            )
        if (
            abs(
                curve.start_temperature_c
                - criteria.target_start_temperature_c
            )
            > tolerance
        ):
            return False
    return True


def select_reference_curves(
    curves: Iterable[BurnCurve],
    criteria: ReferenceCurveCriteria | None = None,
) -> ReferenceCurveSelection:
    """Filtert eine sortierte, vergleichbare historische Referenzgruppe."""
    selected_criteria = criteria or ReferenceCurveCriteria()
    source = tuple(curves)
    burn_ids = {curve.burn_id for curve in source}
    if len(burn_ids) != len(source):
        raise ReferenceSelectionError(
            "Referenzauswahl enthält doppelte Abbrand-IDs."
        )

    selected = tuple(
        sorted(
            (
                curve
                for curve in source
                if _matches_criteria(curve, selected_criteria)
            ),
            key=lambda curve: (curve.start, curve.burn_id),
        )
    )
    sample_counts = {curve.sample_count for curve in selected}
    if selected_criteria.sample_count is None and len(sample_counts) > 1:
        raise ReferenceSelectionError(
            "Referenzkurven besitzen verschiedene Messpunktanzahlen; "
            "sample_count muss explizit gesetzt werden."
        )

    return ReferenceCurveSelection(
        criteria=selected_criteria,
        curves=selected,
        input_curve_count=len(source),
    )
