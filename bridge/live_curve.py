# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Lokales Datenmodell für eine laufende WiFire-Brennkurve."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from protocol.models import LiveStatus


LIVE_CURVE_SCHEMA_VERSION = 1


class LiveCurveStorageError(RuntimeError):
    """Fehler beim Lesen oder Schreiben der laufenden Brennkurve."""


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} benötigt eine Zeitzone.")


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise LiveCurveStorageError(
            f"{field_name} fehlt oder ist kein Zeitstempel."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise LiveCurveStorageError(
            f"{field_name} enthält keinen gültigen ISO-Zeitstempel."
        ) from error
    try:
        _validate_aware_datetime(parsed, field_name)
    except ValueError as error:
        raise LiveCurveStorageError(str(error)) from error
    return parsed


def _parse_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LiveCurveStorageError(f"{field_name} ist keine Ganzzahl.")
    return value


@dataclass(frozen=True, slots=True)
class LiveCurvePoint:
    """Ein zeitgestempelter Messpunkt einer laufenden Brennkurve."""

    observed_at: datetime
    temperature_c: int
    burn_total_minutes: int
    status_raw: int
    flap_percent: int
    door_open: bool

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.observed_at, "observed_at")
        for field_name, value in (
            ("temperature_c", self.temperature_c),
            ("burn_total_minutes", self.burn_total_minutes),
            ("status_raw", self.status_raw),
            ("flap_percent", self.flap_percent),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} muss eine Ganzzahl sein.")
        if self.burn_total_minutes < 0:
            raise ValueError("burn_total_minutes darf nicht negativ sein.")
        if not 0 <= self.status_raw <= 255:
            raise ValueError("status_raw muss zwischen 0 und 255 liegen.")
        if not 0 <= self.flap_percent <= 100:
            raise ValueError("flap_percent muss zwischen 0 und 100 liegen.")
        if not isinstance(self.door_open, bool):
            raise ValueError("door_open muss ein Wahrheitswert sein.")

    @classmethod
    def from_status(
        cls,
        status: LiveStatus,
        *,
        observed_at: datetime,
    ) -> "LiveCurvePoint":
        """Erzeugt einen Messpunkt aus einem dekodierten Live-Zustand."""
        return cls(
            observed_at=observed_at,
            temperature_c=status.temperature_c,
            burn_total_minutes=status.burn_total_minutes,
            status_raw=status.status_raw,
            flap_percent=status.flap_percent,
            door_open=status.door_open,
        )

    def to_dict(self) -> dict[str, object]:
        """Erzeugt die persistente JSON-Darstellung."""
        return {
            "observed_at": self.observed_at.isoformat(timespec="seconds"),
            "temperature_c": self.temperature_c,
            "burn_total_minutes": self.burn_total_minutes,
            "status_raw": self.status_raw,
            "flap_percent": self.flap_percent,
            "door_open": self.door_open,
        }

    @classmethod
    def from_dict(cls, data: object) -> "LiveCurvePoint":
        """Lädt einen validierten Messpunkt aus JSON-Daten."""
        if not isinstance(data, dict):
            raise LiveCurveStorageError("Messpunkt ist kein JSON-Objekt.")
        door_open = data.get("door_open")
        if not isinstance(door_open, bool):
            raise LiveCurveStorageError(
                "door_open fehlt oder ist kein Wahrheitswert."
            )
        try:
            return cls(
                observed_at=_parse_datetime(
                    data.get("observed_at"),
                    "observed_at",
                ),
                temperature_c=_parse_int(
                    data.get("temperature_c"),
                    "temperature_c",
                ),
                burn_total_minutes=_parse_int(
                    data.get("burn_total_minutes"),
                    "burn_total_minutes",
                ),
                status_raw=_parse_int(
                    data.get("status_raw"),
                    "status_raw",
                ),
                flap_percent=_parse_int(
                    data.get("flap_percent"),
                    "flap_percent",
                ),
                door_open=door_open,
            )
        except ValueError as error:
            raise LiveCurveStorageError(str(error)) from error


