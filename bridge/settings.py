# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Verwaltung und Absicherung der Kamin-Systemeinstellungen (Schließzeitverzögerung)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from bridge.logging_setup import log_error, log_info, log_warning
from protocol.device_diagnostics import ControllerSettings, DeviceDiagnosticsReadError
from protocol.models import LiveStatus


SETTINGS_STORAGE_SCHEMA_VERSION = 1
DEFAULT_UNLOCK_TIMEOUT_SECONDS = 300.0  # 5 Minuten automatische Wiedersperrung

Logger = Callable[[str], None]
Clock = Callable[[], float]


class SettingsDiagnosticsClientLike(Protocol):
    def read_controller_settings(self) -> ControllerSettings:
        ...

    def set_closing_delay(
        self,
        new_delay_minutes: int,
        current_settings: ControllerSettings | None = None,
    ) -> ControllerSettings:
        ...


class SettingsPublisherLike(Protocol):
    def publish_closing_delay(self, minutes: int) -> None:
        ...

    def publish_settings_lock(self, unlocked: bool) -> None:
        ...


@dataclass(frozen=True, slots=True)
class SettingsState:
    """Gespeicherter Zustand der Systemeinstellungen."""

    schema_version: int = SETTINGS_STORAGE_SCHEMA_VERSION
    closing_delay_minutes: int = 60
    raw_payload: str | None = None
    last_updated_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SettingsState:
        return cls(
            schema_version=int(
                data.get("schema_version", SETTINGS_STORAGE_SCHEMA_VERSION)
            ),
            closing_delay_minutes=int(data.get("closing_delay_minutes", 60)),
            raw_payload=data.get("raw_payload"),
            last_updated_at=data.get("last_updated_at"),
        )


