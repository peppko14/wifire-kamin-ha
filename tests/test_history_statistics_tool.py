# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für das lesende Statistikwerkzeug."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from history.statistics import HistoryStatistics
from history.storage import HistoryStorage
from protocol.models import BurnRecord
from tools.history_statistics_v1_2_0 import (
    format_monthly_report,
    format_report,
    format_season_report,
    load_statistics,
    main,
    parse_since,
)


class HistoryStatisticsToolTests(unittest.TestCase):
    def save_record(
        self,
        directory: Path,
        *,
        start: datetime = datetime(2026, 1, 1, 20, 0),
        maximum: int = 400,
    ) -> None:
        storage = HistoryStorage(directory)
        storage.save(
            BurnRecord(
                start=start,
                temperatures_c=(24, 100, maximum, 80),
                source_archive_number=1,
                stage_90_minute=10,
                stage_75_minute=40,
                stage_50_minute=80,
                stage_25_minute=120,
                stage_0_minute=180,
            )
        )

    def test_load_statistics_reads_real_history_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)

            statistics = load_statistics(path)

            self.assertEqual(statistics.burn_count, 1)
            self.assertEqual(statistics.highest_temperature_c, 400)
            self.assertEqual(statistics.total_duration_minutes, 180)

    def test_report_contains_core_values(self) -> None:
        statistics = HistoryStatistics(
            source_record_count=2,
            burn_count=2,
            excluded_record_count=0,
            duration_record_count=2,
            first_burn_start=datetime(2026, 1, 1, 20, 0),
            latest_burn_start=datetime(2026, 1, 3, 21, 0),
            total_duration_minutes=240,
            average_duration_minutes=120.0,
            average_max_temperature_c=450.0,
            highest_temperature_c=500,
            highest_temperature_start=datetime(2026, 1, 3, 21, 0),
            average_start_temperature_c=26.0,
            average_end_temperature_c=90.0,
        )

        report = format_report(statistics)

        self.assertIn("Gespeicherte Datensätze:      2", report)
        self.assertIn("Berücksichtigte Abbrände:     2", report)
        self.assertIn("Höchste Temperatur:          500 °C", report)
        self.assertIn("Mittlere Abbrenndauer:       120.0 min", report)

    def test_json_mode_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main(["--history-dir", str(path), "--json"])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["burn_count"], 1)
            self.assertEqual(payload["highest_temperature_c"], 400)

    def test_empty_directory_produces_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main(["--history-dir", directory])

            self.assertEqual(exit_code, 0)
            self.assertIn("Berücksichtigte Abbrände:     0", output.getvalue())

    def test_since_filter_is_forwarded_to_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(path),
                    "--since",
                    "2027-01-01",
                    "--json",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["source_record_count"], 1)
            self.assertEqual(payload["burn_count"], 0)
            self.assertEqual(payload["excluded_record_count"], 1)

    def test_since_accepts_date_and_datetime(self) -> None:
        self.assertEqual(parse_since("2026-01-01"), datetime(2026, 1, 1))
        self.assertEqual(
            parse_since("2026-01-01T12:30:00"),
            datetime(2026, 1, 1, 12, 30),
        )

    def test_monthly_json_groups_records_by_calendar_month(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path, start=datetime(2026, 1, 10, 20, 0))
            self.save_record(path, start=datetime(2026, 2, 10, 20, 0))
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(path),
                    "--monthly",
                    "--json",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["group_by"], "month")
            self.assertEqual(
                [item["period"] for item in payload["periods"]],
                ["2026-01", "2026-02"],
            )

    def test_season_json_uses_july_to_june_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path, start=datetime(2026, 6, 30, 20, 0))
            self.save_record(path, start=datetime(2026, 7, 1, 20, 0))
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(path),
                    "--seasons",
                    "--json",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["group_by"], "heating_season")
            self.assertEqual(
                [item["label"] for item in payload["periods"]],
                ["2025/2026", "2026/2027"],
            )

    def test_monthly_text_report_contains_period_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(path),
                    "--monthly",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn("WiFire-Kamin Monatsstatistik", output.getvalue())
            self.assertIn("2026-01", output.getvalue())

    def test_season_text_report_contains_readable_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(path),
                    "--seasons",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn(
                "WiFire-Kamin Heizsaisonstatistik",
                output.getvalue(),
            )
            self.assertIn("2025/2026", output.getvalue())

    def test_empty_period_reports_are_explicit(self) -> None:
        self.assertIn(
            "Keine Abbrände",
            format_monthly_report(()),
        )
        self.assertIn(
            "Keine Abbrände",
            format_season_report(()),
        )

    def test_monthly_and_seasons_are_mutually_exclusive(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(["--monthly", "--seasons"])


if __name__ == "__main__":
    unittest.main()
