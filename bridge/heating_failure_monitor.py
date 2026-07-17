#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Restartfeste Erkennung neuer WiFire-Heizfehler."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from bridge.logging_setup import log_warning
from protocol.device_diagnostics import (
    AlarmEntry,
    AlarmList,
    DeviceDiagnosticsReadError,
)


STATE_SCHEMA_VERSION = 1
Logger = Callable[[str], None]
Clock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
RunningCheck = Callable[[], bool]


def always_running() -> bool:
    """Standardwert für Werkzeuge ohne eigenen Lebenszyklus."""
    return True


class HeatingFailureClientLike(Protocol):
    """Benötigte lesende Schnittstelle des Diagnoseclients."""

    def read_alarms(self) -> AlarmList:
        ...


class HeatingFailurePublisherLike(Protocol):
    """Benötigte retained MQTT-Veröffentlichungen."""

    def publish_heating_failures(
        self,
        payload: dict[str, object],
    ) -> None:
        ...

    def publish_heating_failure_event(
        self,
        payload: dict[str, object],
    ) -> None:
        ...


class ScheduleLike(Protocol):
    def is_due(self, now: float) -> bool:
        ...

    def mark_updated(self, now: float) -> None:
        ...


class HeatingFailureStateError(RuntimeError):
    """Der lokale Erkennungszustand konnte nicht verarbeitet werden."""


def local_now() -> datetime:
    """Liefert die lokale Raspberry-Zeit mit UTC-Versatz."""
    return datetime.now().astimezone()


@dataclass(frozen=True, slots=True)
class HeatingFailureState:
    """Persistierter Fingerabdruck der zuletzt gelesenen Alarmplätze."""

    fingerprint: str
    raw_records: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "fingerprint": self.fingerprint,
            "raw_records": list(self.raw_records),
        }


