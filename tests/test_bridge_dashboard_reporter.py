# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from bridge.dashboard import DashboardCurveSnapshot
from bridge.dashboard_reporter import (
    DashboardCurveReporter,
    parse_dashboard_since,
)
from history.curves import BurnCurve, BurnCurveLoadResult, CurvePoint
from history.identifiers import build_burn_id
from history.storage import HistoryReadIssue
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


class FakePublisher:
    def __init__(self) -> None:
        self.snapshots: list[DashboardCurveSnapshot] = []

    def publish_dashboard_snapshot(
        self,
        snapshot: DashboardCurveSnapshot,
    ) -> None:
        self.snapshots.append(snapshot)


class DashboardSinceTests(unittest.TestCase):
    def test_none_and_empty_string_disable_filter(self) -> None:
        self.assertIsNone(parse_dashboard_since(None))
        self.assertIsNone(parse_dashboard_since(""))

    def test_iso_date_is_inclusive_midnight(self) -> None:
        self.assertEqual(
            parse_dashboard_since("2026-01-01"),
            datetime(2026, 1, 1),
        )

    def test_invalid_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "DASHBOARD_CURVES_SINCE"):
            parse_dashboard_since("kein-datum")


class DashboardCurveReporterTests(unittest.TestCase):
    def test_refresh_forwards_filters_and_publishes_snapshot(self) -> None:
        curves = (
            make_curve((20, 30), start=datetime(2026, 1, 1)),
            make_curve((30, 50), start=datetime(2026, 1, 2)),
        )
        calls: list[dict[str, object]] = []

        def load_curves(
            directory: Path,
            *,
            since: datetime | None,
            include_warnings: bool,
        ) -> BurnCurveLoadResult:
            calls.append(
                {
                    "directory": directory,
                    "since": since,
                    "include_warnings": include_warnings,
                }
            )
            return BurnCurveLoadResult(curves=curves, issues=())

        publisher = FakePublisher()
        messages: list[str] = []
        reporter = DashboardCurveReporter(
            history_directory=Path("data/history"),
            publisher=publisher,
            since=datetime(2026, 1, 1),
            include_warnings=False,
            logger=messages.append,
            now=lambda: datetime(2026, 7, 14, tzinfo=timezone.utc),
            curve_loader=load_curves,
        )

        snapshot = reporter.refresh()

        self.assertIsNotNone(snapshot)
        self.assertEqual(publisher.snapshots, [snapshot])
        self.assertEqual(
            calls,
            [
                {
                    "directory": Path("data/history"),
                    "since": datetime(2026, 1, 1),
                    "include_warnings": False,
                }
            ],
        )
        self.assertTrue(any("2 Abbrände" in item for item in messages))

    def test_empty_history_is_logged_without_publication(self) -> None:
        publisher = FakePublisher()
        messages: list[str] = []
        reporter = DashboardCurveReporter(
            history_directory=Path("data/history"),
            publisher=publisher,
            logger=messages.append,
            curve_loader=lambda directory, **kwargs: BurnCurveLoadResult(
                curves=(),
                issues=(),
            ),
        )

        result = reporter.refresh()

        self.assertIsNone(result)
        self.assertEqual(publisher.snapshots, [])
        self.assertTrue(any("keine passenden" in item for item in messages))

    def test_only_damaged_files_keep_retained_snapshot_unchanged(self) -> None:
        issue = HistoryReadIssue(
            path=Path("data/history/broken.json"),
            message="ungültiges JSON",
        )
        publisher = FakePublisher()
        messages: list[str] = []
        reporter = DashboardCurveReporter(
            history_directory=Path("data/history"),
            publisher=publisher,
            logger=messages.append,
            curve_loader=lambda directory, **kwargs: BurnCurveLoadResult(
                curves=(),
                issues=(issue,),
            ),
        )

        result = reporter.refresh()

        self.assertIsNone(result)
        self.assertEqual(publisher.snapshots, [])
        self.assertTrue(
            any("broken.json" in message for message in messages)
        )
        self.assertTrue(
            any("retained Werte" in message for message in messages)
        )

    def test_invalid_warning_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "boolesch"):
            DashboardCurveReporter(
                history_directory=Path("data/history"),
                publisher=FakePublisher(),
                include_warnings="ja",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
