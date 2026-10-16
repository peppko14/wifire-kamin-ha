# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""
Steuerung der wöchentlichen Zeitsynchronisation mit Nachholprinzip und manuellem Trigger.

Regeln:
1. Reguläre Fälligkeit: Dienstags ab 06:00 Uhr lokaler Zeit (Wochentag 1).
2. Nachhol-Prinzip (Catch-Up): Wird Dienstag verpasst (Kamin aktiv, Raspberry offline,
   Netzwerk getrennt), bleibt die Fälligkeit für die gesamte Kalenderwoche vorgemerkt
   und wird beim ersten erkannten Ruhezustand nachgeholt.
3. Drift-Guard: Ist die letzte erfolgreiche Synchronisation länger als 7 Tage her
   und die gemessene Abweichung beträgt mehr als 60 Sekunden, wird die Synchronisation
   beim nächsten Ruhezustand nachgeholt.
4. Schutzprüfungen vor Ausführung:
   - Kamin nachweislich inaktiv (Luftklappe 0 %, keine laufende Brennkurve)
   - Aktuelle Livedaten vorhanden und frisch
   - Host-Systemzeit per NTP synchronisiert
5. Manueller Trigger: Über MQTT-Button (Home Assistant) jederzeit anstoßbar
   (unterliegt denselben Schutzprüfungen).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import subprocess
from typing import Any, Callable, Protocol

from bridge.logging_setup import log_error, log_info, log_warning
from protocol.device_diagnostics import ControllerTime
from protocol.models import LiveStatus


TIME_SYNC_SCHEMA_VERSION = 1
DEFAULT_TARGET_WEEKDAY = 1  # Dienstag (0=Mo, 1=Di, 2=Mi, 3=Do, 4=Fr, 5=Sa, 6=So)
DEFAULT_TARGET_HOUR = 6
DEFAULT_TARGET_MINUTE = 0
DEFAULT_DRIFT_THRESHOLD_SECONDS = 60.0
DEFAULT_MAX_DAYS_BEFORE_DRIFT_SYNC = 7

Logger = Callable[[str], None]
Clock = Callable[[], datetime]
RunningCheck = Callable[[], bool]
HostTimeCheck = Callable[[], bool]


