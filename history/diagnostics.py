# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Getrennte Diagnoseablage für nicht regulär speicherbare Abbrände."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from protocol.models import BurnRecord
from protocol.quality import QualityReport


__version__ = "1.0.0"
DIAGNOSTIC_SCHEMA_VERSION = 1


class HistoryDiagnosticError(RuntimeError):
    """Eine Diagnose-Datei konnte nicht gespeichert werden."""


class HistoryDiagnosticStorage:
    """Speichert unvollständige oder ungültige Datensätze getrennt."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def build_diagnostic_id(self, record: BurnRecord) -> str:
        """Erzeugt eine stabile ID ohne Anforderungen der regulären Burn-ID."""
        if record.start is not None:
            identity = {
                "start": record.start.isoformat(timespec="seconds"),
                "source_archive_number": record.source_archive_number,
            }
        else:
            identity = {
                "raw": record.raw,
                "source_archive_number": record.source_archive_number,
                "temperatures_c": list(record.temperatures_c),
            }

        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def build_filename(self, record: BurnRecord, diagnostic_id: str) -> str:
        """Erzeugt einen lesbaren, stabilen Diagnose-Dateinamen."""
        if record.start is None:
            start_text = "unknown-start"
        else:
            start_text = record.start.strftime("%Y-%m-%d_%H-%M")
        return f"{start_text}_{diagnostic_id[:12]}.json"

    def serialize_record(
        self,
        record: BurnRecord,
        report: QualityReport,
    ) -> dict[str, object]:
        """Erzeugt eine robuste Diagnose-Darstellung ohne Ableitungen."""
        diagnostic_id = self.build_diagnostic_id(record)
        return {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "diagnostic_id": diagnostic_id,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "quality": report.to_dict(),
            "record": {
                "start": (
                    record.start.isoformat(timespec="seconds")
                    if record.start is not None
                    else None
                ),
                "source_archive_number": record.source_archive_number,
                "measurement_count": record.measurement_count,
                "temperatures_c": list(record.temperatures_c),
                "stage_90_minute": record.stage_90_minute,
                "stage_75_minute": record.stage_75_minute,
                "stage_50_minute": record.stage_50_minute,
                "stage_25_minute": record.stage_25_minute,
                "stage_0_minute": record.stage_0_minute,
                "active_or_incomplete": record.active_or_incomplete,
                "raw": record.raw,
            },
        }

    def save(
        self,
        record: BurnRecord,
        report: QualityReport,
    ) -> tuple[Path, bool, str]:
        """Speichert einen Diagnose-Datensatz atomisch und duplikatfrei."""
        self.ensure_directory()
        diagnostic_id = self.build_diagnostic_id(record)
        target = self.directory / self.build_filename(record, diagnostic_id)

        if target.exists():
            return target, False, diagnostic_id

        payload = self.serialize_record(record, report)
        temporary = target.with_suffix(target.suffix + ".tmp")

        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise HistoryDiagnosticError(
                f"Diagnose konnte nicht gespeichert werden: {error}"
            ) from error

        return target, True, diagnostic_id
