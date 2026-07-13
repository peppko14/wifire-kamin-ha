# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die automatische Archiv-Synchronisation."""

import unittest

from history.sync import (
    ArchiveSyncSettings,
    build_archive_command,
    build_archive_url,
)


class ArchiveSyncTests(unittest.TestCase):
    def test_archive_url_is_derived_from_live_url(self) -> None:
        self.assertEqual(
            build_archive_url(
                "http://192.168.0.1/direct/00"
            ),
            "http://192.168.0.1/direct/35",
        )

    def test_archive_url_preserves_host_and_port(self) -> None:
        self.assertEqual(
            build_archive_url(
                "http://wifire.local:8080/direct/00"
            ),
            "http://wifire.local:8080/direct/35",
        )

    def test_invalid_live_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_archive_url("192.168.0.1/direct/00")

    def test_non_direct_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_archive_url(
                "http://192.168.0.1/status/00"
            )

    def test_archive_command_is_correct(self) -> None:
        self.assertEqual(
            build_archive_command(1),
            "aacc3355023501ffff",
        )
        self.assertEqual(
            build_archive_command(23),
            "aacc3355023517ffff",
        )

    def test_settings_reject_invalid_range(self) -> None:
        settings = ArchiveSyncSettings(
            live_url="http://192.168.0.1/direct/00",
            first_archive=23,
            last_archive=1,
        )

        with self.assertRaises(ValueError):
            settings.validate()

    def test_settings_accept_known_stable_delays(self) -> None:
        settings = ArchiveSyncSettings(
            live_url="http://192.168.0.1/direct/00",
            retry_delay_seconds=10,
            archive_delay_seconds=10,
        )

        settings.validate()


if __name__ == "__main__":
    unittest.main()
