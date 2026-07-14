#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Erstellt einen nur lesenden Betriebsbericht der WiFire-Kamin-Bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


__version__ = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import config  # noqa: E402
from operations.diagnostics import (  # noqa: E402
    CheckStatus,
    DiagnosticReport,
    build_report,
    check_configuration,
    check_disk_space,
    check_history,
    check_latest_backup,
    check_mqtt,
    check_python_version,
    check_service,
    check_wifire,
    skipped_check,
)
from version import APP_VERSION  # noqa: E402


STATUS_LABELS = {
    CheckStatus.OK: "OK",
    CheckStatus.WARNING: "WARNUNG",
    CheckStatus.ERROR: "FEHLER",
    CheckStatus.SKIPPED: "ÜBERSPRUNGEN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prüft die WiFire-Kamin-Bridge nur lesend."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="WiFire- und MQTT-Netzwerkprüfung überspringen",
    )
    parser.add_argument(
        "--skip-service",
        action="store_true",
        help="systemd-Dienststatus nicht prüfen",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def create_report(args: argparse.Namespace) -> DiagnosticReport:
    data_directory = PROJECT_DIR / "data"
    checks = [
        check_python_version(),
        check_configuration(config),
        check_disk_space(PROJECT_DIR),
        check_history(
            data_directory / "history",
            data_directory / "history-incomplete",
        ),
        check_latest_backup(data_directory / "backups"),
    ]

    if args.offline:
        checks.extend(
            [
                skipped_check("wifire", "Offline-Prüfung wurde gewählt."),
                skipped_check("mqtt", "Offline-Prüfung wurde gewählt."),
            ]
        )
    else:
        checks.extend(
            [
                check_wifire(config.WIFIRE_URL, config.REQUEST_TIMEOUT),
                check_mqtt(config.MQTT_HOST, config.MQTT_PORT, 5),
            ]
        )

    checks.append(
        skipped_check("service", "Dienstprüfung wurde übersprungen.")
        if args.skip_service
        else check_service()
    )
    return build_report(APP_VERSION, checks)


def print_text(report: DiagnosticReport) -> None:
    print("WiFire-Kamin Betriebsdiagnose")
    print("-----------------------------")
    print(f"Projektversion: {report.project_version}")
    for check in report.checks:
        label = STATUS_LABELS[check.status]
        print(f"[{label:11}] {check.name}: {check.message}")
    print()
    print(f"Gesamtstatus: {STATUS_LABELS[report.overall_status]}")


def main() -> int:
    args = parse_args()
    report = create_report(args)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_text(report)
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
