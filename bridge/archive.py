#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Lesender Zugriff auf die Archivdaten des WiFire-Kamins."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Protocol
from urllib.request import Request, urlopen

from bridge.logging_setup import log_warning
from protocol.duration import (
    DURATION_SOURCE_STAGE_0,
    calculate_duration_minutes,
)
from wifire_protocol import decode_archive_record




class HttpResponse(Protocol):
    """Benötigte Schnittstelle einer HTTP-Antwort."""

    def read(self) -> bytes:
        ...


class UrlOpener(Protocol):
    """Benötigte Schnittstelle zum Öffnen eines HTTP-Requests."""

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> ContextManager[HttpResponse]:
        ...


def open_url(
    request: Request,
    *,
    timeout: int,
) -> ContextManager[HttpResponse]:
    """Ruft den Standard-URL-Opener mit klarer Testschnittstelle auf."""
    return urlopen(request, timeout=timeout)


ArchiveDecoder = Callable[[str], Any]
Sleeper = Callable[[int | float], None]
Logger = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ArchiveReader:
    """Liest und dekodiert Archivblöcke mit Wiederholungen."""

    archive_url: str
    request_timeout: int = 15
    retry_count: int = 3
    retry_delay: int | float = 5
    sleeper: Sleeper = time.sleep
    opener: UrlOpener = open_url
    decoder: ArchiveDecoder = decode_archive_record
    logger: Logger = print

    def read_raw(self, command: str) -> str:
        """Liest einen rohen Archivblock."""
        last_error: Exception | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                body = json.dumps(
                    {"raw": command}
                ).encode("utf-8")

                request = Request(
                    self.archive_url,
                    data=body,
                    headers={
                        "Content-Type": "text/plain",
                        "Accept": "application/json",
                        "Connection": "close",
                    },
                    method="POST",
                )

                with self.opener(
                    request,
                    timeout=self.request_timeout,
                ) as response:
                    result = json.loads(
                        response.read().decode("utf-8")
                    )

                raw = result.get("raw")
                if not isinstance(raw, str):
                    raise ValueError(
                        "Archivantwort enthält kein gültiges "
                        "Feld 'raw'."
                    )

                bytes.fromhex(raw)
                return raw

            except (OSError, ValueError) as error:
                last_error = error

                log_warning(
                    self.logger,
                    f"Archivversuch {attempt}/{self.retry_count} "
                    f"fehlgeschlagen: {error}"
                )

                if attempt < self.retry_count:
                    self.sleeper(self.retry_delay)

        raise RuntimeError(
            f"Archivabfrage nach {self.retry_count} Versuchen "
            f"fehlgeschlagen: {last_error}"
        )

    def read_record(self, command: str) -> Any:
        """Liest und dekodiert einen Archivblock."""
        return self.decoder(self.read_raw(command))


def build_archive_attributes(
    record: Any,
) -> dict[str, object]:
    """Erzeugt die MQTT-Attribute eines Archivdatensatzes."""
    timestamp = (
        record.timestamp.isoformat(timespec="minutes")
        if record.timestamp
        else None
    )
    duration = calculate_duration_minutes(
        stage_90_minute=record.stage_90_minute,
        stage_75_minute=record.stage_75_minute,
        stage_50_minute=record.stage_50_minute,
        stage_25_minute=record.stage_25_minute,
        stage_0_minute=record.stage_0_minute,
    )

    return {
        "archive_number": record.archive_number,
        "start": timestamp,
        "measurement_count": record.measurement_count,
        "duration_minutes": duration,
        "duration_source": (
            DURATION_SOURCE_STAGE_0 if duration is not None else None
        ),
        "start_temperature_c": record.start_temperature_c,
        "end_temperature_c": record.end_temperature_c,
        "max_temperature_c": record.max_temperature_c,
        "max_temperature_minute": (
            record.max_temperature_minute
        ),
        "stage_90_minute": record.stage_90_minute,
        "stage_75_minute": record.stage_75_minute,
        "stage_50_minute": record.stage_50_minute,
        "stage_25_minute": record.stage_25_minute,
        "stage_0_minute": record.stage_0_minute,
        "temperatures_c": record.temperatures,
    }
