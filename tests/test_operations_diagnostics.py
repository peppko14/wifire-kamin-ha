# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from history.backup import create_backup
from operations.diagnostics import (
    CheckStatus,
    DiagnosticCheck,
    build_report,
    check_configuration,
    check_disk_space,
    check_latest_backup,
    check_mqtt,
    check_python_version,
    check_service,
    check_wifire,
)


VALID_RAW = "aacc33550f0020001800010100000000ffff01ff3803"


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class OperationsDiagnosticsTests(unittest.TestCase):
    def test_supported_python_is_ok(self) -> None:
        result = check_python_version((3, 11))

        self.assertIs(result.status, CheckStatus.OK)

    def test_old_python_is_error(self) -> None:
        result = check_python_version((3, 10))

        self.assertIs(result.status, CheckStatus.ERROR)

    def test_configuration_never_contains_password(self) -> None:
        config = SimpleNamespace(
            WIFIRE_URL="http://192.168.0.1/direct/00",
            MQTT_HOST="192.168.1.99",
            MQTT_PORT=1883,
            MQTT_PASSWORD="very-secret",
            REQUEST_TIMEOUT=5,
        )

        result = check_configuration(config)

        self.assertIs(result.status, CheckStatus.OK)
        self.assertNotIn("very-secret", json.dumps(result.to_dict()))

    def test_invalid_configuration_is_error(self) -> None:
        config = SimpleNamespace(
            WIFIRE_URL="https://user:password@example.invalid/status",
            MQTT_HOST="192.168.XXX.XXX",
            MQTT_PORT=70000,
            REQUEST_TIMEOUT=0,
        )

        result = check_configuration(config)

        self.assertIs(result.status, CheckStatus.ERROR)

    def test_low_disk_space_is_warning(self) -> None:
        usage = SimpleNamespace(total=1000, used=999, free=1024 * 1024)

        result = check_disk_space(
            Path("."),
            minimum_free_mib=100,
            disk_usage=lambda path: usage,
        )

        self.assertIs(result.status, CheckStatus.WARNING)

    def test_wifire_valid_payload_is_ok(self) -> None:
        result = check_wifire(
            "http://192.168.0.1/direct/00",
            5,
            opener=lambda request, timeout: FakeResponse({"raw": VALID_RAW}),
        )

        self.assertIs(result.status, CheckStatus.OK)
        self.assertEqual(dict(result.details)["temperature_c"], 24)

    def test_wifire_invalid_payload_is_error(self) -> None:
        result = check_wifire(
            "http://192.168.0.1/direct/00",
            5,
            opener=lambda request, timeout: FakeResponse({}),
        )

        self.assertIs(result.status, CheckStatus.ERROR)

    def test_mqtt_reachable_is_ok_and_closes_socket(self) -> None:
        connection = FakeConnection()

        result = check_mqtt(
            "192.168.1.99",
            1883,
            5,
            connector=lambda address, timeout: connection,
        )

        self.assertIs(result.status, CheckStatus.OK)
        self.assertTrue(connection.closed)

    def test_inactive_service_is_warning(self) -> None:
        completed = SimpleNamespace(returncode=3, stdout="inactive\n")

        result = check_service(runner=lambda *args, **kwargs: completed)

        self.assertIs(result.status, CheckStatus.WARNING)

    def test_latest_verified_backup_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            history = root / "history"
            diagnostics = root / "history-incomplete"
            history.mkdir()
            diagnostics.mkdir()
            (history / "burn.json").write_text("{}", encoding="utf-8")
            backup = root / "backups" / "history.zip"
            create_backup(history, diagnostics, backup)

            result = check_latest_backup(
                backup.parent,
                now=datetime.now(UTC) + timedelta(days=1),
            )

        self.assertIs(result.status, CheckStatus.OK)
        self.assertEqual(dict(result.details)["history_files"], 1)

    def test_report_prioritizes_errors_over_warnings(self) -> None:
        report = build_report(
            "0.10.0",
            [
                DiagnosticCheck("one", CheckStatus.WARNING, "warning"),
                DiagnosticCheck("two", CheckStatus.ERROR, "error"),
            ],
        )

        self.assertTrue(report.has_errors)
        self.assertTrue(report.has_warnings)
        self.assertIs(report.overall_status, CheckStatus.ERROR)
        self.assertEqual(report.to_dict()["overall_status"], "error")


if __name__ == "__main__":
    unittest.main()
