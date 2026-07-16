# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den Programmeinstieg ohne private Konfiguration."""

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from types import ModuleType
import unittest
from unittest.mock import patch

import mqtt_discovery


class MqttDiscoveryTests(unittest.TestCase):
    def test_load_config_returns_imported_module(self) -> None:
        config = ModuleType("config")

        with patch.object(
            mqtt_discovery,
            "import_module",
            return_value=config,
        ):
            self.assertIs(mqtt_discovery.load_config(), config)

    def test_missing_config_prints_setup_steps_and_returns_two(self) -> None:
        error = ModuleNotFoundError(
            "No module named 'config'",
            name="config",
        )
        stderr = StringIO()

        with patch.object(
            mqtt_discovery,
            "import_module",
            side_effect=error,
        ), redirect_stderr(stderr):
            result = mqtt_discovery.main()

        self.assertEqual(result, 2)
        message = stderr.getvalue()
        self.assertIn("config.py", message)
        self.assertIn("cp config.example.py config.py", message)
        self.assertIn("chmod 600 config.py", message)
        self.assertIn("nano config.py", message)
        self.assertNotIn("Traceback", message)

    def test_dependency_error_inside_config_is_not_hidden(self) -> None:
        error = ModuleNotFoundError(
            "No module named 'missing_dependency'",
            name="missing_dependency",
        )

        with patch.object(
            mqtt_discovery,
            "import_module",
            side_effect=error,
        ), self.assertRaises(ModuleNotFoundError) as context:
            mqtt_discovery.load_config()

        self.assertIs(context.exception, error)


if __name__ == "__main__":
    unittest.main()
