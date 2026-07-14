# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from history.storage import HistoryStorage
from protocol.models import BurnRecord
from tools.burn_curve_export_v1_0_0 import main, parse_since


class BurnCurveExportToolTests(unittest.TestCase):
    def save_curve(
        self,
        directory: Path,
        *,
        start: datetime,
        temperatures: tuple[int, ...],
        archive_number: int,
    ) -> None:
        HistoryStorage(directory).save(
            BurnRecord(
                start=start,
                temperatures_c=temperatures,
                source_archive_number=archive_number,
                stage_0_minute=120,
            )
        )

    def test_since_accepts_date_and_datetime(self) -> None:
        self.assertEqual(parse_since("2026-01-01"), datetime(2026, 1, 1))
        self.assertEqual(
            parse_since("2026-01-01T12:30:00"),
            datetime(2026, 1, 1, 12, 30),
        )

    def test_main_exports_real_history_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history"
            target = root / "exports" / "curves.json"
            self.save_curve(
                history,
                start=datetime(2026, 1, 1),
                temperatures=(20, 100, 200),
                archive_number=1,
            )
            self.save_curve(
                history,
                start=datetime(2026, 1, 2),
                temperatures=(30, 110, 210),
                archive_number=2,
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "--history-dir",
                    str(history),
                    "--output",
                    str(target),
                ])

            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["source_curve_count"], 2)
        self.assertIn("Exportierte Kurven:       2", output.getvalue())

    def test_main_forwards_since_filter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history"
            target = root / "curves.json"
            self.save_curve(
                history,
                start=datetime(2025, 1, 1),
                temperatures=(20, 100),
                archive_number=1,
            )
            self.save_curve(
                history,
                start=datetime(2026, 1, 1),
                temperatures=(30, 110),
                archive_number=2,
            )

            with redirect_stdout(StringIO()):
                exit_code = main([
                    "--history-dir",
                    str(history),
                    "--output",
                    str(target),
                    "--since",
                    "2026-01-01",
                ])
            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["source_curve_count"], 1)
        self.assertEqual(payload["filters"]["since"], "2026-01-01T00:00:00")

    def test_main_reports_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history"
            target = root / "curves.json"
            self.save_curve(
                history,
                start=datetime(2026, 1, 1),
                temperatures=(20, 100),
                archive_number=1,
            )
            target.write_text("existing", encoding="utf-8")
            error_output = StringIO()

            with redirect_stderr(error_output):
                exit_code = main([
                    "--history-dir",
                    str(history),
                    "--output",
                    str(target),
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("existiert bereits", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
