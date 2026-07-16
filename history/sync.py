# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-unabhängige Synchronisation des WiFire-Ringpuffers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bridge.logging_setup import log_warning
from history.manager import HistoryManager, HistorySyncResult
from history.ring_buffer import ArchiveOutcome, RingBufferStrategy
from protocol.adapters import ArchiveRecordLike, archive_record_to_burn_record
from protocol.models import BurnRecord
from wifire_protocol import decode_archive_record




RawReader = Callable[[str, int], str]
Decoder = Callable[[str], ArchiveRecordLike]
RecordAdapter = Callable[[ArchiveRecordLike], BurnRecord]
Sleeper = Callable[[float], None]
Logger = Callable[[str], None]
RecordCallback = Callable[[int, ArchiveRecordLike, HistorySyncResult], None]
RunningCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ArchiveSyncSettings:
    """Konfiguration einer lokalen Archiv-Synchronisation."""

    live_url: str
    first_archive: int = 1
    last_archive: int = 23
    request_timeout: int = 15
    retry_count: int = 3
    retry_delay_seconds: float = 10.0
    archive_delay_seconds: float = 10.0

    def strategy(self) -> RingBufferStrategy:
        """Erzeugt und validiert die gemeinsame Ringpuffer-Strategie."""
        strategy = RingBufferStrategy(
            first_archive=self.first_archive,
            last_archive=self.last_archive,
            request_delay_seconds=self.archive_delay_seconds,
        )
        strategy.validate()
        return strategy

    def validate(self) -> None:
        self.strategy()
        if self.request_timeout < 1:
            raise ValueError("request_timeout muss mindestens 1 sein.")
        if self.retry_count < 1:
            raise ValueError("retry_count muss mindestens 1 sein.")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds darf nicht negativ sein.")


@dataclass(frozen=True, slots=True)
class ArchiveReadResult:
    """Ergebnis eines lokalen Ringpuffer-Abgleichs."""

    records_read: int
    read_failures: int
    sync_result: HistorySyncResult
    archives_examined: int
    stopped_on_existing: bool


def build_archive_url(live_url: str) -> str:
    """Leitet ``/direct/35`` aus der konfigurierten Live-URL ab."""
    parsed = urlsplit(live_url)

    if not parsed.scheme or not parsed.netloc:
        raise ValueError("WIFIRE_URL ist keine gültige absolute URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[-2] != "direct":
        raise ValueError(
            "WIFIRE_URL muss auf einen Endpunkt unter /direct/ zeigen."
        )

    path_parts[-1] = "35"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, "/" + "/".join(path_parts), "", "")
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
                result = json.loads(response.read().decode("utf-8"))

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


def _merge_results(results: list[HistorySyncResult]) -> HistorySyncResult:
    """Fasst die einzeln und sofort gespeicherten Ergebnisse zusammen."""
    return HistorySyncResult(
        imported_ids=tuple(
            burn_id for result in results for burn_id in result.imported_ids
        ),
        existing_ids=tuple(
            burn_id for result in results for burn_id in result.existing_ids
        ),
        skipped_incomplete=sum(
            result.skipped_incomplete for result in results
        ),
        failed_records=sum(result.failed_records for result in results),
        diagnostic_ids=tuple(
            diagnostic_id
            for result in results
            for diagnostic_id in result.diagnostic_ids
        ),
        diagnostic_failures=sum(
            result.diagnostic_failures for result in results
        ),
    )


def synchronize_archives(
    manager: HistoryManager,
    settings: ArchiveSyncSettings,
    *,
    raw_reader: RawReader | None = None,
    decoder: Decoder = decode_archive_record,
    record_adapter: RecordAdapter = archive_record_to_burn_record,
    sleeper: Sleeper = time.sleep,
    logger: Logger = print,
    on_record_synchronized: RecordCallback | None = None,
    is_running: RunningCheck = lambda: True,
) -> ArchiveReadResult:
    """Speichert neue Abbrände sofort und unabhängig von MQTT lokal.

    Der Scan läuft vom neuesten zum älteren Ringpufferplatz. Beim ersten
    bereits vorhandenen vollständigen Abbrand endet er. Fehler und
    unvollständige Datensätze werden protokolliert, stoppen den Scan aber
    nicht.
    """
    settings.validate()
    strategy = settings.strategy()
    archive_url = build_archive_url(settings.live_url)

    if raw_reader is None:
        def configured_reader(url: str, number: int) -> str:
            return read_archive_raw(
                url,
                number,
                timeout=settings.request_timeout,
                retry_count=settings.retry_count,
                retry_delay_seconds=settings.retry_delay_seconds,
            )

        raw_reader = configured_reader

    records_read = 0
    read_failures = 0
    archives_examined = 0
    stopped_on_existing = False
    sync_results: list[HistorySyncResult] = []
    archive_numbers = strategy.archive_numbers()

    for number in archive_numbers:
        if not is_running():
            break

        archives_examined += 1

        try:
            raw = raw_reader(archive_url, number)
            archive_record = decoder(raw)
            burn_record = record_adapter(archive_record)
            records_read += 1

            # Wichtig: sofort lokal speichern, nicht erst am Ende des Scans.
            sync_result = manager.synchronize([burn_record])
            sync_results.append(sync_result)

            if sync_result.imported_count:
                outcome = ArchiveOutcome.NEW
                logger(f"Archiv {number}: neuer Abbrand lokal gespeichert.")
            elif sync_result.existing_count:
                outcome = ArchiveOutcome.EXISTING
                stopped_on_existing = True
                logger(f"Archiv {number}: bereits lokal vorhanden.")
            elif sync_result.skipped_incomplete:
                outcome = ArchiveOutcome.INCOMPLETE
                logger(f"Archiv {number}: unvollständig, übersprungen.")
            else:
                outcome = ArchiveOutcome.READ_ERROR
                log_warning(
                    logger,
                    f"Archiv {number}: lokale Speicherung fehlgeschlagen.",
                )

            # Optionale Verbraucher laufen bewusst erst nach dem lokalen
            # Speichern und dürfen den Historienabgleich nicht gefährden.
            if on_record_synchronized is not None:
                try:
                    on_record_synchronized(number, archive_record, sync_result)
                except Exception as error:  # optionale externe Integration
                    log_warning(
                        logger,
                        f"Archiv {number}: nachgelagerte Verarbeitung "
                        f"fehlgeschlagen: {error}"
                    )

        except (OSError, RuntimeError, ValueError) as error:
            read_failures += 1
            outcome = ArchiveOutcome.READ_ERROR
            log_warning(
                logger,
                f"Archiv {number}: Lesefehler: {error}",
            )

        if not strategy.should_continue_after(outcome):
            break
        if strategy.needs_delay_after(number, outcome):
            sleeper(strategy.request_delay_seconds)

    return ArchiveReadResult(
        records_read=records_read,
        read_failures=read_failures,
        sync_result=_merge_results(sync_results),
        archives_examined=archives_examined,
        stopped_on_existing=stopped_on_existing,
    )
