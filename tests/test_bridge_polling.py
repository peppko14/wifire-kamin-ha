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


class LivePollerTests(unittest.TestCase):
    def test_poll_reads_and_decodes_live_data(self) -> None:
        calls: list[object] = []

        def reader() -> str:
            calls.append("read")
            return "raw-live-data"

        def decoder(raw: str) -> dict[str, object]:
            calls.append(("decode", raw))
            return {"temperature_c": 24}

        poller = LivePoller(reader, decoder)

        self.assertEqual(
            poller.poll(),
            {"temperature_c": 24},
        )
        self.assertEqual(
            calls,
            ["read", ("decode", "raw-live-data")],
        )

    def test_reader_oserror_is_not_changed(self) -> None:
        expected = OSError("nicht erreichbar")

        def reader() -> str:
            raise expected

        poller = LivePoller(reader, lambda raw: {})

        with self.assertRaises(OSError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)

    def test_reader_value_error_is_not_changed(self) -> None:
        expected = ValueError("ungültige Antwort")

        def reader() -> str:
            raise expected

        poller = LivePoller(reader, lambda raw: {})

        with self.assertRaises(ValueError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)

    def test_decoder_value_error_is_not_changed(self) -> None:
        expected = ValueError("ungültige Nutzdaten")

        def decoder(raw: str) -> dict[str, object]:
            raise expected

        poller = LivePoller(lambda: "raw", decoder)

        with self.assertRaises(ValueError) as context:
            poller.poll()

        self.assertIs(context.exception, expected)


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

    def test_config_overrides_are_preserved(self) -> None:
        settings = PollingSettings.from_config(
            SimpleNamespace(
                NORMAL_UPDATE_INTERVAL=90,
                ACTIVE_FIRE_UPDATE_INTERVAL=15,
                ERROR_RETRY_INTERVAL=600,
                ACTIVE_FIRE_TEMPERATURE_C=50,
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
            {"temperature_c": 500},
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
            {"temperature_c": 40},
            False,
            self.settings,
        )

        self.assertEqual(result, (10, "aktiver Abbrand"))

    def test_temperature_below_threshold_is_normal(self) -> None:
        result = get_next_poll_interval(
            {"temperature_c": 39},
            False,
            self.settings,
        )

        self.assertEqual(result, (60, "Normalbetrieb"))


if __name__ == "__main__":
    unittest.main()
