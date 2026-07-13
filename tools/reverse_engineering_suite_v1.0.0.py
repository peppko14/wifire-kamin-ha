#!/usr/bin/env python3
"""
WiFire-Kamin Reverse-Engineering-Suite
Version: 1.0.0

Lesende Analyse für:
- GET /direct/00..99
- POST /direct/35 mit Archivnummern 0..255
- Erkennung gültiger, leerer und doppelter Antworten
- Dekodierung bekannter Archivdaten
- JSON-Gesamtbericht und CSV-Export

Wichtig:
- Vor dem Start den laufenden MQTT-Dienst stoppen.
- Das Werkzeug verändert keine Kaminparameter.
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from wifire_protocol import decode_archive_record


__version__ = "1.0.0"

HOST = "http://192.168.0.1"
DIRECT_BASE = f"{HOST}/direct"
ARCHIVE_URL = f"{DIRECT_BASE}/35"

OUTPUT_ROOT = Path.home() / "wifire-reader" / "reverse-engineering"

REQUEST_TIMEOUT = 15


def build_archive_command(number: int) -> str:
    if number == 0:
        return "aacc33550235003500"
    if not 0 <= number <= 255:
        raise ValueError("Archivnummer außerhalb 0..255")
    return f"aacc33550235{number:02x}ffff"


def request_json_get(endpoint: int, retries: int, delay: float) -> dict:
    url = f"{DIRECT_BASE}/{endpoint:02d}"
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            req = Request(
                url,
                headers={
                    "Accept": "application/json,*/*",
                    "Connection": "close",
                },
                method="GET",
            )
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                body = response.read().decode("utf-8", errors="replace")
                return {
                    "status": response.status,
                    "headers": dict(response.headers.items()),
                    "body": body,
                }
        except HTTPError as error:
            return {
                "status": error.code,
                "headers": dict(error.headers.items()),
                "body": error.read().decode("utf-8", errors="replace"),
            }
        except OSError as error:
            # Echte Verbindungsfehler (Timeout, DNS, Verbindung
            # abgelehnt, ...). HTTPError-Antworten wie 404/500 werden
            # oben bereits als gültiges Ergebnis behandelt.
            last_error = error
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(str(last_error))


def request_archive(number: int, retries: int, delay: float) -> str:
    last_error: Exception | None = None
    command = build_archive_command(number)

    for attempt in range(1, retries + 1):
        try:
            body = json.dumps({"raw": command}).encode("utf-8")
            req = Request(
                ARCHIVE_URL,
                data=body,
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                    "Connection": "close",
                },
                method="POST",
            )
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))

            raw = result.get("raw")
            if not isinstance(raw, str):
                raise ValueError("Archivantwort ohne gültiges raw-Feld")

            bytes.fromhex(raw)
            return raw

        except (OSError, ValueError) as error:
            # OSError: Verbindungsfehler. ValueError: kaputtes JSON,
            # fehlendes raw-Feld oder ungültiges Hex.
            last_error = error
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(str(last_error))


def classify_get_response(response: dict) -> tuple[str, dict]:
    status = response["status"]
    body = response["body"]

    info = {
        "status": status,
        "body_length": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }

    if status == 404:
        return "not_found", info
    if status != 200:
        return "http_error", info

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        info["preview"] = body[:200]
        return "non_json", info

    info["json"] = parsed
    raw = parsed.get("raw") if isinstance(parsed, dict) else None

    if not isinstance(raw, str):
        return "json_without_raw", info

    try:
        raw_bytes = bytes.fromhex(raw)
    except ValueError:
        return "invalid_hex", info

    info["raw_byte_length"] = len(raw_bytes)
    info["raw_header"] = raw_bytes[:8].hex()
    return "valid_raw", info


def classify_archive(raw: str) -> tuple[str, dict]:
    data = bytes.fromhex(raw)
    info = {
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }

    if len(data) != 506:
        return "unexpected_length", info

    try:
        record = decode_archive_record(raw)
    except ValueError as error:
        info["decode_error"] = str(error)
        return "invalid_archive", info

    decoded = asdict(record)
    decoded.pop("raw", None)
    decoded["timestamp"] = (
        record.timestamp.isoformat(timespec="minutes")
        if record.timestamp else None
    )
    decoded["measurement_count"] = record.measurement_count
    decoded["max_temperature_c"] = record.max_temperature_c
    decoded["max_temperature_minute"] = record.max_temperature_minute
    decoded["start_temperature_c"] = record.start_temperature_c
    decoded["end_temperature_c"] = record.end_temperature_c
    info["decoded"] = decoded

    if record.archive_number == 0:
        return "current_or_incomplete", info
    if record.timestamp is None or not record.temperatures:
        return "empty_or_invalid", info
    if record.active_or_incomplete:
        return "incomplete", info
    return "completed", info


def write_archive_csv(number: int, raw: str, output_dir: Path) -> str | None:
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
        for minute, value in enumerate(record.temperatures):
            writer.writerow([minute, value])

    return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-endpoint", type=int, default=99)
    parser.add_argument("--max-archive", type=int, default=255)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not 0 <= args.max_endpoint <= 99:
        sys.exit("--max-endpoint muss zwischen 0 und 99 liegen")
    if not 0 <= args.max_archive <= 255:
        sys.exit("--max-archive muss zwischen 0 und 255 liegen")
    if args.delay < 0:
        sys.exit("--delay darf nicht negativ sein")
    if args.retries < 1:
        sys.exit("--retries muss mindestens 1 sein")

    started = datetime.now()
    stamp = started.strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = OUTPUT_ROOT / stamp
    csv_dir = output_dir / "csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "tool_version": __version__,
        "created_at": started.isoformat(timespec="seconds"),
        "host": HOST,
        "settings": {
            "max_endpoint": args.max_endpoint,
            "max_archive": args.max_archive,
            "delay": args.delay,
            "retries": args.retries,
        },
        "endpoints": {},
        "archives": {},
        "summary": {},
    }

    print(f"WiFire-Kamin Reverse-Engineering-Suite v{__version__}")
    print("=" * 51)

    endpoint_counts: dict[str, int] = {}
    endpoint_hashes: dict[str, int] = {}

    print("\n1/2: GET-Endpunkte")
    for endpoint in range(args.max_endpoint + 1):
        print(f"/direct/{endpoint:02d}: ", end="", flush=True)

        try:
            response = request_json_get(
                endpoint,
                retries=args.retries,
                delay=args.delay,
            )
            classification, info = classify_get_response(response)

            digest = info["sha256"]
            duplicate_of = endpoint_hashes.get(digest)
            if duplicate_of is not None and classification != "not_found":
                classification = "duplicate"
                info["duplicate_of"] = duplicate_of
            else:
                endpoint_hashes[digest] = endpoint

            report["endpoints"][str(endpoint)] = {
                "classification": classification,
                "headers": response["headers"],
                "body": response["body"],
                **info,
            }
            endpoint_counts[classification] = (
                endpoint_counts.get(classification, 0) + 1
            )

            if classification == "valid_raw":
                print(f"gültig, {info['raw_byte_length']} Bytes")
            elif classification == "duplicate":
                print(f"Duplikat von /direct/{info['duplicate_of']:02d}")
            else:
                print(classification)

        except RuntimeError as error:
            # request_json_get() wirft RuntimeError, nachdem alle
            # Versuche für diesen Endpunkt ausgeschöpft sind.
            endpoint_counts["request_error"] = (
                endpoint_counts.get("request_error", 0) + 1
            )
            report["endpoints"][str(endpoint)] = {
                "classification": "request_error",
                "error": str(error),
            }
            print(f"Fehler: {error}")

        if endpoint < args.max_endpoint:
            time.sleep(args.delay)

    archive_counts: dict[str, int] = {}
    archive_hashes: dict[str, int] = {}

    print("\n2/2: Archivnummern")
    for number in range(args.max_archive + 1):
        print(f"Archiv {number:03d}: ", end="", flush=True)

        try:
            raw = request_archive(
                number,
                retries=args.retries,
                delay=args.delay,
            )
            classification, info = classify_archive(raw)

            digest = info["sha256"]
            duplicate_of = archive_hashes.get(digest)
            if duplicate_of is not None:
                classification = "duplicate"
                info["duplicate_of"] = duplicate_of
            else:
                archive_hashes[digest] = number

            csv_file = write_archive_csv(number, raw, csv_dir)
            if csv_file:
                info["csv_file"] = csv_file

            report["archives"][str(number)] = {
                "command": build_archive_command(number),
                "classification": classification,
                "raw": raw,
                **info,
            }
            archive_counts[classification] = (
                archive_counts.get(classification, 0) + 1
            )

            decoded = info.get("decoded", {})
            if classification == "completed":
                print(
                    f"abgeschlossen, {decoded.get('timestamp')}, "
                    f"max {decoded.get('max_temperature_c')} °C"
                )
            elif classification == "duplicate":
                print(f"Duplikat von Archiv {info['duplicate_of']:03d}")
            else:
                print(classification)

        except RuntimeError as error:
            # request_archive() wirft RuntimeError, nachdem alle
            # Versuche für dieses Archiv ausgeschöpft sind.
            archive_counts["request_error"] = (
                archive_counts.get("request_error", 0) + 1
            )
            report["archives"][str(number)] = {
                "command": build_archive_command(number),
                "classification": "request_error",
                "error": str(error),
            }
            print(f"Fehler: {error}")

        if number < args.max_archive:
            time.sleep(args.delay)

    report["summary"] = {
        "endpoint_counts": endpoint_counts,
        "endpoint_unique_responses": len(endpoint_hashes),
        "archive_counts": archive_counts,
        "archive_unique_responses": len(archive_hashes),
    }

    report_path = output_dir / "reverse_engineering_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nFertig")
    print("Bericht:", report_path)
    print("CSV-Ordner:", csv_dir)
    print("Endpoint-Zusammenfassung:", endpoint_counts)
    print("Archiv-Zusammenfassung:", archive_counts)


if __name__ == "__main__":
    main()
