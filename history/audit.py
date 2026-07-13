# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Lesendes Qualitäts-Audit der lokalen WiFire-Historie."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from history.diagnostics import (
    HistoryDiagnosticError,
    HistoryDiagnosticStorage,
)
from history.storage import HistoryStorage, HistoryStorageError


__version__ = "1.0.0"


def _counter_tuple(counter: Counter[object]) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted((str(key), value) for key, value in counter.items())
    )


@dataclass(frozen=True, slots=True)
class HistoryAudit:
    """Zusammenfassung aller gelesenen Historien- und Diagnose-Dateien."""

    regular_file_count: int
    regular_readable_count: int
    regular_unreadable_count: int
    valid_count: int
    warning_count: int
    schema_versions: tuple[tuple[str, int], ...]
    warning_codes: tuple[tuple[str, int], ...]
    diagnostic_file_count: int
    diagnostic_readable_count: int
    diagnostic_unreadable_count: int
    diagnostic_codes: tuple[tuple[str, int], ...]

    @property
    def storage_is_healthy(self) -> bool:
        """True, wenn alle vorhandenen Dateien strukturell lesbar sind."""
        return (
            self.regular_unreadable_count == 0
            and self.diagnostic_unreadable_count == 0
        )

    def to_dict(self) -> dict[str, object]:
        """Erzeugt eine maschinenlesbare Darstellung."""
        return {
            "storage_is_healthy": self.storage_is_healthy,
            "history": {
                "file_count": self.regular_file_count,
                "readable_count": self.regular_readable_count,
                "unreadable_count": self.regular_unreadable_count,
                "valid_count": self.valid_count,
                "warning_count": self.warning_count,
                "schema_versions": dict(self.schema_versions),
                "warning_codes": dict(self.warning_codes),
            },
            "diagnostics": {
                "file_count": self.diagnostic_file_count,
                "readable_count": self.diagnostic_readable_count,
                "unreadable_count": self.diagnostic_unreadable_count,
                "issue_codes": dict(self.diagnostic_codes),
            },
        }


def _issue_codes(quality: object) -> list[str]:
    if not isinstance(quality, dict):
        return []
    issues = quality.get("issues")
    if not isinstance(issues, list):
        return []
    return [
        issue["code"]
        for issue in issues
        if isinstance(issue, dict) and isinstance(issue.get("code"), str)
    ]


def audit_history(
    history_directory: Path,
    diagnostic_directory: Path,
) -> HistoryAudit:
    """Prüft alle JSON-Dateien, ohne Ordner oder Inhalte zu verändern."""
    history_storage = HistoryStorage(history_directory)
    diagnostic_storage = HistoryDiagnosticStorage(diagnostic_directory)
    history_paths = sorted(history_storage.directory.glob("*.json"))
    diagnostic_paths = sorted(
        diagnostic_storage.directory.glob("*.json")
    )

    regular_readable = 0
    regular_unreadable = 0
    valid = 0
    warnings = 0
    schemas: Counter[object] = Counter()
    warning_codes: Counter[object] = Counter()

    for path in history_paths:
        try:
            data = history_storage.load_file(path)
            regular_readable += 1
            schemas[data["schema_version"]] += 1
            quality = data["quality"]
            if quality["status"] == "warning":
                warnings += 1
                warning_codes.update(_issue_codes(quality))
            else:
                valid += 1
        except (HistoryStorageError, KeyError, TypeError):
            regular_unreadable += 1

    diagnostic_readable = 0
    diagnostic_unreadable = 0
    diagnostic_codes: Counter[object] = Counter()

    for path in diagnostic_paths:
        try:
            data = diagnostic_storage.load_file(path)
            diagnostic_readable += 1
            diagnostic_codes.update(_issue_codes(data["quality"]))
        except (HistoryDiagnosticError, KeyError, TypeError):
            diagnostic_unreadable += 1

    return HistoryAudit(
        regular_file_count=len(history_paths),
        regular_readable_count=regular_readable,
        regular_unreadable_count=regular_unreadable,
        valid_count=valid,
        warning_count=warnings,
        schema_versions=_counter_tuple(schemas),
        warning_codes=_counter_tuple(warning_codes),
        diagnostic_file_count=len(diagnostic_paths),
        diagnostic_readable_count=diagnostic_readable,
        diagnostic_unreadable_count=diagnostic_unreadable,
        diagnostic_codes=_counter_tuple(diagnostic_codes),
    )
