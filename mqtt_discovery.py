#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""WiFire-Kamin MQTT Bridge."""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any

import config
from bridge.archive import (
    ArchiveReader,
)
from bridge.archive_sync import ArchiveSynchronizer
from bridge.mqtt_client import MqttConnection
from bridge.polling import (
    LivePoller,
    PollingSettings,
)
from bridge.runtime import BridgeRuntime
from bridge.scheduler import (
    InterruptibleSleeper,
    IntervalSchedule,
)
from bridge.topics import MqttTopics
from decoder import decode_live_data, read_live_data
from history.manager import create_default_history_manager
from history.sync import build_archive_url
from version import APP_VERSION


APP_NAME = "WiFire-Kamin MQTT Bridge"

TOPICS = MqttTopics(
    device_id=config.DEVICE_ID,
    discovery_prefix=config.MQTT_DISCOVERY_PREFIX,
)

POLLING_SETTINGS = PollingSettings.from_config(config)
LIVE_POLLER = LivePoller(read_live_data, decode_live_data)
OFFLINE_AFTER_FAILURES = getattr(
    config,
    "OFFLINE_AFTER_FAILURES",
    3,
)

ARCHIVE_UPDATE_INTERVAL = getattr(
    config,
    "ARCHIVE_UPDATE_INTERVAL",
    21600,
)
ARCHIVE_REQUEST_DELAY = getattr(
    config,
    "ARCHIVE_REQUEST_DELAY",
    10,
)
ARCHIVE_REQUEST_TIMEOUT = getattr(
    config,
    "ARCHIVE_REQUEST_TIMEOUT",
    15,
)
ARCHIVE_RETRY_COUNT = getattr(
    config,
    "ARCHIVE_RETRY_COUNT",
    3,
)
ARCHIVE_RETRY_DELAY = getattr(
    config,
    "ARCHIVE_RETRY_DELAY",
    10,
)

ARCHIVE_URL = build_archive_url(config.WIFIRE_URL)
ARCHIVE_COMMANDS = {
    "archive_1": "aacc3355023501ffff",
    "archive_2": "aacc3355023502ffff",
    "archive_3": "aacc3355023503ffff",
}

running = True


def stop_program(*_: Any) -> None:
    """Beendet die Hauptschleife kontrolliert."""
    global running
    running = False


def main() -> None:
    """Startet die MQTT-Bridge und die adaptive Polling-Schleife."""
    signal.signal(signal.SIGINT, stop_program)
    signal.signal(signal.SIGTERM, stop_program)

    connection = MqttConnection(
        config,
        TOPICS,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        is_running=lambda: running,
    )
    publisher = connection.publisher

    archive_schedule = IntervalSchedule(
        ARCHIVE_UPDATE_INTERVAL
    )
    sleeper = InterruptibleSleeper(lambda: running)

    project_dir = Path(__file__).resolve().parent
    history_manager = create_default_history_manager(
        project_dir
    )
    archive_reader = ArchiveReader(
        archive_url=ARCHIVE_URL,
        request_timeout=ARCHIVE_REQUEST_TIMEOUT,
        retry_count=ARCHIVE_RETRY_COUNT,
        retry_delay=ARCHIVE_RETRY_DELAY,
        sleeper=sleeper,
    )
    archive_synchronizer = ArchiveSynchronizer(
        commands=tuple(ARCHIVE_COMMANDS.items()),
        reader=archive_reader,
        publisher=publisher,
        history_manager=history_manager,
        request_delay=ARCHIVE_REQUEST_DELAY,
        sleeper=sleeper,
        is_running=lambda: running,
    )
    runtime = BridgeRuntime(
        live_poller=LIVE_POLLER,
        publisher=publisher,
        archive_synchronizer=archive_synchronizer,
        archive_schedule=archive_schedule,
        polling_settings=POLLING_SETTINGS,
        sleeper=sleeper,
        is_running=lambda: running,
        offline_after_failures=OFFLINE_AFTER_FAILURES,
        on_state=connection.remember_state,
    )

    connection.start()

    try:
        runtime.run()

    finally:
        connection.stop()

        print("WiFire-Kamin MQTT Bridge beendet.")


if __name__ == "__main__":
    main()
