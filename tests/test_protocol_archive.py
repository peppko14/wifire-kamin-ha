# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die gemeinsame, ausschließlich lesende Archivschnittstelle."""

from __future__ import annotations

import json
import unittest
from typing import Any
from urllib.request import Request

from protocol.archive import (
    ArchiveClient,
    ArchiveReadCancelled,
    ArchiveReadError,
    build_archive_command,
    build_archive_request,
    build_archive_url,
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def json_response(value: object) -> FakeResponse:
    return FakeResponse(json.dumps(value).encode("utf-8"))


class ArchiveProtocolTests(unittest.TestCase):
    def test_archive_url_is_derived_from_live_url(self) -> None:
        self.assertEqual(
            build_archive_url("http://192.168.0.1/direct/00"),
            "http://192.168.0.1/direct/35",
        )

    def test_archive_url_preserves_host_and_port(self) -> None:
        self.assertEqual(
            build_archive_url("http://wifire.local:8080/direct/00"),
            "http://wifire.local:8080/direct/35",
        )

    def test_invalid_live_urls_are_rejected(self) -> None:
        for value in (
            "192.168.0.1/direct/00",
            "http://192.168.0.1/status/00",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_archive_url(value)

    def test_archive_command_supports_the_full_byte_range(self) -> None:
        self.assertEqual(build_archive_command(1), "aacc3355023501ffff")
        self.assertEqual(build_archive_command(23), "aacc3355023517ffff")
        self.assertEqual(build_archive_command(255), "aacc33550235ffffff")

    def test_invalid_archive_numbers_are_rejected(self) -> None:
        for value in (0, 256, True, 1.0, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_archive_command(value)  # type: ignore[arg-type]

    def test_request_contains_only_the_known_read_command(self) -> None:
        request = build_archive_request(
            "http://192.168.0.1/direct/35",
            23,
        )

        self.assertEqual(request.full_url, "http://192.168.0.1/direct/35")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Content-type"), "text/plain")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Connection"), "close")
        self.assertEqual(
            json.loads((request.data or b"").decode("utf-8")),
            {"raw": "aacc3355023517ffff"},
        )

    def test_client_reads_and_validates_raw_hex(self) -> None:
        calls: list[tuple[Request, int]] = []

        def opener(request: Request, *, timeout: int) -> FakeResponse:
            calls.append((request, timeout))
            return json_response({"raw": "aacc3355"})

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            request_timeout=12,
            opener=opener,
        )

        self.assertEqual(client.archive_url, "http://192.168.0.1/direct/35")
        self.assertEqual(client.read_raw(23), "aacc3355")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 12)

    def test_transient_transport_error_is_retried(self) -> None:
        attempts = 0
        sleeps: list[int | float] = []
        messages: list[str] = []

        def opener(request: Request, *, timeout: int) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("kurzer WLAN-Aussetzer")
            return json_response({"raw": "aacc3355"})

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            retry_count=2,
            retry_delay_seconds=4,
            sleeper=sleeps.append,
            opener=opener,
            logger=messages.append,
        )

        self.assertEqual(client.read_raw(1), "aacc3355")
        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [4])
        self.assertTrue(any("Versuch 1/2" in item for item in messages))

    def test_stop_before_first_attempt_prevents_http_request(self) -> None:
        calls = 0

        def opener(request: Request, *, timeout: int) -> FakeResponse:
            nonlocal calls
            calls += 1
            return json_response({"raw": "aacc3355"})

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            opener=opener,
            is_running=lambda: False,
        )

        with self.assertRaisesRegex(
            ArchiveReadCancelled,
            "vor Versuch 1",
        ):
            client.read_raw(1)

        self.assertEqual(calls, 0)

    def test_stop_during_retry_delay_prevents_next_attempt(self) -> None:
        running = True
        attempts = 0
        sleeps: list[int | float] = []

        def opener(request: Request, *, timeout: int) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            raise TimeoutError("kurzer WLAN-Aussetzer")

        def stop_during_sleep(seconds: int | float) -> None:
            nonlocal running
            sleeps.append(seconds)
            running = False

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            retry_count=3,
            retry_delay_seconds=10,
            sleeper=stop_during_sleep,
            opener=opener,
            logger=lambda message: None,
            is_running=lambda: running,
        )

        with self.assertRaisesRegex(
            ArchiveReadCancelled,
            "Retry-Wartezeit",
        ):
            client.read_raw(1)

        self.assertEqual(attempts, 1)
        self.assertEqual(sleeps, [10])

    def test_invalid_responses_fail_after_all_attempts(self) -> None:
        invalid_payloads: tuple[Any, ...] = (
            [],
            {},
            {"raw": 123},
            {"raw": ""},
            {"raw": "kein-hex"},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                calls = 0

                def opener(
                    request: Request,
                    *,
                    timeout: int,
                ) -> FakeResponse:
                    nonlocal calls
                    calls += 1
                    return json_response(payload)

                client = ArchiveClient(
                    "http://192.168.0.1/direct/00",
                    retry_count=2,
                    retry_delay_seconds=0,
                    sleeper=lambda seconds: None,
                    opener=opener,
                    logger=lambda message: None,
                )

                with self.assertRaises(ArchiveReadError):
                    client.read_raw(1)
                self.assertEqual(calls, 2)

    def test_invalid_archive_number_is_not_retried(self) -> None:
        calls = 0

        def opener(request: Request, *, timeout: int) -> FakeResponse:
            nonlocal calls
            calls += 1
            return json_response({"raw": "aacc3355"})

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            opener=opener,
        )

        with self.assertRaises(ValueError):
            client.read_raw(0)
        self.assertEqual(calls, 0)

    def test_programming_errors_are_not_masked_as_transport_errors(self) -> None:
        def opener(request: Request, *, timeout: int) -> FakeResponse:
            raise AttributeError("Programmierfehler")

        client = ArchiveClient(
            "http://192.168.0.1/direct/00",
            opener=opener,
        )

        with self.assertRaises(AttributeError):
            client.read_raw(1)

    def test_invalid_client_settings_are_rejected(self) -> None:
        invalid_settings: tuple[dict[str, object], ...] = (
            {"request_timeout": 0},
            {"retry_count": 0},
            {"retry_delay_seconds": -1},
            {"request_timeout": True},
            {"retry_count": True},
            {"retry_delay_seconds": True},
        )

        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(
                ValueError
            ):
                ArchiveClient(
                    "http://192.168.0.1/direct/00",
                    **settings,  # type: ignore[arg-type]
                )


if __name__ == "__main__":
    unittest.main()
