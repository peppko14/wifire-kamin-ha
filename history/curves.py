# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Unveränderliche Brennkurven aus der lokalen Schema-2-Historie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from history.identifiers import build_burn_id
from history.storage import (
    HISTORY_SCHEMA_VERSION,
    HistoryStorage,
    HistoryStorageError,
)
from protocol.models import BurnRecord
from protocol.quality import (
    MAX_TEMPERATURE_C,
    MIN_MEASUREMENT_COUNT,
    MIN_TEMPERATURE_C,
)


SAMPLE_AXIS = "sample_index"
QUALITY_STATUSES = {"valid", "warning"}
HEX_DIGITS = frozenset("0123456789abcdef")


class BurnCurveError(ValueError):
    """Ein Historieneintrag kann nicht als Brennkurve verwendet werden."""


@dataclass(frozen=True, slots=True)
class CurvePoint:
    """Ein Temperaturwert an einer expliziten Messpunktposition."""

    sample_index: int
    temperature_c: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.sample_index, bool)
            or not isinstance(self.sample_index, int)
            or self.sample_index < 0
        ):
            raise BurnCurveError(
                "sample_index muss eine nichtnegative Ganzzahl sein."
            )
        if (
            isinstance(self.temperature_c, bool)
            or not isinstance(self.temperature_c, int)
            or not MIN_TEMPERATURE_C
            <= self.temperature_c
            <= MAX_TEMPERATURE_C
        ):
            raise BurnCurveError(
                "Temperaturwert liegt außerhalb der Qualitätsgrenzen."
            )

    def to_dict(self) -> dict[str, int]:
        return {
            "sample_index": self.sample_index,
            "temperature_c": self.temperature_c,
        }


@dataclass(frozen=True, slots=True)
class BurnCurve:
    """Vollständige historische Temperaturkurve eines Abbrands."""

    burn_id: str
    start: datetime
    points: tuple[CurvePoint, ...]
    quality_status: str
    warning_codes: tuple[str, ...] = ()
    duration_minutes: int | None = None
    source_archive_number: int | None = None

    def __post_init__(self) -> None:
        if (
            len(self.burn_id) != 64
            or any(character not in HEX_DIGITS for character in self.burn_id)
        ):
            raise BurnCurveError("burn_id muss ein SHA-256-Hash sein.")
        if not isinstance(self.start, datetime):
            raise BurnCurveError("start muss ein Zeitstempel sein.")
        if len(self.points) < MIN_MEASUREMENT_COUNT:
            raise BurnCurveError("Brennkurve besitzt zu wenige Messpunkte.")
        expected_indices = tuple(range(len(self.points)))
        actual_indices = tuple(point.sample_index for point in self.points)
        if actual_indices != expected_indices:
            raise BurnCurveError(
                "Messpunktindizes müssen zusammenhängend bei 0 beginnen."
            )
        expected_burn_id = build_burn_id(
            BurnRecord(
                start=self.start,
                temperatures_c=self.temperatures_c,
            )
        )
        if self.burn_id != expected_burn_id:
            raise BurnCurveError("burn_id widerspricht der Brennkurve.")
        if self.quality_status not in QUALITY_STATUSES:
            raise BurnCurveError("Unbekannter Qualitätsstatus.")
        if self.quality_status == "valid" and self.warning_codes:
            raise BurnCurveError(
                "Eine gültige Kurve darf keine Warnungscodes enthalten."
            )
        if self.quality_status == "warning" and not self.warning_codes:
            raise BurnCurveError(
                "Eine Kurve mit Warnstatus benötigt mindestens einen Code."
            )
        _validate_optional_nonnegative_integer(
            self.duration_minutes,
            "duration_minutes",
        )
        _validate_optional_positive_integer(
            self.source_archive_number,
            "source_archive_number",
        )

    @property
    def sample_count(self) -> int:
        return len(self.points)

    @property
    def temperatures_c(self) -> tuple[int, ...]:
        return tuple(point.temperature_c for point in self.points)

    @property
    def start_temperature_c(self) -> int:
        return self.points[0].temperature_c

    @property
    def end_temperature_c(self) -> int:
        return self.points[-1].temperature_c

    @property
    def max_temperature_c(self) -> int:
        return max(self.temperatures_c)

    @property
    def max_temperature_sample_index(self) -> int:
        return self.temperatures_c.index(self.max_temperature_c)

    def to_dict(self) -> dict[str, object]:
        return {
            "burn_id": self.burn_id,
            "start": self.start.isoformat(timespec="seconds"),
            "sample_axis": SAMPLE_AXIS,
            "sample_count": self.sample_count,
            "duration_minutes": self.duration_minutes,
            "source_archive_number": self.source_archive_number,
            "quality_status": self.quality_status,
            "warning_codes": list(self.warning_codes),
            "max_temperature_c": self.max_temperature_c,
            "max_temperature_sample_index": (
                self.max_temperature_sample_index
            ),
            "points": [point.to_dict() for point in self.points],
        }


