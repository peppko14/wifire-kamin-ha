#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.device_diagnostics."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from bridge.device_diagnostics import (
    DeviceDiagnosticsReporter,
    build_controller_diagnostics_payload,
    build_heating_failures_payload,
)
from protocol.device_diagnostics import (
    AlarmEntry,
    AlarmList,
    ControllerTime,
    DeviceDiagnosticsReadError,
)


BERLIN_SUMMER = timezone(timedelta(hours=2))


def controller_time() -> ControllerTime:
    return ControllerTime(
        value=datetime(2026, 7, 17, 13, 28),
        month_flags=0x10,
        raw="aacc3355",
    )


def alarm_list() -> AlarmList:
    return AlarmList(
        entries=(
            AlarmEntry(
                occurred_on=date(2026, 3, 5),
                code=1,
                label="Heizfehler",
                value_byte=0,
                metadata_byte=0,
                raw_record="1a0305010000",
            ),
            AlarmEntry(
                occurred_on=date(2017, 11, 11),
                code=1,
                label="Heizfehler",
                value_byte=0,
                metadata_byte=0,
                raw_record="110b0b010000",
            ),
        ),
        raw="aacc3355",
    )


class FakeClient:
    def __init__(
        self,
        *,
        clock_error: Exception | None = None,
        alarm_error: Exception | None = None,
    ) -> None:
        self.clock_error = clock_error
        self.alarm_error = alarm_error
        self.calls: list[str] = []

    def read_controller_time(self) -> ControllerTime:
        self.calls.append("clock")
        if self.clock_error is not None:
            raise self.clock_error
        return controller_time()

    def read_alarms(self) -> AlarmList:
        self.calls.append("alarms")
        if self.alarm_error is not None:
            raise self.alarm_error
        return alarm_list()


class FakePublisher:
    def __init__(self) -> None:
        self.controller_payloads: list[dict[str, object]] = []
        self.alarm_payloads: list[dict[str, object]] = []

    def publish_controller_diagnostics(
        self,
        payload: dict[str, object],
    ) -> None:
        self.controller_payloads.append(payload)

    def publish_heating_failures(
        self,
        payload: dict[str, object],
    ) -> None:
        self.alarm_payloads.append(payload)


class DeviceDiagnosticsPayloadTests(unittest.TestCase):
    def test_controller_payload_contains_signed_time_offset(self) -> None:
        payload = build_controller_diagnostics_payload(
            controller_time(),
            datetime(2026, 7, 17, 14, 19, 24, tzinfo=BERLIN_SUMMER),
        )

        self.assertEqual(
            payload["controller_time"],
            "2026-07-17T13:28+02:00",
        )
        self.assertEqual(payload["offset_minutes"], -51.4)
        self.assertEqual(payload["month_flags"], 0x10)

    def test_alarm_payload_omits_raw_protocol_bytes(self) -> None:
        payload = build_heating_failures_payload(
            alarm_list(),
            datetime(2026, 7, 17, 14, 20, tzinfo=BERLIN_SUMMER),
        )

        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["latest_date"], "2026-03-05")
        self.assertEqual(
            payload["entries"][0],
            {
                "occurred_on": "2026-03-05",
                "code": 1,
                "label": "Heizfehler",
            },
        )


class DeviceDiagnosticsReporterTests(unittest.TestCase):
    def test_both_diagnostics_are_published_with_request_pause(self) -> None:
        client = FakeClient()
        publisher = FakePublisher()
        sleeps: list[int | float] = []
        reporter = DeviceDiagnosticsReporter(
            client=client,
            publisher=publisher,
            request_delay_seconds=2,
            sleeper=sleeps.append,
            clock=lambda: datetime(
                2026,
                7,
                17,
                14,
                19,
                24,
                tzinfo=BERLIN_SUMMER,
            ),
            logger=lambda message: None,
        )

        result = reporter.refresh()

        self.assertTrue(result.controller_time_published)
        self.assertTrue(result.heating_failures_published)
        self.assertEqual(client.calls, ["clock", "alarms"])
        self.assertEqual(sleeps, [2])
        self.assertEqual(len(publisher.controller_payloads), 1)
        self.assertEqual(len(publisher.alarm_payloads), 1)

    def test_one_endpoint_failure_does_not_block_the_other(self) -> None:
        client = FakeClient(
            clock_error=DeviceDiagnosticsReadError("clock offline")
        )
        publisher = FakePublisher()
        messages: list[str] = []
        reporter = DeviceDiagnosticsReporter(
            client=client,
            publisher=publisher,
            request_delay_seconds=0,
            clock=lambda: datetime(
                2026,
                7,
                17,
                14,
                20,
                tzinfo=BERLIN_SUMMER,
            ),
            logger=messages.append,
        )

        result = reporter.refresh()

        self.assertFalse(result.controller_time_published)
        self.assertTrue(result.heating_failures_published)
        self.assertEqual(len(publisher.controller_payloads), 0)
        self.assertEqual(len(publisher.alarm_payloads), 1)
        self.assertTrue(any("clock offline" in item for item in messages))

    def test_stop_during_pause_prevents_second_request(self) -> None:
        client = FakeClient()
        publisher = FakePublisher()
        running = True

        def stop_during_sleep(seconds: int | float) -> None:
            nonlocal running
            self.assertEqual(seconds, 2)
            running = False

        reporter = DeviceDiagnosticsReporter(
            client=client,
            publisher=publisher,
            request_delay_seconds=2,
            sleeper=stop_during_sleep,
            is_running=lambda: running,
            clock=lambda: datetime(
                2026,
                7,
                17,
                14,
                20,
                tzinfo=BERLIN_SUMMER,
            ),
            logger=lambda message: None,
        )

        result = reporter.refresh()

        self.assertTrue(result.controller_time_published)
        self.assertFalse(result.heating_failures_published)
        self.assertEqual(client.calls, ["clock"])

    def test_negative_request_delay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DeviceDiagnosticsReporter(
                client=FakeClient(),
                publisher=FakePublisher(),
                request_delay_seconds=-1,
            )


if __name__ == "__main__":
    unittest.main()
