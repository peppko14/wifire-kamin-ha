#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.archive."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from bridge.archive import (
    ArchiveReader,
    build_archive_attributes,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ArchiveReaderTests(unittest.TestCase):
    def test_read_raw_sends_expected_post_request(self) -> None:
        requests: list[tuple[Any, int]] = []

        def opener(request: Any, *, timeout: int) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse({"raw": "aacc3355"})

        reader = ArchiveReader(
            archive_url="http://192.168.0.1/direct/35",
            request_timeout=17,
            opener=opener,
        )

        raw = reader.read_raw("aacc3355023501ffff")

        self.assertEqual(raw, "aacc3355")
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 17)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "http://192.168.0.1/direct/35",
        )
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"raw": "aacc3355023501ffff"},
        )

    def test_failed_request_is_retried(self) -> None:
        attempts = 0
        sleeps: list[int | float] = []
        messages: list[str] = []

        def opener(request: Any, *, timeout: int) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("temporär nicht erreichbar")
            return FakeResponse({"raw": "aacc3355"})

        reader = ArchiveReader(
            archive_url="http://192.168.0.1/direct/35",
            retry_count=3,
            retry_delay=5,
            sleeper=sleeps.append,
            opener=opener,
            logger=messages.append,
        )

        self.assertEqual(reader.read_raw("00"), "aacc3355")
        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [5])
        self.assertEqual(len(messages), 1)
        self.assertIn("Archivversuch 1/3", messages[0])

    def test_all_failed_requests_raise_runtime_error(self) -> None:
        def opener(request: Any, *, timeout: int) -> FakeResponse:
            raise OSError("nicht erreichbar")

        reader = ArchiveReader(
            archive_url="http://192.168.0.1/direct/35",
            retry_count=2,
            retry_delay=0,
            sleeper=lambda seconds: None,
            opener=opener,
            logger=lambda message: None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "nach 2 Versuchen",
        ):
            reader.read_raw("00")

    def test_read_record_uses_decoder(self) -> None:
        decoded = object()
        decoder_inputs: list[str] = []

        def decoder(raw: str) -> object:
            decoder_inputs.append(raw)
            return decoded

        reader = ArchiveReader(
            archive_url="http://192.168.0.1/direct/35",
            opener=lambda request, timeout: FakeResponse(
                {"raw": "aacc3355"}
            ),
            decoder=decoder,
        )

        self.assertIs(reader.read_record("00"), decoded)
        self.assertEqual(decoder_inputs, ["aacc3355"])

    def test_build_archive_attributes_preserves_payload(self) -> None:
        record = SimpleNamespace(
            archive_number=3,
            timestamp=datetime(2026, 4, 11, 2, 21),
            measurement_count=121,
            start_temperature_c=48,
            end_temperature_c=272,
            max_temperature_c=620,
            max_temperature_minute=30,
            stage_90_minute=2,
            stage_75_minute=41,
            stage_50_minute=51,
            stage_25_minute=104,
            stage_0_minute=164,
            temperatures=[48, 69, 119],
        )

        attributes = build_archive_attributes(record)

        self.assertEqual(attributes["archive_number"], 3)
        self.assertEqual(attributes["start"], "2026-04-11T02:21")
        self.assertEqual(attributes["max_temperature_c"], 620)
        self.assertEqual(attributes["duration_minutes"], 164)
        self.assertEqual(
            attributes["duration_source"],
            "stage_0_unwrapped",
        )
        self.assertEqual(
            attributes["temperatures_c"],
            [48, 69, 119],
        )


if __name__ == "__main__":
    unittest.main()