def _required_integer(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BurnCurveError(f"Historienfeld '{field}' muss ganzzahlig sein.")
    return value


def _optional_integer(record: Mapping[str, object], field: str) -> int | None:
    value = record.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise BurnCurveError(
            f"Historienfeld '{field}' muss ganzzahlig oder null sein."
        )
    return value


def _validate_optional_nonnegative_integer(
    value: int | None,
    field: str,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BurnCurveError(f"{field} muss nichtnegativ oder null sein.")


def _validate_optional_positive_integer(
    value: int | None,
    field: str,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BurnCurveError(f"{field} muss positiv oder null sein.")


def _parse_start(record: Mapping[str, object]) -> datetime:
    value = record.get("start")
    if not isinstance(value, str):
        raise BurnCurveError("Historienfeld 'start' fehlt.")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise BurnCurveError(
            "Historienfeld 'start' enthält keinen ISO-Zeitstempel."
        ) from error


def _parse_temperatures(record: Mapping[str, object]) -> tuple[int, ...]:
    values = record.get("temperatures_c")
    if not isinstance(values, list):
        raise BurnCurveError("Historienfeld 'temperatures_c' fehlt.")
    temperatures: list[int] = []
    for index, value in enumerate(values):
        try:
            point = CurvePoint(sample_index=index, temperature_c=value)
        except BurnCurveError as error:
            raise BurnCurveError(
                f"Ungültiger Temperaturwert an Messpunkt {index}: {error}"
            ) from error
        temperatures.append(point.temperature_c)
    return tuple(temperatures)


def _parse_quality(record: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    quality = record.get("quality")
    if not isinstance(quality, dict):
        raise BurnCurveError("Historienfeld 'quality' fehlt.")
    status = quality.get("status")
    issues = quality.get("issues")
    if not isinstance(status, str) or not isinstance(issues, list):
        raise BurnCurveError("Historienfeld 'quality' ist ungültig.")
    codes: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("code"), str):
            raise BurnCurveError("Qualitätsmerkmal enthält keinen Code.")
        codes.append(issue["code"])
    return status, tuple(codes)


def _validate_derived_fields(
    record: Mapping[str, object],
    temperatures: tuple[int, ...],
) -> None:
    expected = {
        "measurement_count": len(temperatures),
        "start_temperature_c": temperatures[0],
        "end_temperature_c": temperatures[-1],
        "max_temperature_c": max(temperatures),
        "max_temperature_minute": temperatures.index(max(temperatures)),
    }
    for field, value in expected.items():
        if _required_integer(record, field) != value:
            raise BurnCurveError(
                f"Historienfeld '{field}' widerspricht der Temperaturkurve."
            )


def curve_from_history_record(record: Mapping[str, object]) -> BurnCurve:
    """Erzeugt eine streng validierte Brennkurve aus Historien-Schema 2."""
    if _required_integer(record, "schema_version") != HISTORY_SCHEMA_VERSION:
        raise BurnCurveError("Nicht unterstützte Historien-Schema-Version.")
    if record.get("active_or_incomplete") is not False:
        raise BurnCurveError("Unvollständiger Abbrand ist keine Brennkurve.")

    start = _parse_start(record)
    temperatures = _parse_temperatures(record)
    if len(temperatures) < MIN_MEASUREMENT_COUNT:
        raise BurnCurveError("Brennkurve besitzt zu wenige Messpunkte.")
    _validate_derived_fields(record, temperatures)

    burn_id = record.get("burn_id")
    if not isinstance(burn_id, str):
        raise BurnCurveError("Historienfeld 'burn_id' fehlt.")
    calculated_id = build_burn_id(
        BurnRecord(start=start, temperatures_c=temperatures)
    )
    if burn_id != calculated_id:
        raise BurnCurveError("burn_id widerspricht der Temperaturkurve.")

    quality_status, warning_codes = _parse_quality(record)
    return BurnCurve(
        burn_id=burn_id,
        start=start,
        points=tuple(
            CurvePoint(sample_index=index, temperature_c=temperature)
            for index, temperature in enumerate(temperatures)
        ),
        quality_status=quality_status,
        warning_codes=warning_codes,
        duration_minutes=_optional_integer(record, "duration_minutes"),
        source_archive_number=_optional_integer(
            record,
            "source_archive_number",
        ),
    )


def load_burn_curves(
    directory: Path,
    *,
    since: datetime | None = None,
    include_warnings: bool = True,
) -> tuple[BurnCurve, ...]:
    """Lädt validierte Kurven chronologisch aus der lokalen Historie."""
    storage = HistoryStorage(directory)
    curves: list[BurnCurve] = []

    for path in sorted(storage.directory.glob("*.json")):
        try:
            record = storage.load_file(path)
            curve = curve_from_history_record(record)
        except (HistoryStorageError, BurnCurveError) as error:
            raise BurnCurveError(
                f"Historien-Datei kann nicht als Kurve gelesen werden: {path}"
            ) from error
        if since is not None and curve.start < since:
            continue
        if not include_warnings and curve.quality_status == "warning":
            continue
        curves.append(curve)

    curves.sort(key=lambda curve: (curve.start, curve.burn_id))
    return tuple(curves)
