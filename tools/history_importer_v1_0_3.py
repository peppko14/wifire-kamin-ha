# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Einmaliger Import vorhandener WiFire-Archive in data/history/."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


__version__ = "1.0.3"

# Das Werkzeug liegt unter tools/. Deshalb muss das Repository-Hauptverzeichnis
# vor den projektinternen Imports in sys.path aufgenommen werden.
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.manager import (  # noqa: E402
    HistoryManager,
    HistorySyncResult,
    create_default_history_manager,
)
from protocol.adapters import archive_record_to_burn_record  # noqa: E402
from protocol.archive import ArchiveClient  # noqa: E402
from wifire_protocol import decode_archive_record  # noqa: E402


WIFIRE_LIVE_URL = "http://192.168.0.1/direct/00"
REQUEST_TIMEOUT = 15

DEFAULT_FIRST_ARCHIVE = 1
DEFAULT_LAST_ARCHIVE = 23
DEFAULT_DELAY = 3.0
DEFAULT_RETRIES = 3


def _log_read_warning(message: str) -> None:
    print(f"  {message}")


def create_archive_client(
    *,
    retries: int,
    retry_delay: float,
) -> ArchiveClient:
    """Erzeugt den gemeinsamen, ausschließlich lesenden Archivclient."""
    return ArchiveClient(
        live_url=WIFIRE_LIVE_URL,
        request_timeout=REQUEST_TIMEOUT,
        retry_count=retries,
        retry_delay_seconds=retry_delay,
        logger=_log_read_warning,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Importiert vorhandene WiFire-Archive in die lokale "
            "Historienablage."
        )
    )

    parser.add_argument("--first", type=int, default=DEFAULT_FIRST_ARCHIVE)
    parser.add_argument("--last", type=int, default=DEFAULT_LAST_ARCHIVE)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)

    return parser.parse_args()


def print_summary(result: HistorySyncResult) -> None:
    print()
    print("Historien-Import")
    print("----------------")
    print(f"Neu gespeichert: {result.imported_count}")
    print(f"Bereits vorhanden: {result.existing_count}")
    print(f"Unvollständig übersprungen: {result.skipped_incomplete}")
    print(f"Fehlgeschlagen: {result.failed_records}")


def main() -> None:
    args = parse_args()

    if not 1 <= args.first <= args.last <= 255:
        sys.exit(
            "Ungültiger Bereich. Erwartet: "
            "1 <= --first <= --last <= 255"
        )

    if args.retries < 1:
        sys.exit("--retries muss mindestens 1 sein.")

    if args.delay < 0:
        sys.exit("--delay darf nicht negativ sein.")

    manager: HistoryManager = create_default_history_manager(
        PROJECT_DIR
    )
    archive_client = create_archive_client(
        retries=args.retries,
        retry_delay=max(1.0, args.delay),
    )

    records = []
    read_failures = 0

    print(f"WiFire History Importer v{__version__}")
    print(
        f"Archive {args.first} bis {args.last} werden gelesen."
    )
    print(f"Ziel: {manager.storage.directory}")
    print()

    for number in range(args.first, args.last + 1):
        print(f"Archiv {number:03d}: ", end="", flush=True)

        try:
            raw = archive_client.read_raw(number)
            archive_record = decode_archive_record(raw)
            burn_record = archive_record_to_burn_record(
                archive_record
            )
            records.append(burn_record)

            if burn_record.is_complete:
                print(
                    f"gelesen | "
                    f"{burn_record.start.isoformat(timespec='minutes')} | "
                    f"Max {burn_record.max_temperature_c} °C"
                )
            else:
                print("gelesen | unvollständig")

        except (RuntimeError, ValueError) as error:
            read_failures += 1
            print(f"FEHLER | {error}")

        if number < args.last:
            time.sleep(args.delay)

    result = manager.synchronize(records)
    print_summary(result)

    if read_failures:
        print(f"Lesefehler vor Synchronisation: {read_failures}")

    print(f"Historienordner: {manager.storage.directory}")


if __name__ == "__main__":
    main()
