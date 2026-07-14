# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from history.curves import (
    SAMPLE_AXIS,
    BurnCurve,
    BurnCurveError,
    CurvePoint,
    curve_from_history_record,
    load_burn_curves,
)
from history.storage import HistoryStorage
from protocol.models import BurnRecord


class HistoryCurvesTests(unittest.TestCase):
    def build_record(
        self,
        *,
        start: datetime = datetime(2026, 4, 22, 21, 23),
        temperatures: tuple[int, ...] = (22, 24, 30, 453, 205),
        archive_number: int = 1,
    ) -> BurnRecord:
        return BurnRecord(
            start=start,
            temperatures_c=temperatures,
            source_archive_number=archive_number,
            stage_90_minute=7,
            stage_75_minute=36,
            stage_50_minute=57,
            stage_25_minute=109,
            stage_0_minute=169,
        )

    def build_payload(self, record: BurnRecord | None = None) -> dict[str, object]:
        storage = HistoryStorage(Path("unused"))
        return storage.serialize_record(record or self.build_record())

    def test_curve_point_is_immutable(self) -> None:
        point = CurvePoint(sample_index=0, temperature_c=24)

        with self.assertRaises(FrozenInstanceError):
            point.temperature_c = 25  # type: ignore[misc]

    def test_curve_point_rejects_invalid_values(self) -> None:
        invalid = ((-1, 20), (True, 20), (0, True), (0, 1201))

        for sample_index, temperature in invalid:
            with self.subTest(
                sample_index=sample_index,
                temperature=temperature,
            ):
                with self.assertRaises(BurnCurveError):
                    CurvePoint(sample_index, temperature)

    def test_curve_properties_use_sample_indices(self) -> None:
        curve = curve_from_history_record(self.build_payload())

        self.assertEqual(curve.sample_count, 5)
        self.assertEqual(curve.temperatures_c, (22, 24, 30, 453, 205))
        self.assertEqual(curve.max_temperature_c, 453)
        self.assertEqual(curve.max_temperature_sample_index, 3)
        self.assertEqual(curve.to_dict()["sample_axis"], SAMPLE_AXIS)
        self.assertEqual(curve.to_dict()["sample_count"], 5)

    def test_curve_is_immutable(self) -> None:
        curve = curve_from_history_record(self.build_payload())

        with self.assertRaises(FrozenInstanceError):
            curve.quality_status = "valid"  # type: ignore[misc]

    def test_curve_rejects_non_contiguous_indices(self) -> None:
        payload = self.build_payload()
        curve = curve_from_history_record(payload)
        points = (
            CurvePoint(0, 22),
            CurvePoint(2, 24),
        )

        with self.assertRaisesRegex(BurnCurveError, "zusammenhängend"):
            BurnCurve(
                burn_id=curve.burn_id,
                start=curve.start,
                points=points,
                quality_status="valid",
            )

    def test_curve_model_rejects_mismatching_burn_id(self) -> None:
        curve = curve_from_history_record(self.build_payload())

        with self.assertRaisesRegex(BurnCurveError, "burn_id"):
            BurnCurve(
                burn_id="0" * 64,
                start=curve.start,
                points=curve.points,
                quality_status=curve.quality_status,
                warning_codes=curve.warning_codes,
            )

    def test_warning_codes_are_preserved(self) -> None:
        curve = curve_from_history_record(self.build_payload())

        self.assertEqual(curve.quality_status, "warning")
        self.assertEqual(
            curve.warning_codes,
            ("measurement_count_unexpected",),
        )

    def test_wrong_schema_is_rejected(self) -> None:
        payload = self.build_payload()
        payload["schema_version"] = 1

        with self.assertRaisesRegex(BurnCurveError, "Schema"):
            curve_from_history_record(payload)

    def test_incomplete_record_is_rejected(self) -> None:
        payload = self.build_payload()
        payload["active_or_incomplete"] = True

        with self.assertRaisesRegex(BurnCurveError, "Unvollständiger"):
            curve_from_history_record(payload)

    def test_wrong_burn_id_is_rejected(self) -> None:
        payload = self.build_payload()
        payload["burn_id"] = "0" * 64

        with self.assertRaisesRegex(BurnCurveError, "burn_id"):
            curve_from_history_record(payload)

    def test_inconsistent_derived_fields_are_rejected(self) -> None:
        fields = (
            "measurement_count",
            "start_temperature_c",
            "end_temperature_c",
            "max_temperature_c",
            "max_temperature_minute",
        )

        for field in fields:
            with self.subTest(field=field):
                payload = self.build_payload()
                payload[field] = 999
                with self.assertRaisesRegex(BurnCurveError, field):
                    curve_from_history_record(payload)

    def test_temperature_outside_quality_range_is_rejected(self) -> None:
        payload = self.build_payload()
        payload["temperatures_c"] = [22, 1300]
        payload["measurement_count"] = 2

        with self.assertRaisesRegex(BurnCurveError, "Messpunkt 1"):
            curve_from_history_record(payload)

    def test_load_curves_sorts_and_filters_by_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            storage.save(
                self.build_record(start=datetime(2026, 2, 1, 10, 0))
            )
            storage.save(
                self.build_record(
                    start=datetime(2026, 4, 1, 10, 0),
                    temperatures=(25, 100, 300),
                    archive_number=2,
                )
            )

            curves = load_burn_curves(
                Path(directory),
                since=datetime(2026, 3, 1),
            )

        self.assertEqual(len(curves), 1)
        self.assertEqual(curves[0].start, datetime(2026, 4, 1, 10, 0))

    def test_load_curves_can_exclude_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = HistoryStorage(Path(directory))
            storage.save(self.build_record())

            curves = load_burn_curves(
                Path(directory),
                include_warnings=False,
            )

        self.assertEqual(curves, ())

    def test_load_curves_reports_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.json"
            path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

            with self.assertRaisesRegex(BurnCurveError, "corrupt.json"):
                load_burn_curves(Path(directory))


if __name__ == "__main__":
    unittest.main()
