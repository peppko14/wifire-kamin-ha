# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime
import unittest

from history.curve_analysis import (
    CurveAnalysisError,
    analyze_curves,
    curve_rmse,
    curve_rmse_to_median,
)
from history.curves import BurnCurve, CurvePoint
from history.identifiers import build_burn_id
from protocol.models import BurnRecord


def make_curve(
    temperatures: tuple[int, ...],
    *,
    start: datetime,
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
        quality_status="valid",
    )


class CurveAnalysisTests(unittest.TestCase):
    def test_average_curve_is_calculated_per_sample(self) -> None:
        first = make_curve((10, 20, 30), start=datetime(2026, 1, 1))
        second = make_curve((20, 30, 40), start=datetime(2026, 1, 2))

        analysis = analyze_curves((first, second))

        self.assertEqual(
            tuple(
                point.average_temperature_c
                for point in analysis.average_points
            ),
            (15.0, 25.0, 35.0),
        )
        self.assertTrue(
            all(
                point.contributing_curve_count == 2
                for point in analysis.average_points
            )
        )

    def test_representative_curve_is_closest_to_average(self) -> None:
        low = make_curve((0, 0), start=datetime(2026, 1, 1))
        middle = make_curve((10, 10), start=datetime(2026, 1, 2))
        high = make_curve((11, 11), start=datetime(2026, 1, 3))

        analysis = analyze_curves((low, middle, high))

        self.assertEqual(analysis.representative_curve, middle)
        self.assertEqual(analysis.representative_rmse_c, 3.0)

    def test_median_curve_is_robust_against_outlier(self) -> None:
        low = make_curve((10, 20), start=datetime(2026, 1, 1))
        middle = make_curve((11, 21), start=datetime(2026, 1, 2))
        outlier = make_curve((100, 200), start=datetime(2026, 1, 3))

        analysis = analyze_curves((low, middle, outlier))

        self.assertEqual(
            tuple(
                point.median_temperature_c
                for point in analysis.median_points
            ),
            (11.0, 21.0),
        )
        self.assertTrue(
            all(
                point.contributing_curve_count == 3
                for point in analysis.median_points
            )
        )

    def test_even_median_uses_middle_pair(self) -> None:
        first = make_curve((10, 20), start=datetime(2026, 1, 1))
        second = make_curve((20, 30), start=datetime(2026, 1, 2))

        analysis = analyze_curves((first, second))

        self.assertEqual(
            tuple(
                point.median_temperature_c
                for point in analysis.median_points
            ),
            (15.0, 25.0),
        )

    def test_median_representative_is_selected_separately(self) -> None:
        low = make_curve((0, 0), start=datetime(2026, 1, 1))
        middle = make_curve((10, 10), start=datetime(2026, 1, 2))
        high = make_curve((11, 11), start=datetime(2026, 1, 3))

        analysis = analyze_curves((low, middle, high))

        self.assertEqual(analysis.median_representative_curve, middle)
        self.assertEqual(analysis.median_representative_rmse_c, 0.0)
        self.assertEqual(analysis.representative_rmse_c, 3.0)

    def test_hottest_curve_is_separate_from_representative(self) -> None:
        normal = make_curve((20, 200), start=datetime(2026, 1, 1))
        hottest = make_curve((20, 600), start=datetime(2026, 1, 2))
        other = make_curve((20, 210), start=datetime(2026, 1, 3))

        analysis = analyze_curves((normal, hottest, other))

        self.assertEqual(analysis.hottest_curve, hottest)
        self.assertNotEqual(
            analysis.representative_curve,
            analysis.hottest_curve,
        )

    def test_hottest_tie_uses_earliest_start(self) -> None:
        later = make_curve((20, 500), start=datetime(2026, 1, 2))
        earlier = make_curve((30, 500), start=datetime(2026, 1, 1))

        analysis = analyze_curves((later, earlier))

        self.assertEqual(analysis.hottest_curve, earlier)

    def test_rmse_is_reproducible(self) -> None:
        first = make_curve((10, 20), start=datetime(2026, 1, 1))
        second = make_curve((20, 30), start=datetime(2026, 1, 2))
        analysis = analyze_curves((first, second))

        self.assertEqual(curve_rmse(first, analysis.average_points), 5.0)
        self.assertEqual(
            curve_rmse_to_median(first, analysis.median_points),
            5.0,
        )

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(CurveAnalysisError, "fehlen"):
            analyze_curves(())

    def test_different_sample_counts_are_rejected(self) -> None:
        short = make_curve((10, 20), start=datetime(2026, 1, 1))
        long = make_curve((10, 20, 30), start=datetime(2026, 1, 2))

        with self.assertRaisesRegex(CurveAnalysisError, "gleich viele"):
            analyze_curves((short, long))

    def test_duplicate_burn_ids_are_rejected(self) -> None:
        curve = make_curve((10, 20), start=datetime(2026, 1, 1))

        with self.assertRaisesRegex(CurveAnalysisError, "doppelte"):
            analyze_curves((curve, curve))

    def test_curves_are_sorted_chronologically(self) -> None:
        later = make_curve((10, 20), start=datetime(2026, 1, 2))
        earlier = make_curve((20, 30), start=datetime(2026, 1, 1))

        analysis = analyze_curves((later, earlier))

        self.assertEqual(analysis.curves, (earlier, later))


if __name__ == "__main__":
    unittest.main()
