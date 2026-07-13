# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den lokalen Historien-Importer."""

import unittest

from tools.history_importer_v1_0_1 import build_archive_command


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


if __name__ == "__main__":
    unittest.main()
