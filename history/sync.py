# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Automatische Synchronisation des WiFire-Ringpuffers mit der lokalen Historie."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from history.manager import HistoryManager, HistorySyncResult
from protocol.adapters import archive_record_to_burn_record
from wifire_protocol import decode_archive_record


__version__ = "1.0.0"


@dataclass(frozen=True, slots=True)
class ArchiveSyncSettings:
    """Konfiguration einer Archiv-Synchronisation."""

    live_url: str
    first_archive: int = 1
    last_archive: int = 23
    request_timeout: int = 15
    retry_count: int = 3
    retry_delay_seconds: float = 10.0
    archive_delay_seconds: float = 10.0

    def validate(self) -> None:
        if not 1 <= self.first_archive <= self.last_archive <= 255:
            raise ValueError(
                "Archivbereich muss 1 <= first <= last <= 255 erfüllen."
            )
        if self.request_timeout < 1:
            raise ValueError("request_timeout muss mindestens 1 sein.")
        if self.retry_count < 1:
            raise ValueError("retry_count muss mindestens 1 sein.")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds darf nicht negativ sein.")
        if self.archive_delay_seconds < 0:
            raise ValueError("archive_delay_seconds darf nicht negativ sein.")


@dataclass(frozen=True, slots=True)
class ArchiveReadResult:
    """Ergebnis des Einlesens des WiFire-Archivbereichs."""

    records_read: int
    read_failures: int
    sync_result: HistorySyncResult


def build_archive_url(live_url: str) -> str:
    """Leitet `/direct/35` portabel aus der konfigurierten Live-URL ab."""
    parsed = urlsplit(live_url)

    if not parsed.scheme or not parsed.netloc:
        raise ValueError("WIFIRE_URL ist keine gültige absolute URL.")

    path_parts = [part for part in parsed.path.split("/") if part]

    if len(path_parts) < 2 or path_parts[-2] != "direct":
        raise ValueError(
            "WIFIRE_URL muss auf einen Endpunkt unter /direct/ zeigen."
        )

    path_parts[-1] = "35"
    archive_path = "/" + "/".join(path_parts)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            archive_path,
            "",
            "",
        )
    )


def build_archive_command(number: int) -> str:
    """Erzeugt den bekannten lesenden Archivbefehl."""
    if not 1 <= number <= 255:
        raise ValueError("Archivnummer muss zwischen 1 und 255 liegen.")

    return f"aacc33550235{number:02x}ffff"


def read_archive_raw(
    archive_url: str,
    number: int,
    *,
    timeout: int,
    retry_count: int,
    retry_delay_seconds: float,
) -> str:
    """Liest einen Archivblock mit begrenzten Wiederholungsversuchen."""
    last_error: Exception | None = None

    for attempt in range(1, retry_count + 1):
        try:
            body = json.dumps(
                {"raw": build_archive_command(number)}
            ).encode("utf-8")

            request = Request(
                archive_url,
                data=body,
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                    "Connection": "close",
                },
                method="POST",
            )

            with urlopen(request, timeout=timeout) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            raw = result.get("raw")
            if not isinstance(raw, str):
                raise ValueError(
                    "Archivantwort enthält kein gültiges raw-Feld."
                )

            bytes.fromhex(raw)
            return raw

        except (OSError, ValueError) as error:
            last_error = error

            if attempt < retry_count:
                time.sleep(retry_delay_seconds)

    raise RuntimeError(
        f"Archiv {number} konnte nach {retry_count} Versuchen "
        f"nicht gelesen werden: {last_error}"
    )


def synchronize_archives(
    manager: HistoryManager,
    settings: ArchiveSyncSettings,
) -> ArchiveReadResult:
    """Liest den Ringpuffer und speichert ausschließlich neue Abbrände."""
    settings.validate()
    archive_url = build_archive_url(settings.live_url)

    records = []
    read_failures = 0

    for number in range(
        settings.first_archive,
        settings.last_archive + 1,
    ):
        try:
            raw = read_archive_raw(
                archive_url,
                number,
                timeout=settings.request_timeout,
                retry_count=settings.retry_count,
                retry_delay_seconds=settings.retry_delay_seconds,
            )
            archive_record = decode_archive_record(raw)
            records.append(
                archive_record_to_burn_record(archive_record)
            )

        except (RuntimeError, ValueError):
            read_failures += 1

        if number < settings.last_archive:
            time.sleep(settings.archive_delay_seconds)

    sync_result = manager.synchronize(records)

    return ArchiveReadResult(
        records_read=len(records),
        read_failures=read_failures,
        sync_result=sync_result,
    )
