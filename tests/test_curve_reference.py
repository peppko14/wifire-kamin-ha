# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime
import unittest

from history.curve_reference import (
    ReferenceCurveCriteria,
    ReferenceSelectionError,
    ReferenceSelectionStatus,
    select_reference_curves,
)
from history.curves import BurnCurve, CurvePoint
from history.identifiers import build_burn_id
from history.periods import HeatingSeason
from protocol.models import BurnRecord


def make_curve(
    temperatures: tuple[int, ...],
    *,
    start: datetime,
    quality_status: str = "valid",
) -> BurnCurve:
    burn_id = build_burn_id(
        BurnRecord(start=start, temperatures_c=temperatures)
    )
    return BurnCurve(
        burn_id=burn_id,
        start=start,
        points=tuple(
            CurvePoint(index, temperature)
            for index, temperature in enumerate(temperatures)
        ),
        quality_status=quality_status,
        warning_codes=(
            ("timestamp_uncertain",)
            if quality_status == "warning"
            else ()
        ),
    )


class ReferenceCurveSelectionTests(unittest.TestCase):
    def test_default_selection_uses_only_valid_curves(self) -> None:
        curves = (
            make_curve((20, 100), start=datetime(2026, 1, 1)),
            make_curve((21, 101), start=datetime(2026, 1, 2)),
            make_curve((22, 102), start=datetime(2026, 1, 3)),
            make_curve(
                (23, 103),
                start=datetime(2017, 1, 1),
                quality_status="warning",
            ),
        )

        selection = select_reference_curves(curves)

        self.assertEqual(len(selection.curves), 3)
        self.assertEqual(selection.rejected_curve_count, 1)
        self.assertTrue(selection.is_evaluable)
        self.assertEqual(selection.status, ReferenceSelectionStatus.READY)

    def test_heating_season_filter_uses_july_boundary(self) -> None:
        included = make_curve(
            (20, 100),
            start=datetime(2026, 6, 30, 23, 59),
        )
        excluded = make_curve(
            (21, 101),
            start=datetime(2026, 7, 1),
        )
        criteria = ReferenceCurveCriteria(
            minimum_curve_count=1,
            heating_season=HeatingSeason(2025),
        )

        selection = select_reference_curves(
            (excluded, included),
            criteria,
        )

        self.assertEqual(selection.curves, (included,))

    def test_start_temperature_tolerance_is_inclusive(self) -> None:
        lower = make_curve((23, 100), start=datetime(2026, 1, 1))
        upper = make_curve((27, 100), start=datetime(2026, 1, 2))
        outside = make_curve((28, 100), start=datetime(2026, 1, 3))
        criteria = ReferenceCurveCriteria(
            minimum_curve_count=2,
            target_start_temperature_c=25,
            start_temperature_tolerance_c=2,
        )

        selection = select_reference_curves(
            (outside, upper, lower),
            criteria,
        )

        self.assertEqual(selection.curves, (lower, upper))
        self.assertTrue(selection.is_evaluable)

    def test_explicit_sample_count_filters_incompatible_curves(self) -> None:
        matching = make_curve((20, 100, 200), start=datetime(2026, 1, 1))
        incompatible = make_curve((20, 100), start=datetime(2026, 1, 2))
        criteria = ReferenceCurveCriteria(
            minimum_curve_count=1,
            sample_count=3,
        )

        selection = select_reference_curves(
            (incompatible, matching),
            criteria,
        )

        self.assertEqual(selection.curves, (matching,))
        self.assertEqual(selection.sample_count, 3)

    def test_ambiguous_sample_counts_require_explicit_filter(self) -> None:
        short = make_curve((20, 100), start=datetime(2026, 1, 1))
        long = make_curve((20, 100, 200), start=datetime(2026, 1, 2))

        with self.assertRaisesRegex(
            ReferenceSelectionError,
            "sample_count",
        ):
            select_reference_curves((short, long))

    def test_too_small_group_is_not_evaluable(self) -> None:
        curves = (
            make_curve((20, 100), start=datetime(2026, 1, 1)),
            make_curve((21, 101), start=datetime(2026, 1, 2)),
        )

        selection = select_reference_curves(curves)

        self.assertFalse(selection.is_evaluable)
        self.assertEqual(
            selection.status,
            ReferenceSelectionStatus.NOT_EVALUABLE,
        )

    def test_invalid_criteria_are_rejected(self) -> None:
        invalid_arguments = (
            {"minimum_curve_count": 0},
            {"minimum_curve_count": True},
            {"target_start_temperature_c": 20},
            {"start_temperature_tolerance_c": 2},
            {
                "target_start_temperature_c": 20,
                "start_temperature_tolerance_c": -1,
            },
            {"sample_count": 1},
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ReferenceSelectionError):
                    ReferenceCurveCriteria(**arguments)

    def test_selection_is_sorted_and_supports_stable_lookup(self) -> None:
        later = make_curve((21, 101), start=datetime(2026, 1, 2))
        earlier = make_curve((20, 100), start=datetime(2026, 1, 1))
        criteria = ReferenceCurveCriteria(minimum_curve_count=1)

        selection = select_reference_curves((later, earlier), criteria)

        self.assertEqual(selection.curves, (earlier, later))
        self.assertEqual(
            selection.curve_by_burn_id(later.burn_id),
            later,
        )
        self.assertIsNone(selection.curve_by_burn_id("0" * 64))

    def test_duplicate_burn_ids_are_rejected(self) -> None:
        curve = make_curve((20, 100), start=datetime(2026, 1, 1))

        with self.assertRaisesRegex(ReferenceSelectionError, "doppelte"):
            select_reference_curves((curve, curve))


if __name__ == "__main__":
    unittest.main()
