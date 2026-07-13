#!/usr/bin/env python3

import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from wifire_protocol import decode_archive_record


WIFIRE_URL = "http://192.168.0.1/direct/35"

COMMANDS = {
    "bereich_01": "aacc3355023501ffff",
    "bereich_02": "aacc3355023502ffff",
    "bereich_03": "aacc3355023503ffff",
    "bereich_00": "aacc33550235003500",
}

OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "archive"


def read_block(command: str) -> str:
    body = json.dumps({"raw": command}).encode("utf-8")

    request = Request(
        WIFIRE_URL,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "Connection": "close",
        },
        method="POST",
    )

    with urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))

    raw = result.get("raw")

    if not isinstance(raw, str):
        raise ValueError("Antwort enthält kein gültiges Feld 'raw'.")

    bytes.fromhex(raw)

    return raw


def record_to_dict(record) -> dict:
    result = asdict(record)

    if record.timestamp is not None:
        result["timestamp"] = record.timestamp.isoformat(
            timespec="minutes"
        )

    result["max_temperature_c"] = record.max_temperature_c
    result["max_temperature_minute"] = (
        record.max_temperature_minute
    )
    result["start_temperature_c"] = record.start_temperature_c
    result["end_temperature_c"] = record.end_temperature_c
    result["measurement_count"] = record.measurement_count

    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "records": {},
    }

    print("WiFire-Kamin Archivabfrage")
    print("--------------------------")

    for name, command in COMMANDS.items():
        print(f"{name}: ", end="", flush=True)

        try:
            raw = read_block(command)
            record = decode_archive_record(raw)

            result["records"][name] = {
                "command": command,
                "decoded": record_to_dict(record),
            }

            print(
                f"OK – {record.measurement_count} Messpunkte, "
                f"Maximum {record.max_temperature_c} °C"
            )

        except (OSError, ValueError) as error:
            # OSError deckt HTTPError/URLError sowie rohe Timeouts ab,
            # ValueError deckt json.JSONDecodeError sowie unsere eigene
            # Validierung (fehlendes 'raw'-Feld, ungültiges Hex) ab.
            result["records"][name] = {
                "command": command,
                "error": str(error),
            }

            print(f"Fehler: {error}")

        time.sleep(1)

    output_file = OUTPUT_DIR / f"{timestamp}_archive_decoded.json"

    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("Archivabfrage beendet.")
    print(f"Gespeichert in: {output_file}")


if __name__ == "__main__":
    main()