def is_host_time_synchronized() -> bool:
    """Prüft, ob die Systemzeit des Hosts (z. B. Raspberry Pi) per NTP synchronisiert ist."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized", "--value"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower() in ("yes", "true", "1")
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError):
        pass
    # Auf Systemen ohne timedatectl (oder in Testumgebungen) keine Blockade
    return True


class DeviceDiagnosticsClientLike(Protocol):
    def read_controller_time(self) -> ControllerTime:
        ...

    def set_controller_time(self, target_time: datetime) -> ControllerTime:
        ...


class TimeSyncPublisherLike(Protocol):
    def publish_time_sync_state(self, payload: dict[str, object]) -> None:
        ...



@dataclass(frozen=True, slots=True)
class TimeSyncState:
    """Persistenter Zustand der Zeitsynchronisation."""

    schema_version: int = TIME_SYNC_SCHEMA_VERSION
    last_synced_week: str | None = None
    last_synced_at: str | None = None
    last_offset_seconds: float | None = None
    status: str = "idle"
    message: str = "Bereit"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeSyncState:
        return cls(
            schema_version=int(data.get("schema_version", TIME_SYNC_SCHEMA_VERSION)),
            last_synced_week=data.get("last_synced_week"),
            last_synced_at=data.get("last_synced_at"),
            last_offset_seconds=(
                float(data["last_offset_seconds"])
                if data.get("last_offset_seconds") is not None
                else None
            ),
            status=str(data.get("status", "idle")),
            message=str(data.get("message", "Bereit")),
        )


@dataclass(frozen=True, slots=True)
class TimeSyncStateStorage:
    """Atomare Speicherung des Synchronisationszustands."""

    path: Path

    def load(self) -> TimeSyncState:
        target = self.path.resolve()
        if not target.exists():
            return TimeSyncState()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            return TimeSyncState.from_dict(payload)
        except (OSError, ValueError, TypeError):
            return TimeSyncState()

    def save(self, state: TimeSyncState) -> None:
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


def get_calendar_week(dt: datetime) -> str:
    """Gibt die ISO-Kalenderwoche im Format YYYY-Www zurück."""
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def is_time_sync_due(
    now: datetime,
    state: TimeSyncState,
    *,
    target_weekday: int = DEFAULT_TARGET_WEEKDAY,
    target_hour: int = DEFAULT_TARGET_HOUR,
    target_minute: int = DEFAULT_TARGET_MINUTE,
    drift_seconds: float | None = None,
    drift_threshold_seconds: float = DEFAULT_DRIFT_THRESHOLD_SECONDS,
    max_days_before_drift_sync: int = DEFAULT_MAX_DAYS_BEFORE_DRIFT_SYNC,
) -> tuple[bool, str]:
    """
    Prüft, ob eine Zeitsynchronisation ansteht (regulär, per Nachholprinzip oder Drift-Guard).

    Gibt (True/False, Begründung) zurück.
    """
    current_week = get_calendar_week(now)

    # 1. Hat die aktuelle Woche den Sync bereits erfolgreich durchgeführt?
    if state.last_synced_week == current_week:
        # Prüfe optionalen Drift-Guard (nach mehr als 7 Tagen bei massiver Drift)
        if state.last_synced_at is not None and drift_seconds is not None:
            try:
                last_dt = datetime.fromisoformat(state.last_synced_at)
                days_since = (now - last_dt).total_seconds() / 86400.0
                if days_since >= max_days_before_drift_sync and abs(drift_seconds) >= drift_threshold_seconds:
                    return True, f"Drift-Guard aktiv: Abweichung {drift_seconds:+.1f}s nach {days_since:.1f} Tagen"
            except (ValueError, TypeError):
                pass
        return False, "Kalenderwoche bereits synchronisiert"

    # 2. Kalenderwoche noch nicht synchronisiert: Prüfen, ob Termin erreicht oder verpasst (Catch-Up)
    # Ist der aktuelle Zeitpunkt am oder nach dem Ziel-Wochentag/Uhrzeit?
    target_time_passed = (
        now.weekday() > target_weekday
        or (now.weekday() == target_weekday and (now.hour, now.minute) >= (target_hour, target_minute))
    )

    if target_time_passed:
        if now.weekday() == target_weekday and now.hour == target_hour:
            return True, f"Regulärer Termin fällig ({current_week}, Di 06:00)"
        return True, f"Nachhol-Termin fällig ({current_week}, Termin war Di 06:00)"

    return False, f"Warte auf regulären Termin ({current_week}, Di 06:00)"


def can_synchronize(
    live_status: LiveStatus | None,
    *,
    is_curve_active: bool,
    ntp_synchronized: bool = True,
) -> tuple[bool, str]:
    """Prüft alle Sicherheitsbedingungen vor einem Schreibzugriff."""
    if not ntp_synchronized:
        return False, "Sperre: Raspberry-Pi-Systemzeit ist nicht per NTP synchronisiert."

    if live_status is None:
        return False, "Sperre: Keine aktuellen Live-Daten von der WiFire-Steuerung verfügbar."

    if live_status.flap_percent > 0:
        return False, f"Sperre: Kamin aktiv (Luftklappe steht bei {live_status.flap_percent} %)."

    if live_status.flap_moving:
        return False, "Sperre: Luftklappe bewegt sich aktuell."

    if is_curve_active:
        return False, "Sperre: Brennkurven-Aufzeichnung ist noch aktiv."

    return True, "Freigegeben: Kamin nachweislich inaktiv und Systemuhr synchron."


def create_default_time_sync_storage(project_dir: Path) -> TimeSyncStateStorage:
    return TimeSyncStateStorage(project_dir / "data" / "time-sync" / "state.json")


@dataclass(slots=True)
class TimeSyncManager:
    """Verwaltet den Lebenszyklus, Nachhol-Prüfung und Ausführung der Zeitsynchronisation."""

    storage: TimeSyncStateStorage
    diagnostics_client: DeviceDiagnosticsClientLike
    publisher: TimeSyncPublisherLike
    enabled: bool = True
    target_weekday: int = DEFAULT_TARGET_WEEKDAY
    target_hour: int = DEFAULT_TARGET_HOUR
    target_minute: int = DEFAULT_TARGET_MINUTE
    clock: Clock = datetime.now
    is_running: RunningCheck = lambda: True
    host_time_check: HostTimeCheck = is_host_time_synchronized
    logger: Logger = print
    current_state: TimeSyncState = field(init=False)

    def __post_init__(self) -> None:
        self.current_state = self.storage.load()

    def publish_current_state(self) -> None:
        """Veröffentlicht den aktuellen Zustand per MQTT an Home Assistant."""
        self.publisher.publish_time_sync_state(self.current_state.to_dict())

    def check_if_due(
        self,
        live_status: LiveStatus | None,
        *,
        is_curve_active: bool,
        current_offset_seconds: float | None = None,
        ntp_synchronized: bool | None = None,
    ) -> bool:
        """Wird zyklisch aufgerufen: Prüft Fälligkeit und führt bei Ruhezustand den Sync aus."""
        if not self.enabled:
            return False

        now = self.clock().astimezone()
        due, reason = is_time_sync_due(
            now,
            self.current_state,
            target_weekday=self.target_weekday,
            target_hour=self.target_hour,
            target_minute=self.target_minute,
            drift_seconds=current_offset_seconds,
        )

        if not due:
            return False

        ntp_ok = (
            self.host_time_check()
            if ntp_synchronized is None
            else ntp_synchronized
        )
        allowed, safety_reason = can_synchronize(
            live_status,
            is_curve_active=is_curve_active,
            ntp_synchronized=ntp_ok,
        )

        if not allowed:
            if self.current_state.status != "blocked":
                self.current_state = TimeSyncState(
                    schema_version=self.current_state.schema_version,
                    last_synced_week=self.current_state.last_synced_week,
                    last_synced_at=self.current_state.last_synced_at,
                    last_offset_seconds=self.current_state.last_offset_seconds,
                    status="blocked",
                    message=f"{reason} (Wartet auf Ruhezustand: {safety_reason})",
                )
                self.storage.save(self.current_state)
                self.publish_current_state()
                log_info(self.logger, f"Zeitsynchronisation vorgemerkt: {safety_reason}")
            return False

        return self.execute_sync(reason=reason, manual=False)

    def trigger_manual_sync(
        self,
        live_status: LiveStatus | None,
        *,
        is_curve_active: bool,
        ntp_synchronized: bool | None = None,
    ) -> bool:
        """Wird über den MQTT-Button aus Home Assistant ausgelöst."""
        log_info(self.logger, "Manuelle Zeitsynchronisation per Home-Assistant-Button angefordert.")

        ntp_ok = (
            self.host_time_check()
            if ntp_synchronized is None
            else ntp_synchronized
        )
        allowed, safety_reason = can_synchronize(
            live_status,
            is_curve_active=is_curve_active,
            ntp_synchronized=ntp_ok,
        )

        if not allowed:
            self.current_state = TimeSyncState(
                schema_version=self.current_state.schema_version,
                last_synced_week=self.current_state.last_synced_week,
                last_synced_at=self.current_state.last_synced_at,
                last_offset_seconds=self.current_state.last_offset_seconds,
                status="blocked",
                message=f"Manueller Sync abgelehnt: {safety_reason}",
            )
            self.storage.save(self.current_state)
            self.publish_current_state()
            log_warning(self.logger, f"Manueller Sync verweigert: {safety_reason}")
            return False

        return self.execute_sync(reason="Manueller Button-Klick", manual=True)

    def execute_sync(self, *, reason: str, manual: bool) -> bool:
        """Führt den geschützten Synchronisationsablauf aus."""
        now = self.clock().astimezone()
        now_iso = now.isoformat(timespec="seconds")
        current_week = get_calendar_week(now)

        log_info(self.logger, f"Zeitsynchronisation gestartet ({reason}).")

        # 1. Steuerungszeit vorab lesen und protokollieren
        pre_offset_seconds: float | None = None
        try:
            ctrl_time = self.diagnostics_client.read_controller_time()
            pre_offset_seconds = (ctrl_time.value.astimezone() - now).total_seconds()
            log_info(
                self.logger,
                f"Steuerungszeit vorab: {ctrl_time.value.isoformat(timespec='minutes')} "
                f"(Abweichung: {pre_offset_seconds:+.1f} Sekunden).",
            )
        except Exception as error:
            log_warning(self.logger, f"Vorab-Lesen der Steuerungszeit fehlgeschlagen: {error}")

        # 2. Schreibender Abgleich auf die Steuerung per POST /direct/23
        post_offset_seconds: float | None = None
        try:
            confirmed_time = self.diagnostics_client.set_controller_time(now)
            post_offset_seconds = (confirmed_time.value.astimezone() - now).total_seconds()
            log_info(
                self.logger,
                f"Steuerungszeit erfolgreich gesetzt auf {confirmed_time.value.isoformat(timespec='minutes')} "
                f"(Restabweichung: {post_offset_seconds:+.1f} Sekunden).",
            )
        except Exception as error:
            log_error(self.logger, f"Schreiben der Steuerungszeit fehlgeschlagen: {error}")
            self.current_state = TimeSyncState(
                schema_version=TIME_SYNC_SCHEMA_VERSION,
                last_synced_week=self.current_state.last_synced_week,
                last_synced_at=self.current_state.last_synced_at,
                last_offset_seconds=pre_offset_seconds,
                status="error",
                message=f"Schreibfehler: {error}",
            )
            self.storage.save(self.current_state)
            self.publish_current_state()
            return False

        # 3. Zustand atomar persistieren
        self.current_state = TimeSyncState(
            schema_version=TIME_SYNC_SCHEMA_VERSION,
            last_synced_week=current_week,
            last_synced_at=now_iso,
            last_offset_seconds=post_offset_seconds,
            status="completed",
            message=f"Erfolgreich ({reason}, KW {current_week})",
        )
        self.storage.save(self.current_state)
        self.publish_current_state()
        log_info(self.logger, f"Zeitsynchronisation abgeschlossen für {current_week}.")
        return True

