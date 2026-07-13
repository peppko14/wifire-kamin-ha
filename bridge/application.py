#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zusammenbau und Lebenszyklus der WiFire-Kamin-Bridge."""

from __future__ import annotations

import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from bridge.archive_sync import RingBufferArchiveSynchronizer
from bridge.mqtt_client import MqttConnection
from bridge.polling import LivePoller, PollingSettings
from bridge.runtime import BridgeRuntime
from bridge.scheduler import InterruptibleSleeper, IntervalSchedule
from bridge.topics import MqttTopics
from decoder import decode_live_data, read_live_data
from history.manager import create_default_history_manager
from history.sync import ArchiveSyncSettings


__version__ = "1.1.0"


Logger = Callable[[str], None]
SignalRegistrar = Callable[[int, Any], Any]


class ConnectionLike(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...


class RuntimeLike(Protocol):
    def run(self) -> None:
        ...


@dataclass(slots=True)
class RunningState:
    """Gemeinsamer, kontrolliert veränderbarer Laufzustand."""

    running: bool = True

    def __call__(self) -> bool:
        return self.running

    def stop(self, *_: Any) -> None:
        """Fordert das kontrollierte Beenden an."""
        self.running = False


@dataclass(frozen=True, slots=True)
class BridgeApplication:
    """Startet und beendet MQTT-Verbindung und Bridge-Laufzeit."""

    connection: ConnectionLike
    runtime: RuntimeLike
    running_state: RunningState
    logger: Logger = print
    signal_registrar: SignalRegistrar = signal.signal

    def install_signal_handlers(self) -> None:
        """Registriert SIGINT und SIGTERM für kontrolliertes Beenden."""
        self.signal_registrar(
            signal.SIGINT,
            self.running_state.stop,
        )
        self.signal_registrar(
            signal.SIGTERM,
            self.running_state.stop,
        )

    def run(self) -> None:
        """Führt den vollständigen Anwendungslebenszyklus aus."""
        self.install_signal_handlers()
        self.connection.start()

        try:
            self.runtime.run()
        finally:
            self.connection.stop()
            self.logger("WiFire-Kamin MQTT Bridge beendet.")


def build_archive_sync_settings(config_module: Any) -> ArchiveSyncSettings:
    """Überträgt die portable Projektkonfiguration in Sync-Einstellungen."""
    return ArchiveSyncSettings(
        live_url=config_module.WIFIRE_URL,
        first_archive=getattr(config_module, "ARCHIVE_FIRST_SLOT", 1),
        last_archive=getattr(config_module, "ARCHIVE_LAST_SLOT", 23),
        request_timeout=getattr(
            config_module,
            "ARCHIVE_REQUEST_TIMEOUT",
            15,
        ),
        retry_count=getattr(config_module, "ARCHIVE_RETRY_COUNT", 3),
        retry_delay_seconds=getattr(
            config_module,
            "ARCHIVE_RETRY_DELAY",
            10,
        ),
        archive_delay_seconds=getattr(
            config_module,
            "ARCHIVE_REQUEST_DELAY",
            10,
        ),
    )


def create_application(
    config_module: Any,
    *,
    project_dir: Path,
    app_name: str,
    app_version: str,
) -> BridgeApplication:
    """Erzeugt die vollständig konfigurierte Bridge-Anwendung."""
    running_state = RunningState()
    topics = MqttTopics(
        device_id=config_module.DEVICE_ID,
        discovery_prefix=config_module.MQTT_DISCOVERY_PREFIX,
    )
    polling_settings = PollingSettings.from_config(
        config_module
    )
    live_poller = LivePoller(
        read_live_data,
        decode_live_data,
    )
    connection = MqttConnection(
        config_module,
        topics,
        app_name=app_name,
        app_version=app_version,
        is_running=running_state,
    )
    sleeper = InterruptibleSleeper(running_state)
    history_manager = create_default_history_manager(
        project_dir
    )
    archive_settings = build_archive_sync_settings(config_module)
    archive_synchronizer = RingBufferArchiveSynchronizer(
        settings=archive_settings,
        publisher=connection.publisher,
        history_manager=history_manager,
        sleeper=sleeper,
        is_running=running_state,
    )
    runtime = BridgeRuntime(
        live_poller=live_poller,
        publisher=connection.publisher,
        archive_synchronizer=archive_synchronizer,
        archive_schedule=IntervalSchedule(
            getattr(
                config_module,
                "ARCHIVE_UPDATE_INTERVAL",
                21600,
            )
        ),
        polling_settings=polling_settings,
        sleeper=sleeper,
        is_running=running_state,
        offline_after_failures=getattr(
            config_module,
            "OFFLINE_AFTER_FAILURES",
            3,
        ),
        on_state=connection.remember_state,
    )

    return BridgeApplication(
        connection=connection,
        runtime=runtime,
        running_state=running_state,
    )
