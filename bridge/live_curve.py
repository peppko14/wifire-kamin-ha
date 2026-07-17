# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Lokales Datenmodell für eine laufende WiFire-Brennkurve."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from bridge.logging_setup import log_warning
from protocol.models import LiveStatus


LIVE_CURVE_SCHEMA_VERSION = 1
LIVE_CURVE_END_AFTER_INACTIVE_SAMPLES = 3
MAX_LIVE_CURVE_MQTT_POINTS = 121
MAX_LIVE_CURVE_MQTT_PAYLOAD_BYTES = 16 * 1024
Logger = Callable[[str], None]
Clock = Callable[[], datetime]
SessionIdFactory = Callable[[], str]


class LiveCurveStorageError(RuntimeError):
    """Fehler beim Lesen oder Schreiben der laufenden Brennkurve."""


class LiveCurvePayloadError(ValueError):
    """Fehler beim Erzeugen der kompakten MQTT-Darstellung."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_session_id() -> str:
    return uuid4().hex


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
        if not all(
            character.isalnum() or character in {"-", "_"}
            for character in self.session_id
        ):
            raise ValueError("session_id enthält unzulässige Zeichen.")
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


def _select_live_curve_points(
    points: tuple[LiveCurvePoint, ...],
    maximum_points: int,
) -> tuple[LiveCurvePoint, ...]:
    if maximum_points < 2:
        raise LiveCurvePayloadError("maximum_points muss mindestens 2 sein.")
    if len(points) <= maximum_points:
        return points
    last_index = len(points) - 1
    selected_indexes = tuple(
        round(position * last_index / (maximum_points - 1))
        for position in range(maximum_points)
    )
    return tuple(points[index] for index in selected_indexes)


def build_live_curve_mqtt_payload(
    session: LiveCurveSession | None,
    *,
    maximum_points: int = MAX_LIVE_CURVE_MQTT_POINTS,
    maximum_payload_bytes: int = MAX_LIVE_CURVE_MQTT_PAYLOAD_BYTES,
) -> dict[str, object]:
    """Erzeugt eine begrenzte, zeitgestempelte MQTT-Momentaufnahme."""
    if maximum_payload_bytes < 1:
        raise LiveCurvePayloadError(
            "maximum_payload_bytes muss mindestens 1 sein."
        )
    if session is None:
        payload: dict[str, object] = {
            "schema_version": LIVE_CURVE_SCHEMA_VERSION,
            "status": "inactive",
            "session_id": None,
            "started_at": None,
            "updated_at": None,
            "point_count": 0,
            "published_point_count": 0,
            "sample_axis": "observed_at",
            "observed_at": [],
            "temperatures_c": [],
            "burn_total_minutes": [],
        }
    else:
        selected = _select_live_curve_points(session.points, maximum_points)
        payload = {
            "schema_version": LIVE_CURVE_SCHEMA_VERSION,
            "status": "active",
            "session_id": session.session_id,
            "started_at": session.started_at.isoformat(timespec="seconds"),
            "updated_at": session.updated_at.isoformat(timespec="seconds"),
            "point_count": len(session.points),
            "published_point_count": len(selected),
            "sample_axis": "observed_at",
            "observed_at": [
                point.observed_at.isoformat(timespec="seconds")
                for point in selected
            ],
            "temperatures_c": [
                point.temperature_c for point in selected
            ],
            "burn_total_minutes": [
                point.burn_total_minutes for point in selected
            ],
        }
    payload_size = len(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if payload_size > maximum_payload_bytes:
        raise LiveCurvePayloadError(
            f"Live-Kurven-Payload ist mit {payload_size} Bytes größer als "
            f"die Grenze von {maximum_payload_bytes} Bytes."
        )
    return payload


@dataclass(frozen=True, slots=True)
class LiveCurveStorage:
    """Speichert genau eine laufende Sitzung atomisch unter data/."""

    path: Path

    @property
    def completed_directory(self) -> Path:
        """Verzeichnis für abgeschlossene Live-Sitzungen."""
        return self.path.resolve().parent / "completed"

    def _write(self, target: Path, session: LiveCurveSession) -> None:
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

    def save(self, session: LiveCurveSession) -> None:
        """Ersetzt den Zwischenstand atomisch durch die neue Sitzung."""
        self._write(self.path.resolve(), session)

    def completed_path(self, session: LiveCurveSession) -> Path:
        """Erzeugt einen stabilen Dateipfad für eine abgeschlossene Sitzung."""
        start_text = session.started_at.strftime("%Y-%m-%d_%H-%M-%S")
        return (
            self.completed_directory
            / f"{start_text}_{session.session_id[:12]}.json"
        )

    def finalize(self, session: LiveCurveSession) -> Path:
        """Archiviert die Sitzung und entfernt danach den Zwischenstand."""
        target = self.completed_path(session)
        self._write(target, session)
        self.clear()
        return target

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


@dataclass(slots=True)
class LiveCurveRecorder:
    """Erkennt, speichert und beendet laufende Brennkurven-Sitzungen."""

    storage: LiveCurveStorage
    active_temperature_c: int
    end_after_inactive_samples: int = (
        LIVE_CURVE_END_AFTER_INACTIVE_SAMPLES
    )
    clock: Clock = _utc_now
    session_id_factory: SessionIdFactory = _new_session_id
    logger: Logger = print
    current_session: LiveCurveSession | None = field(
        default=None,
        init=False,
    )
    inactive_samples: int = field(default=0, init=False)
    initialized: bool = field(default=False, init=False)
    enabled: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.active_temperature_c, bool)
            or not isinstance(self.active_temperature_c, int)
        ):
            raise ValueError("active_temperature_c muss eine Ganzzahl sein.")
        if (
            isinstance(self.end_after_inactive_samples, bool)
            or not isinstance(self.end_after_inactive_samples, int)
            or self.end_after_inactive_samples < 1
        ):
            raise ValueError(
                "end_after_inactive_samples muss mindestens 1 sein."
            )

    def _restore(self) -> None:
        if self.initialized:
            return
        self.current_session = self.storage.load()
        self.initialized = True
        if self.current_session is not None:
            self.logger(
                "Laufende Brennkurve wiederaufgenommen: "
                f"{len(self.current_session.points)} Messpunkte."
            )

    def observe(self, status: LiveStatus) -> LiveCurveSession | None:
        """Verarbeitet einen Live-Zustand ohne die Bridge zu gefährden."""
        if not self.enabled:
            return self.current_session
        try:
            return self._observe(status)
        except LiveCurveStorageError as error:
            self.enabled = False
            log_warning(
                self.logger,
                "Live-Brennkurve wurde nach einem Speicherfehler "
                f"deaktiviert: {error}",
            )
            return self.current_session

    def _observe(self, status: LiveStatus) -> LiveCurveSession | None:
        self._restore()
        point = LiveCurvePoint.from_status(
            status,
            observed_at=self.clock(),
        )

        if self.current_session is None:
            if status.temperature_c < self.active_temperature_c:
                return None
            self.current_session = LiveCurveSession.start(
                session_id=self.session_id_factory(),
                point=point,
            )
            self.storage.save(self.current_session)
            self.inactive_samples = 0
            self.logger(
                "Live-Brennkurve gestartet: "
                f"{self.current_session.session_id}."
            )
            return self.current_session

        self.current_session = self.current_session.append(point)
        self.storage.save(self.current_session)

        if status.temperature_c >= self.active_temperature_c:
            self.inactive_samples = 0
            return self.current_session

        self.inactive_samples += 1
        if self.inactive_samples < self.end_after_inactive_samples:
            return self.current_session

        completed = self.current_session
        target = self.storage.finalize(completed)
        self.current_session = None
        self.inactive_samples = 0
        self.logger(
            "Live-Brennkurve abgeschlossen: "
            f"{len(completed.points)} Messpunkte unter {target}."
        )
        return None


def create_default_live_curve_storage(project_dir: Path) -> LiveCurveStorage:
    """Erzeugt die portable Standardablage im Projekt-Datenordner."""
    return LiveCurveStorage(
        project_dir.resolve() / "data" / "live-curve" / "current.json"
    )
