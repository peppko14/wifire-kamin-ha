#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Liest Steuerungszeit und Alarmliste der WiFire-Steuerung."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from protocol.device_diagnostics import (  # noqa: E402
    AlarmList,
    ControllerTime,
    DeviceDiagnosticsClient,
    DeviceDiagnosticsReadError,
)


__version__ = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Liest ausschließlich die interne Steuerungszeit und die "
            "Alarmliste. Es werden keine Einstellungen verändert."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Ausgabe als JSON.",
    )
    parser.add_argument(
        "--clock-only",
        action="store_true",
        help="Nur die interne Steuerungszeit lesen.",
    )
    parser.add_argument(
        "--alarms-only",
        action="store_true",
        help="Nur die Alarmliste lesen.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Gesamtzahl der Leseversuche je Endpunkt (Standard: 2).",
    )
    return parser


def _clock_payload(
    controller_time: ControllerTime,
    host_time: datetime,
) -> dict[str, object]:
    offset_seconds = round(
        (controller_time.value - host_time).total_seconds()
    )
    return {
        **controller_time.to_dict(),
        "host_time": host_time.isoformat(timespec="seconds"),
        "offset_seconds": offset_seconds,
    }


def _format_offset(offset_seconds: int) -> str:
    minutes = abs(offset_seconds) / 60
    if abs(offset_seconds) < 30:
        return "Steuerungs- und Raspberry-Zeit stimmen minutengenau überein."
    if offset_seconds < 0:
        return f"Die Steuerung liegt ungefähr {minutes:.1f} Minuten zurück."
    return f"Die Steuerung geht ungefähr {minutes:.1f} Minuten vor."


def _print_text(
    controller_time: ControllerTime | None,
    host_time: datetime | None,
    alarms: AlarmList | None,
) -> None:
    print("WiFire-Gerätediagnose")
    print("----------------------")

    if controller_time is not None and host_time is not None:
        offset_seconds = round(
            (controller_time.value - host_time).total_seconds()
        )
        print(
            "Steuerungszeit: "
            f"{controller_time.value.isoformat(timespec='minutes')}"
        )
        print(f"Raspberry-Zeit:  {host_time.isoformat(timespec='seconds')}")
        print(f"Zeitabweichung:  {_format_offset(offset_seconds)}")

    if alarms is not None:
        if controller_time is not None:
            print()
        print(f"Heizfehler:      {len(alarms.entries)}")
        for entry in alarms.entries:
            occurred_on = (
                entry.occurred_on.isoformat()
                if entry.occurred_on is not None
                else "ungültiges Datum"
            )
            print(f"- {occurred_on}: {entry.label} (Code {entry.code})")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.clock_only and args.alarms_only:
        print(
            "--clock-only und --alarms-only dürfen nicht gemeinsam "
            "verwendet werden.",
            file=sys.stderr,
        )
        return 2
    if args.retries < 1:
        print("--retries muss mindestens 1 sein.", file=sys.stderr)
        return 2

    client = DeviceDiagnosticsClient(
        live_url=config.WIFIRE_URL,
        request_timeout=getattr(config, "REQUEST_TIMEOUT", 5),
        retry_count=args.retries,
    )

    controller_time: ControllerTime | None = None
    host_time: datetime | None = None
    alarms: AlarmList | None = None
    try:
        if not args.alarms_only:
            controller_time = client.read_controller_time()
            host_time = datetime.now()
        if not args.clock_only:
            alarms = client.read_alarms()
    except DeviceDiagnosticsReadError as error:
        print(f"Lesefehler: {error}", file=sys.stderr)
        return 1

    if args.json:
        payload: dict[str, object] = {
            "schema_version": 1,
            "read_only": True,
        }
        if controller_time is not None and host_time is not None:
            payload["controller_time"] = _clock_payload(
                controller_time,
                host_time,
            )
        if alarms is not None:
            payload["alarms"] = alarms.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(controller_time, host_time, alarms)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
