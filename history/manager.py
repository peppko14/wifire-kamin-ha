# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Koordination der lokalen WiFire-Abbrandhistorie."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from history.diagnostics import HistoryDiagnosticStorage
from history.identifiers import build_burn_id
from history.storage import HistoryStorage
from protocol.models import BurnRecord
from protocol.quality import validate_burn_record




@dataclass(frozen=True, slots=True)
class HistorySyncResult:
    """Ergebnis eines Historien-Synchronisationslaufs."""

    imported_ids: tuple[str, ...]
    existing_ids: tuple[str, ...]
    skipped_incomplete: int
    failed_records: int
    diagnostic_ids: tuple[str, ...] = ()
    diagnostic_failures: int = 0

    @property
    def imported_count(self) -> int:
        return len(self.imported_ids)

    @property
    def existing_count(self) -> int:
        return len(self.existing_ids)

    @property
    def processed_count(self) -> int:
        return (
            self.imported_count
            + self.existing_count
            + self.skipped_incomplete
            + self.failed_records
        )


class HistoryManager:
    """Importiert neue abgeschlossene Abbrände in die lokale Historie."""

    def __init__(
        self,
        storage: HistoryStorage,
        diagnostic_storage: HistoryDiagnosticStorage | None = None,
    ) -> None:
        self.storage = storage
        self.diagnostic_storage = diagnostic_storage

    def _store_diagnostic(self, record: BurnRecord) -> str | None:
        if self.diagnostic_storage is None:
            return None
        report = validate_burn_record(record)
        _, _, diagnostic_id = self.diagnostic_storage.save(record, report)
        return diagnostic_id

    def synchronize(
        self,
        records: Iterable[BurnRecord],
    ) -> HistorySyncResult:
        """
        Speichert alle neuen, abgeschlossenen Datensätze.

        Unvollständige Datensätze werden übersprungen. Fehler bei einem
        einzelnen Datensatz brechen den gesamten Lauf nicht ab.
        """
        imported_ids: list[str] = []
        existing_ids: list[str] = []
        skipped_incomplete = 0
        failed_records = 0
        diagnostic_ids: list[str] = []
        diagnostic_failures = 0

        for record in records:
            if not record.is_complete:
                skipped_incomplete += 1
                try:
                    diagnostic_id = self._store_diagnostic(record)
                    if diagnostic_id is not None:
                        diagnostic_ids.append(diagnostic_id)
                except (OSError, RuntimeError, ValueError):
                    diagnostic_failures += 1
                continue

            try:
                report = validate_burn_record(record)
                if not report.is_valid:
                    failed_records += 1
                    try:
                        diagnostic_id = self._store_diagnostic(record)
                        if diagnostic_id is not None:
                            diagnostic_ids.append(diagnostic_id)
                    except (OSError, RuntimeError, ValueError):
                        diagnostic_failures += 1
                    continue

                burn_id = build_burn_id(record)
                _, created = self.storage.save(record)

                if created:
                    imported_ids.append(burn_id)
                else:
                    existing_ids.append(burn_id)

            except (OSError, RuntimeError, ValueError):
                failed_records += 1

        return HistorySyncResult(
            imported_ids=tuple(imported_ids),
            existing_ids=tuple(existing_ids),
            skipped_incomplete=skipped_incomplete,
            failed_records=failed_records,
            diagnostic_ids=tuple(diagnostic_ids),
            diagnostic_failures=diagnostic_failures,
        )

    def list_history(self) -> list[dict[str, object]]:
        """Lädt alle lokal gespeicherten Historieneinträge."""
        return self.storage.list_records()

    def latest_record(self) -> dict[str, object] | None:
        """Gibt den zeitlich neuesten gespeicherten Abbrand zurück."""
        records = self.list_history()
        if not records:
            return None
        return records[0]


def create_default_history_manager(project_dir: Path) -> HistoryManager:
    """Erzeugt einen Manager mit portablem Standardpfad."""
    history_dir = project_dir.resolve() / "data" / "history"
    diagnostic_dir = project_dir.resolve() / "data" / "history-incomplete"
    return HistoryManager(
        HistoryStorage(history_dir),
        HistoryDiagnosticStorage(diagnostic_dir),
    )
