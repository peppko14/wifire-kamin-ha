# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Nur lesende Betriebsdiagnose für die WiFire-Kamin-Bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from history.audit import audit_history
from history.backup import HistoryBackupError, verify_backup
from protocol.live import decode_live_status


__version__ = "1.0.0"
MINIMUM_PYTHON = (3, 11)
DEFAULT_MINIMUM_FREE_MIB = 100
DEFAULT_MAXIMUM_BACKUP_AGE_DAYS = 30


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """Ergebnis einer einzelnen, nur lesenden Prüfung."""

    name: str
    status: CheckStatus
    message: str
    details: tuple[tuple[str, str | int | float | bool], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """Gesamtbericht aller Betriebsprüfungen."""

    generated_at: str
    project_version: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    def has_errors(self) -> bool:
        return any(check.status is CheckStatus.ERROR for check in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(
            check.status is CheckStatus.WARNING for check in self.checks
        )

    @property
    def overall_status(self) -> CheckStatus:
        if self.has_errors:
            return CheckStatus.ERROR
        if self.has_warnings:
            return CheckStatus.WARNING
        return CheckStatus.OK

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "project_version": self.project_version,
            "overall_status": self.overall_status.value,
            "checks": [check.to_dict() for check in self.checks],
        }


def check_python_version(
    version_info: tuple[int, int] | None = None,
) -> DiagnosticCheck:
    current = version_info or (sys.version_info.major, sys.version_info.minor)
    supported = current >= MINIMUM_PYTHON
    required = ".".join(str(part) for part in MINIMUM_PYTHON)
    actual = ".".join(str(part) for part in current)
    return DiagnosticCheck(
        name="python",
        status=CheckStatus.OK if supported else CheckStatus.ERROR,
        message=(
            f"Python {actual} erfüllt die Mindestversion {required}."
            if supported
            else f"Python {actual} ist älter als die Mindestversion {required}."
        ),
        details=(("major", current[0]), ("minor", current[1])),
    )


def check_configuration(config: object) -> DiagnosticCheck:
    """Prüft ausschließlich öffentliche Verbindungsparameter."""
    errors: list[str] = []
    wifire_url = getattr(config, "WIFIRE_URL", None)
    mqtt_host = getattr(config, "MQTT_HOST", None)
    mqtt_port = getattr(config, "MQTT_PORT", None)
    request_timeout = getattr(config, "REQUEST_TIMEOUT", None)

    if not isinstance(wifire_url, str):
        errors.append("WIFIRE_URL fehlt")
    else:
        parsed = urlsplit(wifire_url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            errors.append("WIFIRE_URL ist ungültig")

    if (
        not isinstance(mqtt_host, str)
        or not mqtt_host.strip()
        or "XXX" in mqtt_host.upper()
    ):
        errors.append("MQTT_HOST ist nicht konfiguriert")
    if (
        isinstance(mqtt_port, bool)
        or not isinstance(mqtt_port, int)
        or not 1 <= mqtt_port <= 65535
    ):
        errors.append("MQTT_PORT ist ungültig")
    if (
        isinstance(request_timeout, bool)
        or not isinstance(request_timeout, (int, float))
        or request_timeout <= 0
    ):
        errors.append("REQUEST_TIMEOUT ist ungültig")

    if errors:
        return DiagnosticCheck(
            name="configuration",
            status=CheckStatus.ERROR,
            message="; ".join(errors) + ".",
        )
    return DiagnosticCheck(
        name="configuration",
        status=CheckStatus.OK,
        message="Öffentliche Verbindungsparameter sind plausibel.",
        details=(("mqtt_port", mqtt_port),),
    )


def check_disk_space(
    path: Path,
    *,
    minimum_free_mib: int = DEFAULT_MINIMUM_FREE_MIB,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
) -> DiagnosticCheck:
    try:
        usage = disk_usage(path)
        free_mib = round(usage.free / 1024 / 1024, 1)
    except OSError as error:
        return DiagnosticCheck(
            name="disk_space",
            status=CheckStatus.ERROR,
            message=f"Freier Speicher konnte nicht ermittelt werden: {error}",
        )

    status = (
        CheckStatus.OK
        if free_mib >= minimum_free_mib
        else CheckStatus.WARNING
    )
    return DiagnosticCheck(
        name="disk_space",
        status=status,
        message=(
            f"{free_mib:.1f} MiB freier Speicher verfügbar."
            if status is CheckStatus.OK
            else f"Nur {free_mib:.1f} MiB freier Speicher verfügbar."
        ),
        details=(
            ("free_mib", free_mib),
            ("minimum_free_mib", minimum_free_mib),
        ),
    )


def check_history(
    history_directory: Path,
    diagnostic_directory: Path,
) -> DiagnosticCheck:
    audit = audit_history(history_directory, diagnostic_directory)
    if not audit.storage_is_healthy:
        status = CheckStatus.ERROR
        message = "Historie oder Diagnoseablage enthält unlesbare Dateien."
    elif audit.regular_file_count == 0:
        status = CheckStatus.WARNING
        message = "Es sind noch keine Historien-Dateien gespeichert."
    else:
        status = CheckStatus.OK
        message = f"{audit.regular_file_count} Historien-Dateien sind lesbar."
    return DiagnosticCheck(
        name="history",
        status=status,
        message=message,
        details=(
            ("history_files", audit.regular_file_count),
            ("history_unreadable", audit.regular_unreadable_count),
            ("diagnostic_files", audit.diagnostic_file_count),
            (
                "diagnostic_unreadable",
                audit.diagnostic_unreadable_count,
            ),
        ),
    )


def check_latest_backup(
    backup_directory: Path,
    *,
    maximum_age_days: int = DEFAULT_MAXIMUM_BACKUP_AGE_DAYS,
    now: datetime | None = None,
) -> DiagnosticCheck:
    backups = sorted(
        backup_directory.glob("*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return DiagnosticCheck(
            name="backup",
            status=CheckStatus.WARNING,
            message="Es wurde noch kein Historien-Backup gefunden.",
        )

    latest = backups[0]
    try:
        manifest = verify_backup(latest)
        created_at = datetime.fromisoformat(manifest.created_at)
    except (HistoryBackupError, ValueError) as error:
        return DiagnosticCheck(
            name="backup",
            status=CheckStatus.ERROR,
            message=f"Neuestes Historien-Backup ist ungültig: {error}",
        )

    reference = now or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_days = max(0, (reference - created_at).days)
    status = (
        CheckStatus.OK
        if age_days <= maximum_age_days
        else CheckStatus.WARNING
    )
    return DiagnosticCheck(
        name="backup",
        status=status,
        message=(
            f"Neuestes Backup ist verifiziert und {age_days} Tage alt."
            if status is CheckStatus.OK
            else f"Neuestes Backup ist bereits {age_days} Tage alt."
        ),
        details=(
            ("age_days", age_days),
            ("history_files", manifest.history_count),
            ("diagnostic_files", manifest.diagnostic_count),
        ),
    )


def check_wifire(
    url: str,
    timeout: float,
    *,
    opener: Callable[..., Any] = urlopen,
) -> DiagnosticCheck:
    request = Request(
        url,
        headers={"Accept": "application/json", "Connection": "close"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get("raw")
        if not isinstance(raw, str):
            raise ValueError("raw-Feld fehlt")
        live = decode_live_status(raw)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return DiagnosticCheck(
            name="wifire",
            status=CheckStatus.ERROR,
            message=f"WiFire ist nicht lesbar erreichbar: {error}",
        )
    return DiagnosticCheck(
        name="wifire",
        status=CheckStatus.OK,
        message="WiFire-Livedatensatz wurde erfolgreich gelesen.",
        details=(("temperature_c", live.temperature_c),),
    )


def check_mqtt(
    host: str,
    port: int,
    timeout: float,
    *,
    connector: Callable[..., Any] = socket.create_connection,
) -> DiagnosticCheck:
    try:
        connection = connector((host, port), timeout=timeout)
        connection.close()
    except OSError as error:
        return DiagnosticCheck(
            name="mqtt",
            status=CheckStatus.ERROR,
            message=f"MQTT-TCP-Port ist nicht erreichbar: {error}",
        )
    return DiagnosticCheck(
        name="mqtt",
        status=CheckStatus.OK,
        message="MQTT-TCP-Port ist erreichbar; Anmeldung wurde nicht geprüft.",
        details=(("port", port),),
    )


def check_service(
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> DiagnosticCheck:
    try:
        result = runner(
            ["systemctl", "is-active", "wifire-kamin.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return DiagnosticCheck(
            name="service",
            status=CheckStatus.SKIPPED,
            message="systemd ist auf diesem System nicht verfügbar.",
        )
    except (OSError, subprocess.SubprocessError) as error:
        return DiagnosticCheck(
            name="service",
            status=CheckStatus.WARNING,
            message=f"Dienststatus konnte nicht gelesen werden: {error}",
        )

    active = result.returncode == 0 and result.stdout.strip() == "active"
    return DiagnosticCheck(
        name="service",
        status=CheckStatus.OK if active else CheckStatus.WARNING,
        message=(
            "wifire-kamin.service ist aktiv."
            if active
            else "wifire-kamin.service ist nicht aktiv."
        ),
    )


def skipped_check(name: str, reason: str) -> DiagnosticCheck:
    return DiagnosticCheck(
        name=name,
        status=CheckStatus.SKIPPED,
        message=reason,
    )


def build_report(
    project_version: str,
    checks: list[DiagnosticCheck],
) -> DiagnosticReport:
    return DiagnosticReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        project_version=project_version,
        checks=tuple(checks),
    )
