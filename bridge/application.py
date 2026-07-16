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
from bridge.dashboard_reporter import (
    DashboardCurveReporter,
    parse_dashboard_since,
)
from bridge.logging_setup import configure_logging, log_warning
from bridge.mqtt_client import MqttConnection
from bridge.polling import LivePoller, PollingSettings
from bridge.runtime import BridgeRuntime
from bridge.scheduler import InterruptibleSleeper, IntervalSchedule
from bridge.statistics import (
    HistoryStatisticsReporter,
    parse_statistics_since,
)
from bridge.topics import MqttTopics
from decoder import read_live_data
from history.manager import create_default_history_manager
from history.sync import ArchiveSyncSettings
from protocol.live import decode_live_status




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


class HistoryReporterLike(Protocol):
    def refresh(self) -> object:
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


def refresh_history_outputs(
    statistics_reporter: HistoryReporterLike,
    dashboard_reporter: HistoryReporterLike,
    *,
    logger: Logger = print,
) -> None:
    """Aktualisiert Historienausgaben unabhängig voneinander."""
    reporters = (
        ("Historienstatistik", statistics_reporter),
        ("Brennkurven-Vergleich", dashboard_reporter),
    )
    for name, reporter in reporters:
        try:
            reporter.refresh()
        except (OSError, RuntimeError, ValueError) as error:
            log_warning(
                logger,
                f"{name} konnte nicht aktualisiert werden: {error}",
            )


def create_application(
    config_module: Any,
    *,
    project_dir: Path,
    app_name: str,
    app_version: str,
) -> BridgeApplication:
    """Erzeugt die vollständig konfigurierte Bridge-Anwendung."""
    logger = configure_logging(
        getattr(config_module, "LOG_LEVEL", "INFO")
    )
    running_state = RunningState()
    topics = MqttTopics(
        device_id=config_module.DEVICE_ID,
        discovery_prefix=config_module.MQTT_DISCOVERY_PREFIX,
    )
    polling_settings = PollingSettings.from_config(
        config_module
    )
    sleeper = InterruptibleSleeper(running_state)
    live_poller = LivePoller(
        read_live_data,
        decode_live_status,
        retry_count=polling_settings.live_retry_count,
        retry_delay_seconds=(
            polling_settings.live_retry_delay_seconds
        ),
        sleeper=sleeper,
        is_running=running_state,
        logger=logger,
    )
    connection = MqttConnection(
        config_module,
        topics,
        app_name=app_name,
        app_version=app_version,
        is_running=running_state,
        logger=logger,
    )
    history_manager = create_default_history_manager(
        project_dir,
        logger=logger,
    )
    statistics_reporter = HistoryStatisticsReporter(
        history_provider=history_manager,
        publisher=connection.publisher,
        since=parse_statistics_since(
            getattr(config_module, "STATISTICS_SINCE", None)
        ),
        logger=logger,
    )
    dashboard_since = parse_dashboard_since(
        getattr(
            config_module,
            "DASHBOARD_CURVES_SINCE",
            getattr(config_module, "STATISTICS_SINCE", None),
        )
    )
    dashboard_reporter = DashboardCurveReporter(
        history_directory=history_manager.storage.directory,
        publisher=connection.publisher,
        since=dashboard_since,
        include_warnings=getattr(
            config_module,
            "DASHBOARD_INCLUDE_WARNINGS",
            True,
        ),
        logger=logger,
    )

    archive_settings = build_archive_sync_settings(config_module)
    archive_synchronizer = RingBufferArchiveSynchronizer(
        settings=archive_settings,
        publisher=connection.publisher,
        history_manager=history_manager,
        sleeper=sleeper,
        is_running=running_state,
        logger=logger,
        on_complete=lambda: refresh_history_outputs(
            statistics_reporter,
            dashboard_reporter,
            logger=logger,
        ),
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
        logger=logger,
    )

    return BridgeApplication(
        connection=connection,
        runtime=runtime,
        running_state=running_state,
        logger=logger,
    )
