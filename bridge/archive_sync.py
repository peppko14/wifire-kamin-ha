#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Koordination von MQTT-Archiv und lokaler Abbrandhistorie."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from bridge.archive import build_archive_attributes
from history.manager import HistoryManager, HistorySyncResult
from history.sync import (
    ArchiveReadResult,
    ArchiveSyncSettings,
    Decoder,
    RawReader,
    RecordAdapter as HistoryRecordAdapter,
    synchronize_archives,
)
from protocol.adapters import archive_record_to_burn_record
from wifire_protocol import decode_archive_record


__version__ = "1.3.0"


Sleeper = Callable[[int | float], None]
RunningCheck = Callable[[], bool]
Logger = Callable[[str], None]
RecordAdapter = Callable[[Any], Any]
AttributesBuilder = Callable[[Any], dict[str, object]]
CompletionCallback = Callable[[], Any]


class ArchiveReaderLike(Protocol):
    def read_record(self, command: str) -> Any:
        ...


class ArchivePublisherLike(Protocol):
    def publish_archive(
        self,
        number: int,
        *,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        ...


class HistoryManagerLike(Protocol):
    def synchronize(self, records: list[Any]) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class RingBufferArchiveSynchronizer:
    """Bindet den lokalen Ringpuffer-Abgleich in die Bridge ein.

    Die ersten drei Archivplätze werden weiterhin in MQTT veröffentlicht.
    Die lokale Speicherung aller relevanten Plätze geschieht vorher und ist
    daher nicht vom MQTT-Ergebnis abhängig.
    """

    settings: ArchiveSyncSettings
    history_manager: HistoryManager
    publisher: ArchivePublisherLike
    sleeper: Sleeper
    is_running: RunningCheck = lambda: True
    logger: Logger = print
    mqtt_archive_count: int = 3
    raw_reader: RawReader | None = None
    decoder: Decoder = decode_archive_record
    record_adapter: HistoryRecordAdapter = archive_record_to_burn_record
    attributes_builder: AttributesBuilder = build_archive_attributes
    on_complete: CompletionCallback | None = None

    def _publish_after_local_storage(
        self,
        number: int,
        archive_record: Any,
        sync_result: HistorySyncResult,
    ) -> None:
        """Aktualisiert optionale MQTT-Archive nach lokalem Speichern."""
        if number > self.mqtt_archive_count:
            return

        timestamp = archive_record.timestamp
        if timestamp is None:
            return

        self.publisher.publish_archive(
            number,
            state=timestamp.isoformat(timespec="seconds"),
            attributes=self.attributes_builder(archive_record),
        )

    def synchronize(self) -> ArchiveReadResult:
        """Führt genau einen lokalen Ringpuffer-Abgleich aus."""
        self.logger("Ringpuffer-Synchronisation wird gestartet.")
        result = synchronize_archives(
            self.history_manager,
            self.settings,
            raw_reader=self.raw_reader,
            decoder=self.decoder,
            record_adapter=self.record_adapter,
            sleeper=self.sleeper,
            logger=self.logger,
            on_record_synchronized=self._publish_after_local_storage,
            is_running=self.is_running,
        )

        if self.on_complete is not None:
            try:
                self.on_complete()
            except Exception as error:  # optionale nachgelagerte Integration
                self.logger(
                    "Historienausgaben konnten nicht aktualisiert werden: "
                    f"{error}"
                )

        self.logger(
            "Ringpuffer-Synchronisation beendet: "
            f"{result.sync_result.imported_count} neu, "
            f"{result.sync_result.existing_count} vorhanden, "
            f"{result.sync_result.skipped_incomplete} unvollständig, "
            f"{result.read_failures} Lesefehler."
        )
        return result


@dataclass(frozen=True, slots=True)
class ArchiveSynchronizer:
    """Synchronisiert bekannte Archive mit MQTT und lokaler Historie."""

    commands: tuple[tuple[str, str], ...]
    reader: ArchiveReaderLike
    publisher: ArchivePublisherLike
    history_manager: HistoryManagerLike
    request_delay: int | float
    sleeper: Sleeper
    is_running: RunningCheck
    logger: Logger = print
    record_adapter: RecordAdapter = archive_record_to_burn_record
    attributes_builder: AttributesBuilder = build_archive_attributes

    def synchronize(self) -> None:
        """Führt einen vollständigen Archivabgleich aus."""
        self.logger("Archivaktualisierung wird gestartet.")

        for index, (name, command) in enumerate(
            self.commands,
            start=1,
        ):
            if not self.is_running():
                return

            try:
                record = self.reader.read_record(command)

                if record.timestamp is None:
                    self.logger(
                        f"{name}: kein gültiger Zeitstempel – "
                        f"übersprungen."
                    )
                    continue

                state = record.timestamp.isoformat(
                    timespec="seconds"
                )

                self.publisher.publish_archive(
                    index,
                    state=state,
                    attributes=self.attributes_builder(record),
                )

                self.logger(
                    f"{name}: {state}, Maximum "
                    f"{record.max_temperature_c} °C, "
                    f"{record.measurement_count} Messpunkte."
                )

                burn_record = self.record_adapter(record)
                history_result = self.history_manager.synchronize(
                    [burn_record]
                )

                if history_result.imported_count:
                    self.logger(
                        f"{name}: neuer Abbrand lokal unter "
                        f"data/history gespeichert."
                    )
                elif history_result.existing_count:
                    self.logger(
                        f"{name}: Abbrand bereits in lokaler "
                        f"Historie."
                    )
                elif history_result.skipped_incomplete:
                    self.logger(
                        f"{name}: unvollständiger Abbrand "
                        f"nicht gespeichert."
                    )

            except (RuntimeError, ValueError) as error:
                self.logger(f"{name}: Archivfehler: {error}")

            if index < len(self.commands):
                self.sleeper(self.request_delay)

        self.logger("Archivaktualisierung beendet.")