@dataclass(frozen=True, slots=True)
class HeatingFailureStateStorage:
    """Speichert den Erkennungszustand atomisch außerhalb von Git."""

    path: Path
    logger: Logger = print

    def load(self) -> HeatingFailureState | None:
        """Lädt einen gültigen Zustand oder setzt sicher eine neue Basis."""
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Zustand ist kein JSON-Objekt.")
            if value.get("schema_version") != STATE_SCHEMA_VERSION:
                raise ValueError("Unbekannte Schema-Version.")
            fingerprint = value.get("fingerprint")
            raw_records = value.get("raw_records")
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or not isinstance(raw_records, list)
                or not all(isinstance(item, str) for item in raw_records)
            ):
                raise ValueError("Zustandsfelder sind ungültig.")
            return HeatingFailureState(
                fingerprint=fingerprint,
                raw_records=tuple(raw_records),
            )
        except (OSError, json.JSONDecodeError, ValueError) as error:
            log_warning(
                self.logger,
                "Heizfehler-Ausgangszustand ist nicht lesbar und wird "
                f"neu aufgebaut: {error}",
            )
            return None

    def save(self, state: HeatingFailureState) -> None:
        """Speichert den Zustand atomisch und dauerhaft."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    state.to_dict(),
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise HeatingFailureStateError(
                "Heizfehler-Ausgangszustand konnte nicht gespeichert werden: "
                f"{error}"
            ) from error


@dataclass(frozen=True, slots=True)
class HeatingFailureCheckResult:
    """Ergebnis einer fälligen oder übersprungenen Alarmprüfung."""

    checked: bool
    baseline_created: bool = False
    event_published: bool = False


def build_heating_failure_state(alarms: AlarmList) -> HeatingFailureState:
    """Bildet einen stabilen Fingerabdruck der geordneten Alarmplätze."""
    raw_records = tuple(entry.raw_record for entry in alarms.entries)
    fingerprint = hashlib.sha256(
        "\n".join(raw_records).encode("ascii")
    ).hexdigest()
    return HeatingFailureState(
        fingerprint=fingerprint,
        raw_records=raw_records,
    )


def _entry_to_dict(entry: AlarmEntry) -> dict[str, object]:
    return {
        "occurred_on": (
            entry.occurred_on.isoformat()
            if entry.occurred_on is not None
            else None
        ),
        "code": entry.code,
        "label": entry.label,
    }


def build_heating_failures_payload(
    alarms: AlarmList,
    observed_at: datetime,
) -> dict[str, object]:
    """Erzeugt die retained Liste ohne unbekannte Telegrammbytes."""
    entries = [_entry_to_dict(entry) for entry in alarms.entries]
    latest_date = next(
        (
            entry["occurred_on"]
            for entry in entries
            if entry["occurred_on"] is not None
        ),
        None,
    )
    return {
        "schema_version": 1,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "count": len(entries),
        "latest_date": latest_date,
        "entries": entries,
    }


def find_new_entries(
    alarms: AlarmList,
    previous: HeatingFailureState,
) -> tuple[AlarmEntry, ...]:
    """Ermittelt zusätzliche gleiche Einträge als Multimengen-Differenz."""
    previous_counts = Counter(previous.raw_records)
    added: list[AlarmEntry] = []
    for entry in alarms.entries:
        if previous_counts[entry.raw_record] > 0:
            previous_counts[entry.raw_record] -= 1
        else:
            added.append(entry)
    return tuple(added)


def build_heating_failure_event_payload(
    alarms: AlarmList,
    current: HeatingFailureState,
    previous: HeatingFailureState,
    detected_at: datetime,
) -> dict[str, object]:
    """Erzeugt ein pro veränderter Alarmliste eindeutiges Ereignis."""
    new_entries = find_new_entries(alarms, previous)
    return {
        "schema_version": 1,
        "event_id": current.fingerprint,
        "detected_at": detected_at.isoformat(timespec="seconds"),
        "new_count": len(new_entries),
        "new_entries": [_entry_to_dict(entry) for entry in new_entries],
        "current_count": len(alarms.entries),
    }


@dataclass(frozen=True, slots=True)
class HeatingFailureMonitor:
    """Prüft die Alarmliste selten, sequenziell und restartfest."""

    client: HeatingFailureClientLike
    publisher: HeatingFailurePublisherLike
    storage: HeatingFailureStateStorage
    schedule: ScheduleLike
    is_running: RunningCheck = always_running
    monotonic: MonotonicClock = time.monotonic
    clock: Clock = local_now
    logger: Logger = print

    def refresh_if_due(self) -> HeatingFailureCheckResult:
        """Prüft nur bei Fälligkeit und erzeugt nie ein Start-Ereignis."""
        now = self.monotonic()
        if not self.is_running() or not self.schedule.is_due(now):
            return HeatingFailureCheckResult(checked=False)

        try:
            alarms = self.client.read_alarms()
            observed_at = self.clock()
            current = build_heating_failure_state(alarms)
            previous = self.storage.load()

            self.publisher.publish_heating_failures(
                build_heating_failures_payload(alarms, observed_at)
            )

            if previous is None:
                self.storage.save(current)
                self.logger(
                    "Heizfehler-Ausgangszustand gespeichert; "
                    "alte Einträge lösen keine Meldung aus."
                )
                return HeatingFailureCheckResult(
                    checked=True,
                    baseline_created=True,
                )

            if current.fingerprint == previous.fingerprint:
                return HeatingFailureCheckResult(checked=True)

            new_entries = find_new_entries(alarms, previous)
            event_published = False
            if new_entries:
                event_payload = build_heating_failure_event_payload(
                    alarms,
                    current,
                    previous,
                    observed_at,
                )
                self.publisher.publish_heating_failure_event(event_payload)
                event_published = True

            self.storage.save(current)
            if event_published:
                self.logger("Neuer Heizfehler für Home Assistant erkannt.")
            return HeatingFailureCheckResult(
                checked=True,
                event_published=event_published,
            )
        except (
            DeviceDiagnosticsReadError,
            HeatingFailureStateError,
            OSError,
            ValueError,
        ) as error:
            log_warning(
                self.logger,
                f"Heizfehlerprüfung fehlgeschlagen: {error}",
            )
            return HeatingFailureCheckResult(checked=True)
        finally:
            self.schedule.mark_updated(self.monotonic())


def create_default_heating_failure_storage(
    project_dir: Path,
    *,
    logger: Logger = print,
) -> HeatingFailureStateStorage:
    """Erzeugt den portablen Speicherort innerhalb von data/."""
    return HeatingFailureStateStorage(
        path=(
            project_dir
            / "data"
            / "device-diagnostics"
            / "heating-failure-state.json"
        ).resolve(),
        logger=logger,
    )
