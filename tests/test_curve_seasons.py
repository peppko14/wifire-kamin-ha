# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime
import unittest

from history.curve_seasons import (
    HeatingSeasonCurveError,
    HeatingSeasonCurveReason,
    HeatingSeasonCurveStatus,
    analyze_current_heating_season_curves,
)
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


class HeatingSeasonCurveAnalysisTests(unittest.TestCase):
    def test_always_returns_three_rolling_seasons(self) -> None:
        result = analyze_current_heating_season_curves(
            (),
            at=datetime(2026, 8, 1),
        )

        self.assertEqual(
            tuple(item.season.label for item in result.seasons),
            ("2026/2027", "2025/2026", "2024/2025"),
        )
        self.assertTrue(
            all(
                item.status is HeatingSeasonCurveStatus.NOT_EVALUABLE
                for item in result.seasons
            )
        )
        self.assertIsNone(result.sample_count)

    def test_each_season_receives_its_own_median_curve(self) -> None:
        current = (
            make_curve((10, 20), start=datetime(2026, 7, 2)),
            make_curve((20, 30), start=datetime(2026, 7, 3)),
            make_curve((30, 40), start=datetime(2026, 7, 4)),
        )
        previous = (
            make_curve((100, 200), start=datetime(2026, 2, 1)),
            make_curve((110, 210), start=datetime(2026, 2, 2)),
            make_curve((120, 220), start=datetime(2026, 2, 3)),
        )

        result = analyze_current_heating_season_curves(
            current + previous,
            at=datetime(2026, 8, 1),
        )

        self.assertEqual(
            tuple(
                point.median_temperature_c
                for point in result.seasons[0].median_points
            ),
            (20.0, 30.0),
        )
        self.assertEqual(
            tuple(
                point.median_temperature_c
                for point in result.seasons[1].median_points
            ),
            (110.0, 210.0),
        )
        self.assertEqual(result.seasons[2].median_points, ())
        self.assertEqual(result.sample_count, 2)

    def test_july_boundary_assigns_curves_to_correct_season(self) -> None:
        before = make_curve(
            (10, 20),
            start=datetime(2026, 6, 30, 23, 59),
        )
        after = make_curve((20, 30), start=datetime(2026, 7, 1))

        result = analyze_current_heating_season_curves(
            (before, after),
            at=datetime(2026, 8, 1),
            minimum_curve_count=1,
        )

        self.assertEqual(result.seasons[0].selection.curves, (after,))
        self.assertEqual(result.seasons[1].selection.curves, (before,))

    def test_warning_curves_are_excluded_and_reported_in_count(self) -> None:
        valid = make_curve((10, 20), start=datetime(2026, 7, 2))
        warning = make_curve(
            (20, 30),
            start=datetime(2026, 7, 3),
            quality_status="warning",
        )

        result = analyze_current_heating_season_curves(
            (valid, warning),
            at=datetime(2026, 8, 1),
            minimum_curve_count=2,
        )
        season = result.seasons[0]

        self.assertEqual(season.source_curve_count, 2)
        self.assertEqual(season.eligible_curve_count, 1)
        self.assertEqual(
            season.reason,
            HeatingSeasonCurveReason.REFERENCE_GROUP_TOO_SMALL,
        )

    def test_mixed_sample_counts_require_explicit_filter(self) -> None:
        short = make_curve((10, 20), start=datetime(2026, 7, 2))
        long = make_curve((10, 20, 30), start=datetime(2026, 7, 3))

        with self.assertRaisesRegex(HeatingSeasonCurveError, "sample_count"):
            analyze_current_heating_season_curves(
                (short, long),
                at=datetime(2026, 8, 1),
            )

    def test_explicit_sample_count_filters_incompatible_curves(self) -> None:
        matching = make_curve((10, 20), start=datetime(2026, 7, 2))
        incompatible = make_curve(
            (10, 20, 30),
            start=datetime(2026, 7, 3),
        )

        result = analyze_current_heating_season_curves(
            (matching, incompatible),
            at=datetime(2026, 8, 1),
            minimum_curve_count=1,
            sample_count=2,
        )

        self.assertTrue(result.seasons[0].is_evaluable)
        self.assertEqual(
            result.seasons[0].selection.curves,
            (matching,),
        )

    def test_stable_season_lookup(self) -> None:
        result = analyze_current_heating_season_curves(
            (),
            at=datetime(2026, 8, 1),
        )

        self.assertEqual(
            result.season_by_key("2025-2026"),
            result.seasons[1],
        )
        self.assertIsNone(result.season_by_key("2023-2024"))

    def test_duplicate_ids_and_invalid_timestamp_are_rejected(self) -> None:
        curve = make_curve((10, 20), start=datetime(2026, 7, 2))

        with self.assertRaisesRegex(HeatingSeasonCurveError, "doppelte"):
            analyze_current_heating_season_curves(
                (curve, curve),
                at=datetime(2026, 8, 1),
            )
        with self.assertRaisesRegex(HeatingSeasonCurveError, "Zeitstempel"):
            analyze_current_heating_season_curves((), at="2026-08-01")


if __name__ == "__main__":
    unittest.main()
