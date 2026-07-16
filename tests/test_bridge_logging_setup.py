# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für die zentrale, levelbasierte Protokollierung."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
import unittest

from bridge.logging_setup import (
    configure_logging,
    log_error,
    log_warning,
)


@dataclass(slots=True)
class RecordingLogger:
    info_messages: list[str] = field(default_factory=list)
    warning_messages: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)

    def __call__(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


class LoggingSetupTests(unittest.TestCase):
    def test_info_uses_standard_output_with_timestamp_and_level(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        logger = configure_logging(
            "INFO",
            stdout=stdout,
            stderr=stderr,
        )

        logger("Bridge gestartet.")

        output = stdout.getvalue()
        self.assertIn(" INFO wifire_kamin: Bridge gestartet.", output)
        self.assertRegex(output, r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(stderr.getvalue(), "")

    def test_warning_and_error_use_standard_error(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        logger = configure_logging(
            "INFO",
            stdout=stdout,
            stderr=stderr,
        )

        logger.warning("WLAN instabil.")
        logger.error("MQTT-Verbindung fehlgeschlagen.")

        self.assertEqual(stdout.getvalue(), "")
        output = stderr.getvalue()
        self.assertIn(" WARNING wifire_kamin: WLAN instabil.", output)
        self.assertIn(
            " ERROR wifire_kamin: MQTT-Verbindung fehlgeschlagen.",
            output,
        )

    def test_configured_level_filters_less_severe_messages(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        logger = configure_logging(
            "error",
            stdout=stdout,
            stderr=stderr,
        )

        logger("nicht sichtbar")
        logger.warning("ebenfalls nicht sichtbar")
        logger.error("sichtbar")

        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("nicht sichtbar", stderr.getvalue())
        self.assertIn(" ERROR wifire_kamin: sichtbar", stderr.getvalue())

    def test_invalid_level_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "LOG_LEVEL"):
            configure_logging("VERBOSE")

    def test_level_helpers_use_structured_methods_when_available(self) -> None:
        logger = RecordingLogger()

        log_warning(logger, "Warnung")
        log_error(logger, "Fehler")

        self.assertEqual(logger.warning_messages, ["Warnung"])
        self.assertEqual(logger.error_messages, ["Fehler"])
        self.assertEqual(logger.info_messages, [])

    def test_level_helpers_keep_plain_callables_compatible(self) -> None:
        messages: list[str] = []

        log_warning(messages.append, "Warnung")
        log_error(messages.append, "Fehler")

        self.assertEqual(messages, ["Warnung", "Fehler"])


if __name__ == "__main__":
    unittest.main()
