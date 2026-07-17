#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Strategie für den rotierenden Archivpuffer des WiFire-Kamins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from protocol.adapters import ArchiveRecordLike


DEFAULT_ARCHIVE_SCAN_LIMIT = 255
DEFAULT_MAX_CONSECUTIVE_READ_ERRORS = 3


class ArchiveOutcome(Enum):
    """Fachliches Ergebnis eines gelesenen Archivplatzes."""

    NEW = "new"
    EXISTING = "existing"
    EMPTY = "empty"
    INCOMPLETE = "incomplete"
    READ_ERROR = "read_error"


def is_empty_archive_record(record: ArchiveRecordLike) -> bool:
    """Erkennt einen adressierbaren, aber noch unbelegten Archivplatz."""
    return (
        record.timestamp is None
        and not record.temperatures
        and record.stage_90_minute is None
        and record.stage_75_minute is None
        and record.stage_50_minute is None
        and record.stage_25_minute is None
        and record.stage_0_minute is None
        and record.active_or_incomplete
    )


@dataclass(frozen=True, slots=True)
class RingBufferStrategy:
    """Legt Bereich, Pausen und Abbruchregel eines Archivscans fest."""

    first_archive: int = 1
    last_archive: int = DEFAULT_ARCHIVE_SCAN_LIMIT
    request_delay_seconds: int | float = 10
    max_consecutive_read_errors: int = (
        DEFAULT_MAX_CONSECUTIVE_READ_ERRORS
    )

    def validate(self) -> None:
        """Prüft den konfigurierten Archivbereich und die Mindestpause."""
        if not 1 <= self.first_archive <= self.last_archive <= 255:
            raise ValueError(
                "Archivbereich muss 1 <= first <= last <= 255 erfüllen."
            )

        if self.request_delay_seconds < 10:
            raise ValueError(
                "Zwischen Archivabfragen sind mindestens "
                "10 Sekunden erforderlich."
            )
        if (
            isinstance(self.max_consecutive_read_errors, bool)
            or not isinstance(self.max_consecutive_read_errors, int)
            or self.max_consecutive_read_errors < 1
        ):
            raise ValueError(
                "max_consecutive_read_errors muss mindestens 1 sein."
            )

    def archive_numbers(self) -> tuple[int, ...]:
        """Liefert die Archivplätze in Reihenfolge neu nach alt."""
        self.validate()
        return tuple(
            range(
                self.first_archive,
                self.last_archive + 1,
            )
        )

    def should_continue_after(
        self,
        outcome: ArchiveOutcome,
        consecutive_read_errors: int = 0,
    ) -> bool:
        """Beendet den Scan an einer fachlichen oder technischen Grenze."""
        if outcome in {ArchiveOutcome.EXISTING, ArchiveOutcome.EMPTY}:
            return False
        return not (
            outcome is ArchiveOutcome.READ_ERROR
            and consecutive_read_errors >= self.max_consecutive_read_errors
        )

    def needs_delay_after(
        self,
        archive_number: int,
        outcome: ArchiveOutcome,
        consecutive_read_errors: int = 0,
    ) -> bool:
        """Entscheidet, ob vor dem nächsten Platz gewartet wird."""
        return (
            archive_number < self.last_archive
            and self.should_continue_after(
                outcome,
                consecutive_read_errors,
            )
        )
