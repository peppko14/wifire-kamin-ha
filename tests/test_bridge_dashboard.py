# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json
import unittest

from bridge.dashboard import (
    DASHBOARD_SCHEMA_VERSION,
    MAX_DASHBOARD_PAYLOAD_BYTES,
    DashboardCurveSeries,
    DashboardCurveSnapshot,
    DashboardPayloadTooLargeError,
    DashboardSnapshotError,
    build_dashboard_snapshot,
)
from history.curve_analysis import analyze_curves
from history.curves import BurnCurve, CurvePoint, SAMPLE_AXIS
from history.identifiers import build_burn_id
from protocol.models import BurnRecord


def make_curve(
    temperatures: tuple[int, ...],
    *,
    start: datetime,
    duration_minutes: int | None = None,
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
        duration_minutes=duration_minutes,
    )


def make_analysis(*, sample_count: int = 3):
    low = tuple(20 + index for index in range(sample_count))
    middle = tuple(30 + index * 2 for index in range(sample_count))
    hot = tuple(40 + index * 4 for index in range(sample_count))
    curves = (
        make_curve(
            low,
            start=datetime(2026, 1, 1),
            duration_minutes=150,
        ),
        make_curve(
            middle,
            start=datetime(2026, 1, 2),
            duration_minutes=180,
        ),
        make_curve(
            hot,
            start=datetime(2026, 1, 3),
            duration_minutes=210,
        ),
    )
    return analyze_curves(
        curves,
        since=datetime(2026, 1, 1),
        include_warnings=False,
    )


class DashboardSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_exactly_three_defined_series(self) -> None:
        snapshot = build_dashboard_snapshot(
            make_analysis(),
            generated_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        )

        payload = snapshot.to_dict()

        self.assertEqual(
            tuple(payload["series"]),
            ("average", "representative", "hottest"),
        )
        self.assertNotIn("curves", payload)

    def test_snapshot_preserves_axis_and_filter_metadata(self) -> None:
        snapshot = build_dashboard_snapshot(make_analysis())

        payload = snapshot.to_dict()

        self.assertEqual(payload["schema_version"], DASHBOARD_SCHEMA_VERSION)
        self.assertEqual(payload["sample_axis"], SAMPLE_AXIS)
        self.assertEqual(payload["source_curve_count"], 3)
        self.assertEqual(payload["sample_count"], 3)
        self.assertEqual(payload["filters"]["since"], "2026-01-01T00:00:00")
        self.assertFalse(payload["filters"]["include_warnings"])

    def test_average_series_uses_calculated_values(self) -> None:
        analysis = make_analysis()

        snapshot = build_dashboard_snapshot(analysis)

        self.assertEqual(
            snapshot.average.temperatures_c,
            tuple(
                point.average_temperature_c
                for point in analysis.average_points
            ),
        )
        self.assertIsNone(snapshot.average.burn_id)

    def test_representative_series_contains_reference_metadata(self) -> None:
        analysis = make_analysis()

        snapshot = build_dashboard_snapshot(analysis)

        self.assertEqual(
            snapshot.representative.burn_id,
            analysis.representative_curve.burn_id,
        )
        self.assertEqual(
            snapshot.representative.rmse_to_average_c,
            analysis.representative_rmse_c,
        )

    def test_hottest_series_contains_hottest_real_curve(self) -> None:
        analysis = make_analysis()

        snapshot = build_dashboard_snapshot(analysis)

        self.assertEqual(
            snapshot.hottest.burn_id,
            analysis.hottest_curve.burn_id,
        )
        self.assertEqual(
            snapshot.hottest.max_temperature_c,
            analysis.hottest_curve.max_temperature_c,
        )

    def test_full_size_snapshot_stays_below_fixed_payload_limit(self) -> None:
        snapshot = build_dashboard_snapshot(make_analysis(sample_count=121))

        self.assertLessEqual(
            snapshot.payload_size_bytes,
            MAX_DASHBOARD_PAYLOAD_BYTES,
        )

    def test_payload_is_compact_json_without_point_objects(self) -> None:
        snapshot = build_dashboard_snapshot(make_analysis())

        payload = snapshot.to_json()
        decoded = json.loads(payload)

        self.assertNotIn('"sample_index":', payload)
        self.assertNotIn('"minute":', payload)
        self.assertEqual(
            decoded["series"]["average"]["temperatures_c"],
            list(snapshot.average.temperatures_c),
        )

    def test_configured_payload_limit_is_enforced(self) -> None:
        with self.assertRaises(DashboardPayloadTooLargeError):
            build_dashboard_snapshot(
                make_analysis(),
                maximum_payload_bytes=1,
            )

    def test_different_series_lengths_are_rejected(self) -> None:
        analysis = make_analysis()
        snapshot = build_dashboard_snapshot(analysis)
        shortened = DashboardCurveSeries(
            role="average",
            label="Durchschnitt",
            temperatures_c=(20.0, 30.0),
        )

        with self.assertRaisesRegex(DashboardSnapshotError, "gleich viele"):
            DashboardCurveSnapshot(
                generated_at=snapshot.generated_at,
                source_curve_count=snapshot.source_curve_count,
                sample_count=snapshot.sample_count,
                average=shortened,
                representative=snapshot.representative,
                hottest=snapshot.hottest,
                since=snapshot.since,
                include_warnings=snapshot.include_warnings,
            )

    def test_invalid_temperature_is_rejected(self) -> None:
        with self.assertRaisesRegex(DashboardSnapshotError, "Temperatur"):
            DashboardCurveSeries(
                role="average",
                label="Durchschnitt",
                temperatures_c=(float("nan"),),
            )

    def test_models_are_immutable(self) -> None:
        snapshot = build_dashboard_snapshot(make_analysis())

        with self.assertRaises(FrozenInstanceError):
            snapshot.sample_count = 4


if __name__ == "__main__":
    unittest.main()
