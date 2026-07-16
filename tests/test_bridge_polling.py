#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für bridge.polling."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from bridge.polling import (
    LivePoller,
    PollingSettings,
    get_next_poll_interval,
)
from protocol.models import LiveStatus


def live_status(temperature_c: int = 24) -> LiveStatus:
    return LiveStatus(
        temperature_c=temperature_c,
        flap_percent=100,
        flap_moving=False,
        burn_hours=0,
        burn_minutes=12,
        burn_total_minutes=12,
        door_open=False,
        fan_raw=1,
        status_raw=1,
        raw="raw-live-data",
    )


class LivePollerTests(unittest.TestCase):
    def test_poll_reads_and_decodes_live_data(self) -> None:
        calls: list[object] = []

        def reader() -> str:
            calls.append("read")
            return "raw-live-data"

        expected = live_status()

        def decoder(raw: str) -> LiveStatus:
            calls.append(("decode", raw))
            return expected

        poller = LivePoller(reader, decoder)

        self.assertEqual(
            poller.poll(),
            expected,
        )
        self.assertEqual(
            calls,
            ["read", ("decode", "raw-live-data")],
        )

    def test_reader_oserror_is_not_changed(self) -> None:
        expected = OSError("nicht erreichbar")

        def reader() -> str:
            raise expected

        poller = LivePoller(
            reader,
            lambda raw: live_status(),
            retry_count=1,
        )

        with self.assertRaises(OSError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)

    def test_reader_value_error_is_not_changed(self) -> None:
        expected = ValueError("ungültige Antwort")

        def reader() -> str:
            raise expected

        poller = LivePoller(
            reader,
            lambda raw: live_status(),
            retry_count=1,
        )

        with self.assertRaises(ValueError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)

    def test_decoder_value_error_is_not_changed(self) -> None:
        expected = ValueError("ungültige Nutzdaten")

        def decoder(raw: str) -> LiveStatus:
            raise expected

        poller = LivePoller(
            lambda: "raw",
            decoder,
            retry_count=1,
        )

        with self.assertRaises(ValueError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)

    def test_transient_error_succeeds_on_second_attempt(self) -> None:
        read_count = 0
        sleeps: list[int | float] = []
        messages: list[str] = []

        def reader() -> str:
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                raise OSError("kurzer WLAN-Aussetzer")
            return "raw-live-data"

        expected = live_status()
        poller = LivePoller(
            reader,
            lambda raw: expected,
            retry_count=2,
            retry_delay_seconds=2,
            sleeper=sleeps.append,
            logger=messages.append,
        )

        self.assertEqual(poller.poll(), expected)
        self.assertEqual(read_count, 2)
        self.assertEqual(sleeps, [2])
        self.assertTrue(
            any("WLAN-Aussetzer" in message for message in messages)
        )

    def test_all_attempts_fail_with_last_error(self) -> None:
        expected = OSError("nicht erreichbar")
        read_count = 0
        sleeps: list[int | float] = []

        def reader() -> str:
            nonlocal read_count
            read_count += 1
            raise expected

        poller = LivePoller(
            reader,
            lambda raw: live_status(),
            retry_count=3,
            retry_delay_seconds=2,
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        with self.assertRaises(OSError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)
        self.assertEqual(read_count, 3)
        self.assertEqual(sleeps, [2, 2])

    def test_programming_error_is_not_retried(self) -> None:
        read_count = 0
        sleeps: list[int | float] = []

        def reader() -> str:
            nonlocal read_count
            read_count += 1
            raise TypeError("Programmierfehler")

        poller = LivePoller(
            reader,
            lambda raw: live_status(),
            retry_count=3,
            sleeper=sleeps.append,
            logger=lambda message: None,
        )

        with self.assertRaises(TypeError):
            poller.poll()

        self.assertEqual(read_count, 1)
        self.assertEqual(sleeps, [])

    def test_stop_request_prevents_another_attempt(self) -> None:
        expected = OSError("nicht erreichbar")
        running = True
        read_count = 0

        def reader() -> str:
            nonlocal read_count
            read_count += 1
            raise expected

        def stop_during_sleep(seconds: int | float) -> None:
            nonlocal running
            running = False

        poller = LivePoller(
            reader,
            lambda raw: live_status(),
            retry_count=3,
            sleeper=stop_during_sleep,
            is_running=lambda: running,
            logger=lambda message: None,
        )

        with self.assertRaises(OSError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)
        self.assertEqual(read_count, 1)


class PollingSettingsTests(unittest.TestCase):
    def test_defaults_match_previous_runtime_values(self) -> None:
        settings = PollingSettings.from_config(
            SimpleNamespace()
        )

        self.assertEqual(settings.normal_update_interval, 60)
        self.assertEqual(
            settings.active_fire_update_interval,
            10,
        )
        self.assertEqual(settings.error_retry_interval, 300)
        self.assertEqual(
            settings.active_fire_temperature_c,
            40,
        )
        self.assertEqual(settings.live_retry_count, 2)
        self.assertEqual(settings.live_retry_delay_seconds, 2)

    def test_config_overrides_are_preserved(self) -> None:
        settings = PollingSettings.from_config(
            SimpleNamespace(
                NORMAL_UPDATE_INTERVAL=90,
                ACTIVE_FIRE_UPDATE_INTERVAL=15,
                ERROR_RETRY_INTERVAL=600,
                ACTIVE_FIRE_TEMPERATURE_C=50,
                LIVE_RETRY_COUNT=4,
                LIVE_RETRY_DELAY=3,
            )
        )

        self.assertEqual(settings.normal_update_interval, 90)
        self.assertEqual(
            settings.active_fire_update_interval,
            15,
        )
        self.assertEqual(settings.error_retry_interval, 600)
        self.assertEqual(
            settings.active_fire_temperature_c,
            50,
        )
        self.assertEqual(settings.live_retry_count, 4)
        self.assertEqual(settings.live_retry_delay_seconds, 3)

    def test_invalid_retry_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LivePoller(
                lambda: "raw",
                lambda raw: live_status(),
                retry_count=0,
            )

        with self.assertRaises(ValueError):
            LivePoller(
                lambda: "raw",
                lambda raw: live_status(),
                retry_delay_seconds=-1,
            )


class GetNextPollIntervalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = PollingSettings(
            normal_update_interval=60,
            active_fire_update_interval=10,
            error_retry_interval=300,
            active_fire_temperature_c=40,
        )

    def test_read_error_uses_error_interval(self) -> None:
        result = get_next_poll_interval(
            live_status(temperature_c=500),
            True,
            self.settings,
        )

        self.assertEqual(result, (300, "Lesefehler"))

    def test_missing_state_uses_error_interval(self) -> None:
        result = get_next_poll_interval(
            None,
            False,
            self.settings,
        )

        self.assertEqual(result, (300, "Lesefehler"))

    def test_threshold_temperature_is_active_fire(self) -> None:
        result = get_next_poll_interval(
            live_status(temperature_c=40),
            False,
            self.settings,
        )

        self.assertEqual(result, (10, "aktiver Abbrand"))

    def test_temperature_below_threshold_is_normal(self) -> None:
        result = get_next_poll_interval(
            live_status(temperature_c=39),
            False,
            self.settings,
        )

        self.assertEqual(result, (60, "Normalbetrieb"))


if __name__ == "__main__":
    unittest.main()
