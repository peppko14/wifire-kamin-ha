# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den adaptiven lokalen Historien-Importer."""

from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, MagicMock, patch

from history.manager import HistorySyncResult
from protocol.archive import ArchiveClient
import tools.history_importer_v1_1_0 as importer


def empty_record(number: int) -> SimpleNamespace:
    return SimpleNamespace(
        archive_number=number,
        timestamp=None,
        stage_90_minute=None,
        stage_75_minute=None,
        stage_50_minute=None,
        stage_25_minute=None,
        stage_0_minute=None,
        temperatures=[],
        active_or_incomplete=True,
        raw="aacc3355",
    )


def manager() -> MagicMock:
    value = MagicMock()
    value.storage.directory = "/tmp/history"
    value.synchronize.return_value = HistorySyncResult((), (), 0, 0)
    return value


class HistoryImporterTests(unittest.TestCase):
    def test_client_uses_shared_read_only_archive_transport(self) -> None:
        client = importer.create_archive_client(
            retries=4,
            retry_delay=10,
        )

        self.assertIsInstance(client, ArchiveClient)
        self.assertEqual(client.live_url, importer.WIFIRE_LIVE_URL)
        self.assertEqual(client.request_timeout, importer.REQUEST_TIMEOUT)
        self.assertEqual(client.retry_count, 4)
        self.assertEqual(client.retry_delay_seconds, 10)

    def test_factory_delegates_configuration_to_archive_client(self) -> None:
        with patch.object(importer, "ArchiveClient") as client_type:
            importer.create_archive_client(retries=2, retry_delay=10)

        client_type.assert_called_once_with(
            live_url=importer.WIFIRE_LIVE_URL,
            request_timeout=importer.REQUEST_TIMEOUT,
            retry_count=2,
            retry_delay_seconds=10,
            logger=ANY,
        )

    def test_default_range_uses_technical_limit(self) -> None:
        with patch("sys.argv", ["history_importer"]):
            args = importer.parse_args()

        self.assertEqual(args.first, 1)
        self.assertEqual(args.last, 255)
        self.assertEqual(args.delay, 10)

    def test_first_empty_slot_stops_without_history_diagnostic(self) -> None:
        archive_client = MagicMock()
        archive_client.read_raw.return_value = "raw"
        history_manager = manager()

        with (
            patch.object(
                importer,
                "parse_args",
                return_value=Namespace(
                    first=24,
                    last=30,
                    delay=10,
                    retries=1,
                ),
            ),
            patch.object(
                importer,
                "create_archive_client",
                return_value=archive_client,
            ),
            patch.object(
                importer,
                "create_default_history_manager",
                return_value=history_manager,
            ),
            patch.object(
                importer,
                "decode_archive_record",
                return_value=empty_record(24),
            ),
            patch.object(importer, "archive_record_to_burn_record") as adapter,
            patch.object(importer.time, "sleep") as sleeper,
            patch("builtins.print"),
        ):
            importer.main()

        archive_client.read_raw.assert_called_once_with(24)
        adapter.assert_not_called()
        history_manager.synchronize.assert_called_once_with([])
        sleeper.assert_not_called()

    def test_three_consecutive_read_errors_stop_the_import(self) -> None:
        archive_client = MagicMock()
        archive_client.read_raw.side_effect = RuntimeError("offline")
        history_manager = manager()

        with (
            patch.object(
                importer,
                "parse_args",
                return_value=Namespace(
                    first=1,
                    last=10,
                    delay=10,
                    retries=1,
                ),
            ),
            patch.object(
                importer,
                "create_archive_client",
                return_value=archive_client,
            ),
            patch.object(
                importer,
                "create_default_history_manager",
                return_value=history_manager,
            ),
            patch.object(importer.time, "sleep") as sleeper,
            patch("builtins.print"),
        ):
            importer.main()

        self.assertEqual(
            [call.args[0] for call in archive_client.read_raw.call_args_list],
            [1, 2, 3],
        )
        self.assertEqual(sleeper.call_count, 2)
        history_manager.synchronize.assert_called_once_with([])


if __name__ == "__main__":
    unittest.main()
