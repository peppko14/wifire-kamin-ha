# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from history.curve_analysis import analyze_curves
from history.curve_export import (
    CURVE_EXPORT_SCHEMA_VERSION,
    CurveExportError,
    build_curve_export,
    write_curve_export,
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


class CurveExportTests(unittest.TestCase):
    def build_analysis(self):
        curves = (
            make_curve((10, 20, 30), start=datetime(2026, 1, 1)),
            make_curve((20, 30, 40), start=datetime(2026, 1, 2)),
        )
        return analyze_curves(
            curves,
            since=datetime(2026, 1, 1),
            include_warnings=False,
        )

    def test_export_contains_portable_schema_and_all_curves(self) -> None:
        payload = build_curve_export(
            self.build_analysis(),
            generated_at=datetime(2026, 7, 14, tzinfo=UTC),
        )

        self.assertEqual(payload["schema_version"], CURVE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(payload["sample_axis"], "sample_index")
        self.assertEqual(payload["source_curve_count"], 2)
        self.assertEqual(len(payload["curves"]), 2)
        self.assertEqual(
            payload["generated_at"],
            "2026-07-14T00:00:00+00:00",
        )

    def test_export_contains_average_and_references(self) -> None:
        payload = build_curve_export(self.build_analysis())

        self.assertEqual(
            payload["average_curve"]["points"][0][
                "average_temperature_c"
            ],
            15.0,
        )
        self.assertIn(
            "rmse_to_average_c",
            payload["representative_curve"],
        )
        self.assertEqual(
            payload["hottest_curve"]["max_temperature_c"],
            40,
        )

    def test_export_records_filters(self) -> None:
        payload = build_curve_export(self.build_analysis())

        self.assertEqual(payload["filters"]["since"], "2026-01-01T00:00:00")
        self.assertFalse(payload["filters"]["include_warnings"])

    def test_write_export_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "export" / "curves.json"

            result = write_curve_export(self.build_analysis(), target)
            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(result, target.resolve())
        self.assertEqual(payload["source_curve_count"], 2)

    def test_write_refuses_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "curves.json"
            write_curve_export(self.build_analysis(), target)

            with self.assertRaisesRegex(CurveExportError, "existiert bereits"):
                write_curve_export(self.build_analysis(), target)

    def test_write_can_replace_file_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "curves.json"
            target.write_text("old", encoding="utf-8")

            write_curve_export(
                self.build_analysis(),
                target,
                overwrite=True,
            )

            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(target.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