@dataclass(frozen=True, slots=True)
class LiveCurveSession:
    """Unveränderliche Momentaufnahme einer laufenden Beobachtung."""

    session_id: str
    started_at: datetime
    points: tuple[LiveCurvePoint, ...]

    def __post_init__(self) -> None:
        if not self.session_id or not self.session_id.strip():
            raise ValueError("session_id darf nicht leer sein.")
        _validate_aware_datetime(self.started_at, "started_at")
        if not self.points:
            raise ValueError("Eine Live-Sitzung benötigt mindestens einen Punkt.")
        if self.started_at != self.points[0].observed_at:
            raise ValueError(
                "started_at muss dem ersten Beobachtungszeitpunkt entsprechen."
            )
        for previous, current in zip(self.points, self.points[1:]):
            if current.observed_at < previous.observed_at:
                raise ValueError(
                    "Live-Messpunkte müssen zeitlich sortiert sein."
                )

    @classmethod
    def start(
        cls,
        *,
        session_id: str,
        point: LiveCurvePoint,
    ) -> "LiveCurveSession":
        """Beginnt eine Sitzung mit ihrem ersten Messpunkt."""
        return cls(
            session_id=session_id,
            started_at=point.observed_at,
            points=(point,),
        )

    @property
    def updated_at(self) -> datetime:
        """Zeitpunkt des neuesten gespeicherten Messpunkts."""
        return self.points[-1].observed_at

    def append(self, point: LiveCurvePoint) -> "LiveCurveSession":
        """Gibt eine neue Sitzung mit einem weiteren Messpunkt zurück."""
        return replace(self, points=(*self.points, point))

    def to_dict(self) -> dict[str, object]:
        """Erzeugt die persistente JSON-Darstellung."""
        return {
            "schema_version": LIVE_CURVE_SCHEMA_VERSION,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
            "point_count": len(self.points),
            "points": [point.to_dict() for point in self.points],
        }

    @classmethod
    def from_dict(cls, data: object) -> "LiveCurveSession":
        """Lädt eine validierte Sitzung aus JSON-Daten."""
        if not isinstance(data, dict):
            raise LiveCurveStorageError("Live-Sitzung ist kein JSON-Objekt.")
        if data.get("schema_version") != LIVE_CURVE_SCHEMA_VERSION:
            raise LiveCurveStorageError(
                "Nicht unterstützte Live-Kurven-Schema-Version."
            )
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise LiveCurveStorageError("session_id fehlt oder ist ungültig.")
        raw_points = data.get("points")
        if not isinstance(raw_points, list):
            raise LiveCurveStorageError("points fehlt oder ist keine Liste.")
        points = tuple(LiveCurvePoint.from_dict(item) for item in raw_points)
        point_count = _parse_int(data.get("point_count"), "point_count")
        if point_count != len(points):
            raise LiveCurveStorageError(
                "point_count stimmt nicht mit den Messpunkten überein."
            )
        started_at = _parse_datetime(data.get("started_at"), "started_at")
        updated_at = _parse_datetime(data.get("updated_at"), "updated_at")
        try:
            session = cls(
                session_id=session_id,
                started_at=started_at,
                points=points,
            )
        except ValueError as error:
            raise LiveCurveStorageError(str(error)) from error
        if session.updated_at != updated_at:
            raise LiveCurveStorageError(
                "updated_at stimmt nicht mit dem letzten Messpunkt überein."
            )
        return session


@dataclass(frozen=True, slots=True)
class LiveCurveStorage:
    """Speichert genau eine laufende Sitzung atomisch unter data/."""

    path: Path

    def save(self, session: LiveCurveSession) -> None:
        """Ersetzt den Zwischenstand atomisch durch die neue Sitzung."""
        target = self.path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    session.to_dict(),
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise LiveCurveStorageError(
                f"Live-Kurve konnte nicht gespeichert werden: {target}"
            ) from error

    def load(self) -> LiveCurveSession | None:
        """Lädt die laufende Sitzung oder gibt bei fehlender Datei None zurück."""
        target = self.path.resolve()
        if not target.exists():
            return None
        try:
            data: Any = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LiveCurveStorageError(
                f"Live-Kurve ist nicht lesbar: {target}"
            ) from error
        return LiveCurveSession.from_dict(data)

    def clear(self) -> None:
        """Entfernt den Zwischenstand einer beendeten Sitzung."""
        try:
            self.path.resolve().unlink(missing_ok=True)
        except OSError as error:
            raise LiveCurveStorageError(
                f"Live-Kurve konnte nicht entfernt werden: {self.path}"
            ) from error


def create_default_live_curve_storage(project_dir: Path) -> LiveCurveStorage:
    """Erzeugt die portable Standardablage im Projekt-Datenordner."""
    return LiveCurveStorage(
        project_dir.resolve() / "data" / "live-curve" / "current.json"
    )
