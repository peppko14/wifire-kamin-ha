# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den lokalen Historien-Importer."""

import unittest
from unittest.mock import patch

from tools.history_importer_v1_0_2 import (
    build_archive_command,
    read_archive,
)


class HistoryImporterTests(unittest.TestCase):
    def test_archive_command_is_built_correctly(self) -> None:
        self.assertEqual(
            build_archive_command(1),
            "aacc3355023501ffff",
        )
        self.assertEqual(
            build_archive_command(23),
            "aacc3355023517ffff",
        )

    def test_invalid_archive_number_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_archive_command(0)

        with self.assertRaises(ValueError):
            build_archive_command(256)

    def test_oserror_is_retried(self) -> None:
        with (
            patch(
                "tools.history_importer_v1_0_2.urlopen",
                side_effect=OSError("Netzwerkfehler"),
            ) as opener,
            patch("tools.history_importer_v1_0_2.time.sleep") as sleeper,
        ):
            with self.assertRaises(RuntimeError):
                read_archive(1, retries=2, retry_delay=0.25)

        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once_with(0.25)

    def test_invalid_payload_is_reported_as_read_failure(self) -> None:
        with patch("tools.history_importer_v1_0_2.urlopen") as opener:
            response = opener.return_value.__enter__.return_value
            response.read.return_value = b"{}"

            with self.assertRaises(RuntimeError):
                read_archive(1, retries=1, retry_delay=0)

        opener.assert_called_once()

    def test_programming_error_is_not_retried(self) -> None:
        with patch(
            "tools.history_importer_v1_0_2.urlopen",
            side_effect=AttributeError("Programmierfehler"),
        ) as opener:
            with self.assertRaises(AttributeError):
                read_archive(1, retries=3, retry_delay=0)

        opener.assert_called_once()


if __name__ == "__main__":
    unittest.main()
