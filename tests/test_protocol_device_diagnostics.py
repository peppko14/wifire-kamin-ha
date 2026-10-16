# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from types import TracebackType
from urllib.request import Request

from protocol.device_diagnostics import (
    ALARM_PACKET_LENGTH,
    DeviceDiagnosticsClient,
    build_direct_url,
    build_read_request,
    decode_alarm_list,
    decode_controller_time,
)


CLOCK_RAW = "aacc335506221a17110c39a900"


def build_alarm_raw(*records: bytes) -> str:
    data = bytearray(ALARM_PACKET_LENGTH)
    data[:7] = bytes.fromhex("aacc3355ffa604")
    start = ALARM_PACKET_LENGTH - 2 - 60
    for index, record in enumerate(records):
        if len(record) != 6:
            raise ValueError("Test-Alarmdatensatz muss sechs Bytes haben.")
        offset = start + index * 6
        data[offset : offset + 6] = record
    data[-2:] = bytes.fromhex("950a")
    return data.hex()


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class FakeOpener:
    def __init__(self, *results: bytes | OSError) -> None:
        self.results = list(results)
        self.calls: list[tuple[Request, int]] = []

    def __call__(self, request: Request, *, timeout: int) -> FakeResponse:
        self.calls.append((request, timeout))
        result = self.results.pop(0)
        if isinstance(result, OSError):
            raise result
        return FakeResponse(result)


class ControllerTimeDecoderTests(unittest.TestCase):
    def test_decodes_internal_controller_time(self) -> None:
        result = decode_controller_time(CLOCK_RAW)

        self.assertEqual(result.value, datetime(2026, 7, 17, 12, 57))
        self.assertEqual(result.month_flags, 0x10)
        self.assertEqual(
            result.to_dict(),
            {
                "value": "2026-07-17T12:57",
                "month_flags": 16,
            },
        )

    def test_rejects_wrong_clock_command(self) -> None:
        raw = bytearray.fromhex(CLOCK_RAW)
        raw[5] = 0x23

        with self.assertRaisesRegex(
            ValueError,
            "Unerwartetes Steuerungszeit-Telegramm",
        ):
            decode_controller_time(raw.hex())

    def test_rejects_invalid_clock_date(self) -> None:
        raw = bytearray.fromhex(CLOCK_RAW)
        raw[7] = 0x10

        with self.assertRaisesRegex(
            ValueError,
            "Ungültige Steuerungszeit",
        ):
            decode_controller_time(raw.hex())


class AlarmListDecoderTests(unittest.TestCase):
    def test_decodes_sorts_and_labels_alarm_entries(self) -> None:
        raw = build_alarm_raw(
            bytes.fromhex("110b0b010036"),
            bytes.fromhex("1a130501003a"),
            bytes.fromhex("11041707005c"),
        )

        result = decode_alarm_list(raw)

        self.assertEqual(len(result.entries), 3)
        self.assertEqual(result.entries[0].occurred_on, date(2026, 3, 5))
        self.assertEqual(result.entries[0].label, "Heizfehler")
        self.assertEqual(result.entries[1].occurred_on, date(2017, 11, 11))
        self.assertEqual(result.entries[2].occurred_on, date(2017, 4, 23))
        self.assertEqual(result.entries[2].label, "Unbekannter Alarm (7)")

    def test_empty_alarm_slots_are_ignored(self) -> None:
        result = decode_alarm_list(build_alarm_raw())

        self.assertEqual(result.entries, ())

    def test_invalid_alarm_date_is_preserved_as_unknown(self) -> None:
        result = decode_alarm_list(
            build_alarm_raw(bytes.fromhex("1a1f1f010012"))
        )

        self.assertIsNone(result.entries[0].occurred_on)
        self.assertEqual(result.entries[0].raw_record, "1a1f1f010012")

    def test_rejects_wrong_alarm_packet_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "Alarmtelegramm hat"):
            decode_alarm_list(build_alarm_raw()[:-2])


class DeviceDiagnosticsClientTests(unittest.TestCase):
    def test_builds_only_known_read_endpoints(self) -> None:
        self.assertEqual(
            build_direct_url("http://192.168.0.1/direct/00", "22"),
            "http://192.168.0.1/direct/22",
        )
        self.assertEqual(
            build_direct_url("http://192.168.0.1/direct/00", "04"),
            "http://192.168.0.1/direct/04",
        )
        with self.assertRaisesRegex(ValueError, "Nicht freigegebener"):
            build_direct_url("http://192.168.0.1/direct/00", "23")

    def test_request_is_get_without_body(self) -> None:
        request = build_read_request(
            "http://192.168.0.1/direct/00",
            "22",
        )

        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.full_url, "http://192.168.0.1/direct/22")

    def test_client_retries_transport_error(self) -> None:
        response = json.dumps({"raw": CLOCK_RAW}).encode("utf-8")
        opener = FakeOpener(OSError("kurzer Aussetzer"), response)
        sleeps: list[int | float] = []
        logs: list[str] = []
        client = DeviceDiagnosticsClient(
            live_url="http://192.168.0.1/direct/00",
            retry_count=2,
            retry_delay_seconds=3,
            opener=opener,
            sleeper=sleeps.append,
            logger=logs.append,
        )

        result = client.read_controller_time()

        self.assertEqual(result.value, datetime(2026, 7, 17, 12, 57))
        self.assertEqual(sleeps, [3])
        self.assertEqual(len(logs), 1)
        self.assertEqual(len(opener.calls), 2)
        self.assertTrue(
            all(call[0].get_method() == "GET" for call in opener.calls)
        )

    def test_client_reads_alarm_list(self) -> None:
        raw = build_alarm_raw(bytes.fromhex("1a130501003a"))
        response = json.dumps({"raw": raw}).encode("utf-8")
        opener = FakeOpener(response)
        client = DeviceDiagnosticsClient(
            live_url="http://192.168.0.1/direct/00",
            opener=opener,
        )

        result = client.read_alarms()

        self.assertEqual(result.entries[0].label, "Heizfehler")
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "http://192.168.0.1/direct/04")
        self.assertEqual(timeout, 5)


if __name__ == "__main__":
    unittest.main()
