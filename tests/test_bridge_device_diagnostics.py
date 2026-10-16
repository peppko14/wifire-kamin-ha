#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.device_diagnostics."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bridge.device_diagnostics import (
    ControllerDiagnosticsReporter,
    build_controller_diagnostics_payload,
)
from protocol.device_diagnostics import (
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


class FakeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def read_controller_time(self) -> ControllerTime:
        if self.error is not None:
            raise self.error
        return controller_time()


class FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def publish_controller_diagnostics(
        self,
        payload: dict[str, object],
    ) -> None:
        self.payloads.append(payload)


class ControllerDiagnosticsTests(unittest.TestCase):
    def test_payload_contains_signed_time_offset(self) -> None:
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

    def test_success_is_published(self) -> None:
        publisher = FakePublisher()
        reporter = ControllerDiagnosticsReporter(
            client=FakeClient(),
            publisher=publisher,
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

        self.assertTrue(reporter.refresh())
        self.assertEqual(len(publisher.payloads), 1)

    def test_failure_keeps_previous_retained_value(self) -> None:
        publisher = FakePublisher()
        messages: list[str] = []
        reporter = ControllerDiagnosticsReporter(
            client=FakeClient(
                DeviceDiagnosticsReadError("clock offline")
            ),
            publisher=publisher,
            logger=messages.append,
        )

        self.assertFalse(reporter.refresh())
        self.assertEqual(publisher.payloads, [])
        self.assertTrue(any("clock offline" in item for item in messages))


if __name__ == "__main__":
    unittest.main()
