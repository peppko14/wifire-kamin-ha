# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Verifizierte Sicherung und Wiederherstellung der lokalen Historie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile


BACKUP_SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
HISTORY_CATEGORY = "history"
DIAGNOSTIC_CATEGORY = "history-incomplete"
ALLOWED_CATEGORIES = {HISTORY_CATEGORY, DIAGNOSTIC_CATEGORY}


class HistoryBackupError(RuntimeError):
    """Fehler beim Erstellen, Prüfen oder Wiederherstellen eines Backups."""


@dataclass(frozen=True, slots=True)
class BackupEntry:
    """Prüfinformationen zu einer gesicherten Datei."""

    path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Maschinenlesbare Beschreibung eines Historien-Backups."""

    created_at: str
    entries: tuple[BackupEntry, ...]

    @property
    def history_count(self) -> int:
        return sum(
            PurePosixPath(entry.path).parts[0] == HISTORY_CATEGORY
            for entry in self.entries
        )

    @property
    def diagnostic_count(self) -> int:
        return sum(
            PurePosixPath(entry.path).parts[0] == DIAGNOSTIC_CATEGORY
            for entry in self.entries
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": self.created_at,
            "file_count": len(self.entries),
            "history_count": self.history_count,
            "diagnostic_count": self.diagnostic_count,
            "files": [entry.to_dict() for entry in self.entries],
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_archive_path(value: object) -> str:
    if not isinstance(value, str):
        raise HistoryBackupError("Manifest enthält einen ungültigen Dateipfad.")

    path = PurePosixPath(value)
    filename = path.parts[-1] if path.parts else ""
    if (
        "\\" in value
        or path.is_absolute()
        or len(path.parts) != 2
        or path.parts[0] not in ALLOWED_CATEGORIES
        or path.parts[1] in {"", ".", ".."}
        or ":" in filename
        or path.suffix != ".json"
    ):
        raise HistoryBackupError(f"Unsicherer Backup-Pfad: {value}")
    return path.as_posix()


def _parse_manifest(data: bytes) -> BackupManifest:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoryBackupError("Backup-Manifest ist nicht lesbar.") from error

    if not isinstance(payload, dict):
        raise HistoryBackupError("Backup-Manifest enthält kein JSON-Objekt.")
    if payload.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise HistoryBackupError("Nicht unterstützte Backup-Schema-Version.")

    created_at = payload.get("created_at")
    if not isinstance(created_at, str):
        raise HistoryBackupError("Erstellungszeitpunkt im Manifest fehlt.")
    try:
        datetime.fromisoformat(created_at)
    except ValueError as error:
        raise HistoryBackupError(
            "Erstellungszeitpunkt im Manifest ist ungültig."
        ) from error

    files = payload.get("files")
    if not isinstance(files, list):
        raise HistoryBackupError("Dateiliste im Manifest fehlt.")

    entries: list[BackupEntry] = []
    seen_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise HistoryBackupError("Ungültiger Dateieintrag im Manifest.")
        path = _validate_archive_path(item.get("path"))
        size = item.get("size")
        digest = item.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise HistoryBackupError(f"Ungültige Dateigröße für {path}.")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise HistoryBackupError(f"Ungültige Prüfsumme für {path}.")
        if path in seen_paths:
            raise HistoryBackupError(f"Doppelter Dateipfad im Manifest: {path}")
        seen_paths.add(path)
        entries.append(BackupEntry(path=path, size=size, sha256=digest))

    expected_count = payload.get("file_count")
    if expected_count != len(entries):
        raise HistoryBackupError("Dateianzahl im Manifest ist widersprüchlich.")

    manifest = BackupManifest(created_at=created_at, entries=tuple(entries))
    if payload.get("history_count") != manifest.history_count:
        raise HistoryBackupError("Historienanzahl im Manifest ist widersprüchlich.")
    if payload.get("diagnostic_count") != manifest.diagnostic_count:
        raise HistoryBackupError("Diagnoseanzahl im Manifest ist widersprüchlich.")
    return manifest


def _source_files(directory: Path, category: str) -> list[tuple[str, Path]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise HistoryBackupError(f"Quellpfad ist kein Verzeichnis: {directory}")
    return [
        (f"{category}/{path.name}", path)
        for path in sorted(directory.glob("*.json"))
        if path.is_file()
    ]


def create_backup(
    history_directory: Path,
    diagnostic_directory: Path,
    target: Path,
    *,
    overwrite: bool = False,
) -> BackupManifest:
    """Erstellt atomisch ein Backup und prüft es vor der Freigabe."""
    target = target.resolve()
    if target.exists() and not overwrite:
        raise HistoryBackupError(f"Backup existiert bereits: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    sources = [
        *_source_files(history_directory, HISTORY_CATEGORY),
        *_source_files(diagnostic_directory, DIAGNOSTIC_CATEGORY),
    ]
    file_data: list[tuple[str, bytes]] = []
    entries: list[BackupEntry] = []
    for archive_path, source in sources:
        data = source.read_bytes()
        file_data.append((archive_path, data))
        entries.append(
            BackupEntry(
                path=archive_path,
                size=len(data),
                sha256=_sha256(data),
            )
        )

    manifest = BackupManifest(
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        entries=tuple(entries),
    )
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
                + "\n",
            )
            for archive_path, data in file_data:
                archive.writestr(archive_path, data)

        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        verified = verify_backup(temporary)
        temporary.replace(target)
        return verified
    except Exception as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, HistoryBackupError):
            raise
        raise HistoryBackupError(
            f"Backup konnte nicht erstellt werden: {error}"
        ) from error


def verify_backup(path: Path) -> BackupManifest:
    """Prüft Struktur, Vollständigkeit, Größe und SHA-256-Prüfsummen."""
    try:
        with ZipFile(path, "r") as archive:
            names = archive.namelist()
            if names.count(MANIFEST_NAME) != 1:
                raise HistoryBackupError("Backup enthält kein eindeutiges Manifest.")
            if len(names) != len(set(names)):
                raise HistoryBackupError("Backup enthält doppelte Dateipfade.")

            manifest = _parse_manifest(archive.read(MANIFEST_NAME))
            expected_names = {
                MANIFEST_NAME,
                *(entry.path for entry in manifest.entries),
            }
            if set(names) != expected_names:
                raise HistoryBackupError(
                    "Backup-Inhalt stimmt nicht mit dem Manifest überein."
                )

            for entry in manifest.entries:
                data = archive.read(entry.path)
                if len(data) != entry.size:
                    raise HistoryBackupError(
                        f"Dateigröße stimmt nicht: {entry.path}"
                    )
                if _sha256(data) != entry.sha256:
                    raise HistoryBackupError(
                        f"Prüfsumme stimmt nicht: {entry.path}"
                    )
            return manifest
    except (OSError, BadZipFile, KeyError) as error:
        raise HistoryBackupError(f"Backup ist nicht lesbar: {path}") from error


def restore_backup(path: Path, destination: Path) -> BackupManifest:
    """Stellt ein geprüftes Backup ausschließlich in ein neues Ziel wieder her."""
    manifest = verify_backup(path)
    destination = destination.resolve()
    if destination.exists():
        raise HistoryBackupError(
            f"Wiederherstellungsziel existiert bereits: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}-restore-",
            dir=destination.parent,
        )
    )
    try:
        with ZipFile(path, "r") as archive:
            for entry in manifest.entries:
                relative = PurePosixPath(entry.path)
                target = temporary.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(entry.path)
                target.write_bytes(data)
        temporary.replace(destination)
        return manifest
    except Exception as error:
        shutil.rmtree(temporary, ignore_errors=True)
        if isinstance(error, HistoryBackupError):
            raise
        raise HistoryBackupError(
            f"Backup konnte nicht wiederhergestellt werden: {error}"
        ) from error