@dataclass(frozen=True, slots=True)
class SettingsStateStorage:
    """Atomare Speicherung der zuletzt gelesenen Systemeinstellungen."""

    path: Path

    def load(self) -> SettingsState:
        target = self.path.resolve()
        if not target.exists():
            return SettingsState()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            return SettingsState.from_dict(payload)
        except (OSError, ValueError, TypeError):
            return SettingsState()

    def save(self, state: SettingsState) -> None:
        target = self.path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"

        with tempfile.NamedTemporaryFile(
            "w",
            dir=target.parent,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temp_name = temporary.name

        os.replace(temp_name, target)


@dataclass(slots=True)
class SettingsManager:
    """Verwaltet Schreibschutz, Leseprüfung und sichere Änderung der Schließzeitverzögerung."""

    storage: SettingsStateStorage
    diagnostics_client: SettingsDiagnosticsClientLike
    publisher: SettingsPublisherLike
    unlock_timeout_seconds: float = DEFAULT_UNLOCK_TIMEOUT_SECONDS
    clock: Clock = time.monotonic
    logger: Logger = print
    current_state: SettingsState = field(init=False)
    unlocked_until: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.current_state = self.storage.load()

    @property
    def is_unlocked(self) -> bool:
        """Gibt True zurück, wenn die Sperre aktuell aufgehoben ist."""
        return self.clock() < self.unlocked_until

    def publish_current_state(self) -> None:
        """Veröffentlicht aktuelle Schließzeitverzögerung und Sperrzustand."""
        self.publisher.publish_closing_delay(
            self.current_state.closing_delay_minutes
        )
        self.publisher.publish_settings_lock(self.is_unlocked)

    def set_lock_state(self, unlock: bool) -> None:
        """Schaltet den Schreibschutz ein oder für eine begrenzte Zeit aus."""
        now = self.clock()
        if unlock:
            self.unlocked_until = now + self.unlock_timeout_seconds
            log_info(
                self.logger,
                "Schreibschutz für Kamin-Einstellungen temporär aufgehoben "
                f"(für {int(self.unlock_timeout_seconds / 60)} Minuten).",
            )
        else:
            self.unlocked_until = 0.0
            log_info(
                self.logger,
                "Schreibschutz für Kamin-Einstellungen aktiviert.",
            )
        self.publisher.publish_settings_lock(self.is_unlocked)

    def check_auto_lock(self) -> None:
        """Wird zyklisch aufgerufen, um abgelaufene Freigaben wieder zu sperren."""
        if self.unlocked_until > 0.0 and not self.is_unlocked:
            self.unlocked_until = 0.0
            log_info(
                self.logger,
                "Freigabefenster abgelaufen: Schreibschutz für Kamin-Einstellungen automatisch aktiviert.",
            )
            self.publisher.publish_settings_lock(False)

    def refresh_from_controller(self) -> None:
        """Liest die aktuellen Einstellungen direkt vom Kamin."""
        try:
            settings = self.diagnostics_client.read_controller_settings()
            self.current_state = SettingsState(
                closing_delay_minutes=settings.closing_delay_minutes,
                raw_payload=settings.raw_payload,
                last_updated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            )
            self.storage.save(self.current_state)
            self.publisher.publish_closing_delay(settings.closing_delay_minutes)
        except DeviceDiagnosticsReadError as error:
            log_warning(
                self.logger,
                f"Kamin-Einstellungen konnten nicht gelesen werden: {error}",
            )

    def handle_lock_command(self, payload: str) -> None:
        """Verarbeitet einen MQTT-Schaltbefehl für den Schreibschutz."""
        normalized = payload.strip().upper()
        unlock = normalized in ("ON", "1", "TRUE", "UNLOCK", "UNLOCKED")
        self.set_lock_state(unlock)

    def handle_closing_delay_command(
        self,
        new_delay_text: str,
        live_status: LiveStatus | None,
    ) -> bool:
        """Verarbeitet eine Anforderung zur Änderung der Schließzeitverzögerung."""
        self.check_auto_lock()
        try:
            new_delay = int(float(new_delay_text.strip()))
        except ValueError:
            log_warning(
                self.logger,
                f"Ungültiger Wert für Schließzeitverzögerung empfangen: {new_delay_text!r}",
            )
            self.publish_current_state()
            return False

        if not self.is_unlocked:
            log_warning(
                self.logger,
                f"Änderung der Schließzeitverzögerung auf {new_delay} min abgewiesen: "
                "Schreibschutz ist aktiv! Vorher den Switch in Home Assistant einschalten.",
            )
            self.publish_current_state()
            return False

        if live_status is not None and live_status.flap_moving:
            log_warning(
                self.logger,
                f"Änderung der Schließzeitverzögerung auf {new_delay} min abgewiesen: "
                "Luftklappe bewegt sich aktuell.",
            )
            self.publish_current_state()
            return False

        if not (0 <= new_delay <= 120):
            log_warning(
                self.logger,
                f"Schließzeitverzögerung {new_delay} min liegt außerhalb des erlaubten Bereichs (0-120 min).",
            )
            self.publish_current_state()
            return False

        log_info(
            self.logger,
            f"Schreibe neue Schließzeitverzögerung auf Kamin-Steuerung: {new_delay} min ...",
        )

        try:
            updated = self.diagnostics_client.set_closing_delay(new_delay)
            self.current_state = SettingsState(
                closing_delay_minutes=updated.closing_delay_minutes,
                raw_payload=updated.raw_payload,
                last_updated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            )
            self.storage.save(self.current_state)
            self.publisher.publish_closing_delay(updated.closing_delay_minutes)
            log_info(
                self.logger,
                f"Schließzeitverzögerung erfolgreich auf {updated.closing_delay_minutes} min gesetzt und verifiziert.",
            )
            return True
        except (DeviceDiagnosticsReadError, ValueError) as error:
            log_error(
                self.logger,
                f"Fehler beim Setzen der Schließzeitverzögerung: {error}",
            )
            self.publish_current_state()
            return False


def create_default_settings_storage(project_dir: Path) -> SettingsStateStorage:
    return SettingsStateStorage(project_dir / "data" / "settings" / "state.json")
