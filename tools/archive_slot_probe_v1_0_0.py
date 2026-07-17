#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Untersucht explizite WiFire-Archivplätze oberhalb von Platz 23."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Callable


__version__ = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from protocol.archive import (  # noqa: E402
    ArchiveClient,
    ArchiveReadError,
    build_archive_url,
)
from wifire_protocol import ARCHIVE_LENGTH, PACKET_HEADER  # noqa: E402


DEFAULT_LIVE_URL = "http://192.168.0.1/direct/00"
FIRST_UNCONFIRMED_SLOT = 24
MAX_ARCHIVE_SLOT = 255
MAX_SLOTS_PER_RUN = 16
MIN_REQUEST_DELAY_SECONDS = 10.0
MAX_RETRY_COUNT = 3
REPORT_SCHEMA_VERSION = 1

RawReader = Callable[[int], str]
Sleeper = Callable[[int | float], None]
Logger = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ProbeSettings:
    """Sicherheitsgrenzen eines einzelnen Diagnose-Laufs."""

    live_url: str
    first_slot: int
    last_slot: int
    request_delay_seconds: int | float = MIN_REQUEST_DELAY_SECONDS
    request_timeout: int = 15
    retry_count: int = 1
    retry_delay_seconds: int | float = MIN_REQUEST_DELAY_SECONDS

    @property
    def slot_count(self) -> int:
        return self.last_slot - self.first_slot + 1

    def validate(self) -> None:
        build_archive_url(self.live_url)
        if (
            isinstance(self.first_slot, bool)
            or isinstance(self.last_slot, bool)
            or not isinstance(self.first_slot, int)
            or not isinstance(self.last_slot, int)
            or not FIRST_UNCONFIRMED_SLOT
            <= self.first_slot
            <= self.last_slot
            <= MAX_ARCHIVE_SLOT
        ):
            raise ValueError(
                "Erwartet wird ein Bereich von 24 bis höchstens 255."
            )
        if self.slot_count > MAX_SLOTS_PER_RUN:
            raise ValueError(
                f"Pro Lauf sind höchstens {MAX_SLOTS_PER_RUN} "
                "Archivplätze erlaubt."
            )
        if (
            isinstance(self.request_delay_seconds, bool)
            or not isinstance(self.request_delay_seconds, (int, float))
            or self.request_delay_seconds < MIN_REQUEST_DELAY_SECONDS
        ):
            raise ValueError(
                "Zwischen Archivplätzen sind mindestens 10 Sekunden nötig."
            )
        if (
            isinstance(self.request_timeout, bool)
            or not isinstance(self.request_timeout, int)
            or self.request_timeout < 1
        ):
            raise ValueError("request_timeout muss mindestens 1 sein.")
        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or not 1 <= self.retry_count <= MAX_RETRY_COUNT
        ):
            raise ValueError("retry_count muss zwischen 1 und 3 liegen.")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or self.retry_delay_seconds < MIN_REQUEST_DELAY_SECONDS
        ):
            raise ValueError(
                "Zwischen Wiederholungen sind mindestens 10 Sekunden nötig."
            )


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Beobachtung genau eines Archivplatzes ohne fachliche Interpretation."""

    slot: int
    status: str
    raw: str | None = None
    byte_length: int | None = None
    sha256: str | None = None
    prefix_hex: str | None = None
    packet_header_valid: bool | None = None
    known_wire_length: bool | None = None
    duplicate_of_slot: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "status": self.status,
            "raw": self.raw,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "prefix_hex": self.prefix_hex,
            "packet_header_valid": self.packet_header_valid,
            "known_wire_length": self.known_wire_length,
            "duplicate_of_slot": self.duplicate_of_slot,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """Versionierter Bericht eines begrenzten, sequenziellen Probe-Laufs."""

    generated_at: datetime
    settings: ProbeSettings
    results: tuple[ProbeResult, ...]

    @property
    def readable_count(self) -> int:
        return sum(result.status == "readable" for result in self.results)

    @property
    def error_count(self) -> int:
        return sum(result.status == "read_error" for result in self.results)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "live_url": self.settings.live_url,
            "first_slot": self.settings.first_slot,
            "last_slot": self.settings.last_slot,
            "request_delay_seconds": (
                self.settings.request_delay_seconds
            ),
            "readable_count": self.readable_count,
            "error_count": self.error_count,
            "results": [result.to_dict() for result in self.results],
        }


def probe_archive_slots(
    settings: ProbeSettings,
    raw_reader: RawReader,
    *,
    sleeper: Sleeper = time.sleep,
    logger: Logger = print,
    generated_at: datetime | None = None,
) -> ProbeReport:
    """Liest einen expliziten Bereich strikt sequenziell und ohne Decodierung."""
    settings.validate()
    observed_hashes: dict[str, int] = {}
    results: list[ProbeResult] = []

    for slot in range(settings.first_slot, settings.last_slot + 1):
        try:
            raw = raw_reader(slot)
            payload = bytes.fromhex(raw)
            digest = hashlib.sha256(payload).hexdigest()
            duplicate_of_slot = observed_hashes.get(digest)
            if duplicate_of_slot is None:
                observed_hashes[digest] = slot

            result = ProbeResult(
                slot=slot,
                status="readable",
                raw=raw,
                byte_length=len(payload),
                sha256=digest,
                prefix_hex=payload[:8].hex(),
                packet_header_valid=payload.startswith(PACKET_HEADER),
                known_wire_length=len(payload) == ARCHIVE_LENGTH,
                duplicate_of_slot=duplicate_of_slot,
            )
            logger(
                f"Archiv {slot}: lesbar | {len(payload)} Bytes | "
                f"SHA-256 {digest[:12]}"
            )
        except ArchiveReadError as error:
            result = ProbeResult(
                slot=slot,
                status="read_error",
                error=str(error),
            )
            logger(f"Archiv {slot}: Lesefehler | {error}")

        results.append(result)
        if slot < settings.last_slot:
            sleeper(settings.request_delay_seconds)

    return ProbeReport(
        generated_at=generated_at or datetime.now().astimezone(),
        settings=settings,
        results=tuple(results),
    )


def default_output_path(report: ProbeReport) -> Path:
    timestamp = report.generated_at.strftime("%Y-%m-%d_%H-%M-%S")
    return (
        PROJECT_DIR
        / "data"
        / "archive-probe"
        / f"archive_probe_{timestamp}.json"
    )


def write_report(report: ProbeReport, output_path: Path) -> Path:
    """Schreibt private Rohdaten atomisch in die lokale Diagnoseablage."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Untersucht höchstens 16 explizite Archivplätze oberhalb 23 "
            "ausschließlich lesend."
        )
    )
    parser.add_argument("--first", type=int, default=FIRST_UNCONFIRMED_SLOT)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument(
        "--delay",
        type=float,
        default=MIN_REQUEST_DELAY_SECONDS,
    )
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=MIN_REQUEST_DELAY_SECONDS,
    )
    parser.add_argument("--live-url", default=DEFAULT_LIVE_URL)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = ProbeSettings(
        live_url=args.live_url,
        first_slot=args.first,
        last_slot=args.last,
        request_delay_seconds=args.delay,
        request_timeout=args.timeout,
        retry_count=args.retries,
        retry_delay_seconds=args.retry_delay,
    )
    try:
        settings.validate()
    except ValueError as error:
        print(f"Ungültige Probe-Konfiguration: {error}", file=sys.stderr)
        return 2

    archive_client = ArchiveClient(
        live_url=settings.live_url,
        request_timeout=settings.request_timeout,
        retry_count=settings.retry_count,
        retry_delay_seconds=settings.retry_delay_seconds,
    )
    report = probe_archive_slots(settings, archive_client.read_raw)
    output_path = write_report(
        report,
        args.output or default_output_path(report),
    )

    print()
    print("Archivplatz-Probe")
    print("------------------")
    print(f"Lesbar:     {report.readable_count}")
    print(f"Lesefehler: {report.error_count}")
    print(f"Bericht:    {output_path}")
    print("Der Bericht enthält private Rohdaten und gehört nicht in Git.")
    return 0 if report.readable_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
