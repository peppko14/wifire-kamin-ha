# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für das lesende Statistikwerkzeug."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from history.statistics import HistoryStatistics
from history.storage import HistoryStorage
from protocol.models import BurnRecord
from tools.history_statistics_v1_0_0 import (
    format_report,
    load_statistics,
    main,
)


class HistoryStatisticsToolTests(unittest.TestCase):
    def save_record(self, directory: Path) -> None:
        storage = HistoryStorage(directory)
        storage.save(
            BurnRecord(
                start=datetime(2026, 1, 1, 20, 0),
                temperatures_c=(24, 100, 400, 80),
                source_archive_number=1,
            )
        )

    def test_load_statistics_reads_real_history_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_record(path)

            statistics = load_statistics(path)

            self.assertEqual(statistics.burn_count, 1)
            self.assertEqual(statistics.highest_temperature_c, 400)
            self.assertEqual(statistics.total_duration_minutes, 4)

    def test_report_contains_core_values(self) -> None:
        statistics = HistoryStatistics(
            burn_count=2,
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

        self.assertIn("Gespeicherte Abbrände:       2", report)
        self.assertIn("Höchste Temperatur:          500 °C", report)
        self.assertIn("Durchschnittliche Dauer:     120.0 min", report)

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
            self.assertIn("Gespeicherte Abbrände:       0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
