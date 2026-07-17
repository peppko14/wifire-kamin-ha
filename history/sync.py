# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""MQTT-unabhängige Synchronisation des WiFire-Ringpuffers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from bridge.logging_setup import log_warning
from history.manager import HistoryManager, HistorySyncResult
from history.ring_buffer import (
    DEFAULT_ARCHIVE_SCAN_LIMIT,
    DEFAULT_MAX_CONSECUTIVE_READ_ERRORS,
    ArchiveOutcome,
    RingBufferStrategy,
    is_empty_archive_record,
)
from protocol.adapters import ArchiveRecordLike, archive_record_to_burn_record
from protocol.archive import ArchiveClient, ArchiveReadCancelled
from protocol.models import BurnRecord
from wifire_protocol import decode_archive_record




RawReader = Callable[[int], str]
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
    last_archive: int = DEFAULT_ARCHIVE_SCAN_LIMIT
    request_timeout: int = 15
    retry_count: int = 3
    retry_delay_seconds: float = 10.0
    archive_delay_seconds: float = 10.0
    max_consecutive_read_errors: int = (
        DEFAULT_MAX_CONSECUTIVE_READ_ERRORS
    )

    def strategy(self) -> RingBufferStrategy:
        """Erzeugt und validiert die gemeinsame Ringpuffer-Strategie."""
        strategy = RingBufferStrategy(
            first_archive=self.first_archive,
            last_archive=self.last_archive,
            request_delay_seconds=self.archive_delay_seconds,
            max_consecutive_read_errors=(
                self.max_consecutive_read_errors
            ),
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
    empty_archives: int
    stopped_on_empty: bool
    stopped_on_read_error_limit: bool
    stopped_on_request: bool


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
    leeren Platz oder bereits vorhandenen vollständigen Abbrand endet er.
    Unvollständige Datensätze werden protokolliert; nach mehreren
    aufeinanderfolgenden Lesefehlern endet der Lauf kontrolliert.
    """
    settings.validate()
    strategy = settings.strategy()
    if raw_reader is None:
        raw_reader = ArchiveClient(
            live_url=settings.live_url,
            request_timeout=settings.request_timeout,
            retry_count=settings.retry_count,
            retry_delay_seconds=settings.retry_delay_seconds,
            sleeper=sleeper,
            logger=logger,
            is_running=is_running,
        ).read_raw

    records_read = 0
    read_failures = 0
    consecutive_read_errors = 0
    archives_examined = 0
    stopped_on_existing = False
    empty_archives = 0
    stopped_on_empty = False
    stopped_on_read_error_limit = False
    stopped_on_request = False
    sync_results: list[HistorySyncResult] = []
    archive_numbers = strategy.archive_numbers()

    for number in archive_numbers:
        if not is_running():
            stopped_on_request = True
            break

        archives_examined += 1

        try:
            raw = raw_reader(number)
            archive_record = decoder(raw)
            consecutive_read_errors = 0

            if is_empty_archive_record(archive_record):
                empty_archives += 1
                stopped_on_empty = True
                outcome = ArchiveOutcome.EMPTY
                logger(f"Archiv {number}: leer, Scan beendet.")
            else:
                burn_record = record_adapter(archive_record)
                records_read += 1

                # Wichtig: sofort lokal speichern, nicht erst am Scanende.
                sync_result = manager.synchronize([burn_record])
                sync_results.append(sync_result)

                if sync_result.imported_count:
                    outcome = ArchiveOutcome.NEW
                    logger(
                        f"Archiv {number}: neuer Abbrand lokal gespeichert."
                    )
                elif sync_result.existing_count:
                    outcome = ArchiveOutcome.EXISTING
                    stopped_on_existing = True
                    logger(f"Archiv {number}: bereits lokal vorhanden.")
                elif sync_result.skipped_incomplete:
                    outcome = ArchiveOutcome.INCOMPLETE
                    logger(
                        f"Archiv {number}: unvollständig, übersprungen."
                    )
                else:
                    outcome = ArchiveOutcome.READ_ERROR
                    log_warning(
                        logger,
                        f"Archiv {number}: lokale Speicherung "
                        "fehlgeschlagen.",
                    )

                # Optionale Verbraucher laufen erst nach lokalem Speichern.
                if on_record_synchronized is not None:
                    try:
                        on_record_synchronized(
                            number,
                            archive_record,
                            sync_result,
                        )
                    except Exception as error:  # externe Integration
                        log_warning(
                            logger,
                            f"Archiv {number}: nachgelagerte Verarbeitung "
                            f"fehlgeschlagen: {error}"
                        )

        except ArchiveReadCancelled:
            stopped_on_request = True
            logger("Archivscan wurde kontrolliert abgebrochen.")
            break
        except (OSError, RuntimeError, ValueError) as error:
            read_failures += 1
            consecutive_read_errors += 1
            outcome = ArchiveOutcome.READ_ERROR
            log_warning(
                logger,
                f"Archiv {number}: Lesefehler: {error}",
            )

        if not is_running():
            stopped_on_request = True
            logger("Archivscan wurde kontrolliert abgebrochen.")
            break

        if not strategy.should_continue_after(
            outcome,
            consecutive_read_errors,
        ):
            if (
                outcome is ArchiveOutcome.READ_ERROR
                and consecutive_read_errors
                >= strategy.max_consecutive_read_errors
            ):
                stopped_on_read_error_limit = True
                log_warning(
                    logger,
                    "Archivscan nach zu vielen aufeinanderfolgenden "
                    "Lesefehlern beendet.",
                )
            break
        if strategy.needs_delay_after(
            number,
            outcome,
            consecutive_read_errors,
        ):
            sleeper(strategy.request_delay_seconds)

    return ArchiveReadResult(
        records_read=records_read,
        read_failures=read_failures,
        sync_result=_merge_results(sync_results),
        archives_examined=archives_examined,
        stopped_on_existing=stopped_on_existing,
        empty_archives=empty_archives,
        stopped_on_empty=stopped_on_empty,
        stopped_on_read_error_limit=stopped_on_read_error_limit,
        stopped_on_request=stopped_on_request,
    )
