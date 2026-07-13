# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Lokale, atomische Speicherung historischer WiFire-Abbrände."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from history.identifiers import build_burn_id
from protocol.models import BurnRecord


__version__ = "1.0.0"
HISTORY_SCHEMA_VERSION = 1


class HistoryStorageError(RuntimeError):
    """Fehler beim Lesen oder Schreiben der lokalen Historie."""


class HistoryStorage:
    """Speichert und lädt abgeschlossene Abbrände als JSON-Dateien."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def ensure_directory(self) -> None:
        """Erzeugt den Historienordner bei Bedarf."""
        self.directory.mkdir(parents=True, exist_ok=True)

    def build_filename(self, record: BurnRecord, burn_id: str) -> str:
        """Erzeugt einen stabilen, lesbaren Dateinamen."""
        if record.start is None:
            raise ValueError(
                "Für einen Historien-Dateinamen ist eine Startzeit erforderlich."
            )

        start_text = record.start.strftime("%Y-%m-%d_%H-%M")
        return f"{start_text}_{burn_id[:12]}.json"

    def path_for(self, record: BurnRecord) -> Path:
        """Berechnet den Zielpfad eines Abbrands."""
        burn_id = build_burn_id(record)
        return self.directory / self.build_filename(record, burn_id)

    def exists(self, record: BurnRecord) -> bool:
        """Prüft, ob der Abbrand bereits lokal gespeichert ist."""
        return self.path_for(record).exists()

    def serialize_record(self, record: BurnRecord) -> dict[str, Any]:
        """Erzeugt die persistente JSON-Struktur."""
        burn_id = build_burn_id(record)

        return {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "burn_id": burn_id,
            **record.to_history_dict(),
            "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    def save(self, record: BurnRecord) -> tuple[Path, bool]:
        """
        Speichert einen Abbrand atomisch.

        Rückgabe:
            (Pfad, wurde_neu_gespeichert)
        """
        if not record.is_complete:
            raise ValueError(
                "Nur abgeschlossene Abbrände dürfen gespeichert werden."
            )

        self.ensure_directory()
        target = self.path_for(record)

        if target.exists():
            return target, False

        payload = self.serialize_record(record)
        temporary = target.with_suffix(target.suffix + ".tmp")

        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            temporary.replace(target)

        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise HistoryStorageError(
                f"Abbrand konnte nicht gespeichert werden: {error}"
            ) from error

        return target, True

    def load_file(self, path: Path) -> dict[str, Any]:
        """Lädt und validiert eine Historien-Datei grundlegend."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HistoryStorageError(
                f"Historien-Datei ist nicht lesbar: {path}"
            ) from error

        if not isinstance(data, dict):
            raise HistoryStorageError(
                f"Historien-Datei enthält kein JSON-Objekt: {path}"
            )

        if data.get("schema_version") != HISTORY_SCHEMA_VERSION:
            raise HistoryStorageError(
                f"Nicht unterstützte Schema-Version in {path}"
            )

        burn_id = data.get("burn_id")
        if not isinstance(burn_id, str) or len(burn_id) != 64:
            raise HistoryStorageError(
                f"Ungültige burn_id in {path}"
            )

        return data

    def list_records(self) -> list[dict[str, Any]]:
        """Lädt alle gültigen Historien-Datensätze sortiert nach Startzeit."""
        self.ensure_directory()
        records: list[dict[str, Any]] = []

        for path in sorted(self.directory.glob("*.json")):
            records.append(self.load_file(path))

        records.sort(
            key=lambda item: str(item.get("start") or ""),
            reverse=True,
        )
        return records
