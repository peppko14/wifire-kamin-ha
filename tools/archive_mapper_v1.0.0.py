#!/usr/bin/env python3
"""
WiFire-Kamin Archiv-Mapper
Version: 1.0.0

Prüft lesend Archivnummern über POST /direct/35.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from wifire_protocol import decode_archive_record


__version__ = "1.0.0"

WIFIRE_URL = "http://192.168.0.1/direct/35"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "archive-maps"
REQUEST_TIMEOUT = 15


def build_command(number: int) -> str:
    if number == 0:
        return "aacc33550235003500"
    if not 0 <= number <= 255:
        raise ValueError("Archivnummer muss zwischen 0 und 255 liegen.")
    return f"aacc33550235{number:02x}ffff"


def request_archive(number: int, retries: int, delay: float) -> str:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            payload = json.dumps(
                {"raw": build_command(number)}
            ).encode("utf-8")

            request = Request(
                WIFIRE_URL,
                data=payload,
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                    "Connection": "close",
                },
                method="POST",
            )

            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            raw = result.get("raw")
            if not isinstance(raw, str):
                raise ValueError("Antwort ohne gültiges raw-Feld.")

            bytes.fromhex(raw)
            return raw

        except (OSError, ValueError) as error:
            # OSError: HTTP-/Verbindungsfehler. ValueError: kaputtes
            # JSON, fehlendes raw-Feld oder ungültiges Hex.
            last_error = error
            print(
                f"  Versuch {attempt}/{retries} fehlgeschlagen: "
                f"{error}"
            )
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(str(last_error))


def classify(raw: str) -> tuple[str, dict]:
    data = bytes.fromhex(raw)
    details = {
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }

    if len(data) != 506:
        return "unexpected_length", details

    try:
        record = decode_archive_record(raw)
    except ValueError as error:
        details["decode_error"] = str(error)
        return "invalid_archive", details

    decoded = asdict(record)
    decoded.pop("raw", None)
    decoded["timestamp"] = (
        record.timestamp.isoformat(timespec="minutes")
        if record.timestamp else None
    )
    decoded["measurement_count"] = record.measurement_count
    decoded["max_temperature_c"] = record.max_temperature_c
    decoded["max_temperature_minute"] = (
        record.max_temperature_minute
    )
    details["decoded"] = decoded

    if record.archive_number == 0:
        return "current_or_incomplete", details
    if record.timestamp is None or not record.temperatures:
        return "empty_or_invalid", details
    if record.active_or_incomplete:
        return "incomplete", details
    return "completed", details


def write_csv(number: int, raw: str, output_dir: Path) -> str | None:
    try:
        record = decode_archive_record(raw)
    except ValueError:
        return None

    if not record.temperatures:
        return None

    stamp = (
        record.timestamp.strftime("%Y-%m-%d_%H-%M")
        if record.timestamp else "unknown"
    )
    path = output_dir / f"archive_{number:03d}_{stamp}.csv"

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["minute", "temperature_c"])
        for minute, temperature in enumerate(record.temperatures):
            writer.writerow([minute, temperature])

    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-archive", type=int, default=31)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    if not 0 <= args.max_archive <= 255:
        sys.exit("--max-archive muss zwischen 0 und 255 liegen.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    stamp = started.strftime("%Y-%m-%d_%H-%M-%S")
    csv_dir = OUTPUT_DIR / f"{stamp}_csv"
    csv_dir.mkdir(exist_ok=True)

    report = {
        "tool_version": __version__,
        "created_at": started.isoformat(timespec="seconds"),
        "results": {},
        "summary": {},
    }

    counters: dict[str, int] = {}
    seen_hashes: dict[str, int] = {}

    print(f"WiFire-Kamin Archiv-Mapper v{__version__}")

    for number in range(args.max_archive + 1):
        print(f"Archiv {number:03d}: ", end="", flush=True)

        try:
            raw = request_archive(
                number,
                retries=args.retries,
                delay=max(1.0, args.delay),
            )
            classification, details = classify(raw)

            digest = details["sha256"]
            duplicate_of = seen_hashes.get(digest)

            if duplicate_of is not None:
                classification = "duplicate"
                details["duplicate_of"] = duplicate_of
            else:
                seen_hashes[digest] = number

            csv_file = write_csv(number, raw, csv_dir)
            if csv_file:
                details["csv_file"] = csv_file

            report["results"][str(number)] = {
                "command": build_command(number),
                "classification": classification,
                "raw": raw,
                **details,
            }

            counters[classification] = (
                counters.get(classification, 0) + 1
            )

            decoded = details.get("decoded", {})

            if classification == "completed":
                print(
                    f"ABGESCHLOSSEN | {decoded.get('timestamp')} | "
                    f"Max {decoded.get('max_temperature_c')} °C"
                )
            elif classification == "duplicate":
                print(
                    f"DUPLIKAT von Archiv "
                    f"{details['duplicate_of']:03d}"
                )
            else:
                print(classification.upper())

        except RuntimeError as error:
            # request_archive() wirft RuntimeError, nachdem alle
            # Versuche für dieses Archiv ausgeschöpft sind.
            counters["request_error"] = (
                counters.get("request_error", 0) + 1
            )
            report["results"][str(number)] = {
                "command": build_command(number),
                "classification": "request_error",
                "error": str(error),
            }
            print(f"FEHLER | {error}")

        if number < args.max_archive:
            time.sleep(args.delay)

    report["summary"] = {
        **counters,
        "unique_responses": len(seen_hashes),
    }

    report_path = OUTPUT_DIR / f"{stamp}_archive_map.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("Zusammenfassung:", report["summary"])
    print("Bericht:", report_path)


if __name__ == "__main__":
    main()
