# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den lokalen Historien-Importer."""

from __future__ import annotations

import unittest
from unittest.mock import ANY, patch

from protocol.archive import ArchiveClient
from tools.history_importer_v1_0_3 import (
    REQUEST_TIMEOUT,
    WIFIRE_LIVE_URL,
    create_archive_client,
)


class HistoryImporterTests(unittest.TestCase):
    def test_client_uses_shared_read_only_archive_transport(self) -> None:
        client = create_archive_client(
            retries=4,
            retry_delay=2.5,
        )

        self.assertIsInstance(client, ArchiveClient)
        self.assertEqual(client.live_url, WIFIRE_LIVE_URL)
        self.assertEqual(client.request_timeout, REQUEST_TIMEOUT)
        self.assertEqual(client.retry_count, 4)
        self.assertEqual(client.retry_delay_seconds, 2.5)
        self.assertEqual(
            client.archive_url,
            "http://192.168.0.1/direct/35",
        )

    def test_factory_delegates_configuration_to_archive_client(self) -> None:
        with patch(
            "tools.history_importer_v1_0_3.ArchiveClient"
        ) as client_type:
            create_archive_client(retries=2, retry_delay=0.25)

        client_type.assert_called_once_with(
            live_url=WIFIRE_LIVE_URL,
            request_timeout=REQUEST_TIMEOUT,
            retry_count=2,
            retry_delay_seconds=0.25,
            logger=ANY,
        )


if __name__ == "__main__":
    unittest.main()
