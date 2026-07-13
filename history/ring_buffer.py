#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Strategie für den rotierenden Archivpuffer des WiFire-Kamins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


__version__ = "1.0.0"


class ArchiveOutcome(Enum):
    """Fachliches Ergebnis eines gelesenen Archivplatzes."""

    NEW = "new"
    EXISTING = "existing"
    INCOMPLETE = "incomplete"
    READ_ERROR = "read_error"


@dataclass(frozen=True, slots=True)
class RingBufferStrategy:
    """Legt Bereich, Pausen und Abbruchregel eines Archivscans fest."""

    first_archive: int = 1
    last_archive: int = 23
    request_delay_seconds: int | float = 10

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
    ) -> bool:
        """Beendet den Scan erst beim ersten bekannten Abbrand."""
        return outcome is not ArchiveOutcome.EXISTING

    def needs_delay_after(
        self,
        archive_number: int,
        outcome: ArchiveOutcome,
    ) -> bool:
        """Entscheidet, ob vor dem nächsten Platz gewartet wird."""
        return (
            archive_number < self.last_archive
            and self.should_continue_after(outcome)
        )
