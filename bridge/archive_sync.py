#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Koordination von MQTT-Archiv und lokaler Abbrandhistorie."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from bridge.archive import build_archive_attributes
from protocol.adapters import archive_record_to_burn_record


__version__ = "1.0.0"


Sleeper = Callable[[int | float], None]
RunningCheck = Callable[[], bool]
Logger = Callable[[str], None]
RecordAdapter = Callable[[Any], Any]
AttributesBuilder = Callable[[Any], dict[str, object]]


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
