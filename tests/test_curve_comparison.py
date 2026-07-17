# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime
import unittest

from history.curve_comparison import (
    HistoricalComparisonError,
    HistoricalComparisonReason,
    HistoricalComparisonStatus,
    compare_latest_historical_curve,
)
from history.curve_reference import ReferenceCurveCriteria
from history.curves import BurnCurve, CurvePoint
from history.identifiers import build_burn_id
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


class HistoricalCurveComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.low = make_curve((0, 0), start=datetime(2026, 1, 1))
        self.middle = make_curve((10, 10), start=datetime(2026, 1, 2))
        self.high = make_curve((20, 20), start=datetime(2026, 1, 3))
        self.latest = make_curve((15, 15), start=datetime(2026, 1, 4))

    def test_latest_curve_is_excluded_from_reference_group(self) -> None:
        comparison = compare_latest_historical_curve(
            (self.latest, self.middle, self.low, self.high)
        )

        self.assertEqual(comparison.subject_curve, self.latest)
        self.assertEqual(
            comparison.reference_selection.curves,
            (self.low, self.middle, self.high),
        )
        self.assertNotIn(
            self.latest.burn_id,
            {
                curve.burn_id
                for curve in comparison.reference_selection.curves
            },
        )

    def test_latest_curve_is_compared_with_historical_median(self) -> None:
        comparison = compare_latest_historical_curve(
            (self.low, self.middle, self.high, self.latest)
        )

        self.assertTrue(comparison.is_evaluable)
        self.assertEqual(comparison.status, HistoricalComparisonStatus.READY)
        self.assertEqual(comparison.reference_curve_count, 3)
        self.assertEqual(
            tuple(
                point.median_temperature_c
                for point in comparison.median_points
            ),
            (10.0, 10.0),
        )
        self.assertEqual(comparison.subject_median_rmse_c, 5.0)
        self.assertEqual(
            comparison.median_representative_curve,
            self.middle,
        )

    def test_selected_reference_is_compared_separately(self) -> None:
        comparison = compare_latest_historical_curve(
            (self.low, self.middle, self.high, self.latest),
            selected_reference_burn_id=self.low.burn_id,
        )

        self.assertEqual(comparison.selected_reference_curve, self.low)
        self.assertEqual(
            comparison.subject_selected_reference_rmse_c,
            15.0,
        )

    def test_unknown_selected_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(HistoricalComparisonError, "burn_id"):
            compare_latest_historical_curve(
                (self.low, self.middle, self.high, self.latest),
                selected_reference_burn_id="0" * 64,
            )

    def test_latest_curve_cannot_reference_itself(self) -> None:
        with self.assertRaisesRegex(HistoricalComparisonError, "eigene"):
            compare_latest_historical_curve(
                (self.low, self.middle, self.high, self.latest),
                selected_reference_burn_id=self.latest.burn_id,
            )

    def test_small_reference_group_is_not_evaluable(self) -> None:
        comparison = compare_latest_historical_curve(
            (self.low, self.latest)
        )

        self.assertFalse(comparison.is_evaluable)
        self.assertEqual(
            comparison.status,
            HistoricalComparisonStatus.NOT_EVALUABLE,
        )
        self.assertEqual(
            comparison.reason,
            HistoricalComparisonReason.REFERENCE_GROUP_TOO_SMALL,
        )
        self.assertEqual(comparison.median_points, ())

    def test_selected_pair_remains_available_for_small_group(self) -> None:
        comparison = compare_latest_historical_curve(
            (self.low, self.latest),
            selected_reference_burn_id=self.low.burn_id,
        )

        self.assertFalse(comparison.is_evaluable)
        self.assertEqual(comparison.selected_reference_curve, self.low)
        self.assertEqual(
            comparison.subject_selected_reference_rmse_c,
            15.0,
        )

    def test_warning_subject_is_not_evaluable(self) -> None:
        warning = make_curve(
            (15, 15),
            start=datetime(2026, 1, 5),
            quality_status="warning",
        )
        comparison = compare_latest_historical_curve(
            (self.low, self.middle, self.high, warning)
        )

        self.assertFalse(comparison.is_evaluable)
        self.assertEqual(
            comparison.reason,
            HistoricalComparisonReason.SUBJECT_QUALITY_NOT_VALID,
        )

    def test_subject_sample_count_is_applied_to_reference_group(self) -> None:
        incompatible = make_curve(
            (1, 2, 3),
            start=datetime(2025, 12, 31),
        )
        comparison = compare_latest_historical_curve(
            (
                incompatible,
                self.low,
                self.middle,
                self.high,
                self.latest,
            )
        )

        self.assertTrue(comparison.is_evaluable)
        self.assertEqual(
            comparison.reference_selection.rejected_curve_count,
            1,
        )

    def test_mismatching_configured_sample_count_is_rejected(self) -> None:
        criteria = ReferenceCurveCriteria(sample_count=3)

        with self.assertRaisesRegex(
            HistoricalComparisonError,
            "Messpunktanzahl",
        ):
            compare_latest_historical_curve(
                (self.low, self.middle, self.high, self.latest),
                criteria=criteria,
            )

    def test_empty_and_duplicate_input_are_rejected(self) -> None:
        with self.assertRaisesRegex(HistoricalComparisonError, "fehlen"):
            compare_latest_historical_curve(())
        with self.assertRaisesRegex(HistoricalComparisonError, "doppelte"):
            compare_latest_historical_curve((self.low, self.low))


if __name__ == "__main__":
    unittest.main()
