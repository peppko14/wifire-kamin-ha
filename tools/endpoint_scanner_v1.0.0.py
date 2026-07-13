#!/usr/bin/env python3
"""
WiFire-Kamin Endpunkt-Scanner
Version: 1.0.0

Prüft lesend GET /direct/00 bis /direct/99.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


__version__ = "1.0.0"

BASE_URL = "http://192.168.0.1/direct"
OUTPUT_DIR = Path.home() / "wifire-reader" / "endpoint-scans"
REQUEST_TIMEOUT = 10


def request_endpoint(
    endpoint: int,
    retries: int,
    delay: float,
) -> tuple[int, str, dict]:
    last_error: Exception | None = None
    url = f"{BASE_URL}/{endpoint:02d}"

    for attempt in range(1, retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json,*/*",
                    "Connection": "close",
                },
                method="GET",
            )

            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                body = response.read().decode(
                    "utf-8",
                    errors="replace",
                )
                return (
                    response.status,
                    body,
                    dict(response.headers.items()),
                )

        except HTTPError as error:
            return (
                error.code,
                error.read().decode("utf-8", errors="replace"),
                dict(error.headers.items()),
            )

        except OSError as error:
            # HTTPError (z. B. 404/500) wird oben bereits als gültige
            # Antwort behandelt. Hier landen echte Verbindungsfehler
            # (Timeout, Verbindung abgelehnt, DNS, ...).
            last_error = error
            print(
                f"  Versuch {attempt}/{retries} fehlgeschlagen: "
                f"{error}"
            )
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(str(last_error))


def classify(status: int, body: str) -> tuple[str, dict]:
    details = {
        "status": status,
        "body_length": len(body),
        "sha256": hashlib.sha256(
            body.encode("utf-8")
        ).hexdigest(),
    }

    if status == 404:
        return "not_found", details
    if status != 200:
        return "http_error", details

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        details["preview"] = body[:200]
        return "non_json", details

    details["json"] = parsed
    raw = parsed.get("raw") if isinstance(parsed, dict) else None

    if not isinstance(raw, str):
        return "json_without_raw", details

    try:
        raw_bytes = bytes.fromhex(raw)
    except ValueError:
        return "invalid_hex", details

    details["raw_byte_length"] = len(raw_bytes)
    details["raw_header"] = raw_bytes[:8].hex()

    return "valid_raw", details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-endpoint", type=int, default=99)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    if not 0 <= args.max_endpoint <= 99:
        sys.exit("--max-endpoint muss zwischen 0 und 99 liegen.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    stamp = started.strftime("%Y-%m-%d_%H-%M-%S")

    report = {
        "tool_version": __version__,
        "created_at": started.isoformat(timespec="seconds"),
        "results": {},
        "summary": {},
    }

    counters: dict[str, int] = {}
    seen_hashes: dict[str, int] = {}

    print(f"WiFire-Kamin Endpunkt-Scanner v{__version__}")

    for endpoint in range(args.max_endpoint + 1):
        print(f"/direct/{endpoint:02d}: ", end="", flush=True)

        try:
            status, body, headers = request_endpoint(
                endpoint,
                retries=args.retries,
                delay=max(1.0, args.delay),
            )
            classification, details = classify(status, body)

            digest = details["sha256"]
            duplicate_of = seen_hashes.get(digest)

            if duplicate_of is not None and classification != "not_found":
                classification = "duplicate"
                details["duplicate_of"] = duplicate_of
            else:
                seen_hashes[digest] = endpoint

            report["results"][str(endpoint)] = {
                "url": f"{BASE_URL}/{endpoint:02d}",
                "classification": classification,
                "headers": headers,
                "body": body,
                **details,
            }

            counters[classification] = (
                counters.get(classification, 0) + 1
            )

            if classification == "valid_raw":
                print(
                    f"GEFUNDEN | {details['raw_byte_length']} Bytes"
                )
            elif classification == "duplicate":
                print(
                    f"DUPLIKAT von /direct/"
                    f"{details['duplicate_of']:02d}"
                )
            elif classification == "not_found":
                print("404")
            else:
                print(classification.upper())

        except RuntimeError as error:
            # request_endpoint() wirft RuntimeError, nachdem alle
            # Versuche für diesen Endpunkt ausgeschöpft sind.
            # classify() wirft nichts (behandelt JSON-/Hex-Fehler
            # bereits intern als Klassifizierung).
            counters["request_error"] = (
                counters.get("request_error", 0) + 1
            )
            report["results"][str(endpoint)] = {
                "classification": "request_error",
                "error": str(error),
            }
            print(f"FEHLER | {error}")

        if endpoint < args.max_endpoint:
            time.sleep(args.delay)

    report["summary"] = {
        **counters,
        "unique_responses": len(seen_hashes),
    }

    report_path = OUTPUT_DIR / f"{stamp}_endpoint_scan.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("Zusammenfassung:", report["summary"])
    print("Bericht:", report_path)


if __name__ == "__main__":
    main()
