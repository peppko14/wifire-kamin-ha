# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Ausschließlich lesende Diagnosezugriffe auf die WiFire-Steuerung."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, ContextManager, Protocol
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


PACKET_HEADER = bytes.fromhex("aacc3355")
CLOCK_ENDPOINT = "22"
ALARMS_ENDPOINT = "04"
CLOCK_PACKET_LENGTH = 13
ALARM_PACKET_LENGTH = 429
ALARM_RECORD_COUNT = 10
ALARM_RECORD_LENGTH = 6
ALARM_RECORD_BYTES = ALARM_RECORD_COUNT * ALARM_RECORD_LENGTH
KNOWN_ALARM_LABELS = {1: "Heizfehler"}
ALLOWED_ENDPOINTS = frozenset({CLOCK_ENDPOINT, ALARMS_ENDPOINT})


class DeviceDiagnosticsReadError(RuntimeError):
    """Ein Diagnoseendpunkt konnte nach allen Versuchen nicht gelesen werden."""


class HttpResponse(Protocol):
    """Für eine Diagnoseantwort benötigte minimale Schnittstelle."""

    def read(self) -> bytes:
        ...


class UrlOpener(Protocol):
    """Austauschbarer URL-Opener für Tests und Produktivbetrieb."""

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> ContextManager[HttpResponse]:
        ...


Logger = Callable[[str], None]
Sleeper = Callable[[int | float], None]


def open_url(
    request: Request,
    *,
    timeout: int,
) -> ContextManager[HttpResponse]:
    """Öffnet den Request über die Standardbibliothek."""
    return urlopen(request, timeout=timeout)


@dataclass(frozen=True, slots=True)
class ControllerTime:
    """Von der internen WiFire-Uhr gelesener Zeitpunkt."""

    value: datetime
    month_flags: int
    raw: str

    def to_dict(self) -> dict[str, object]:
        """Gibt eine JSON-kompatible Darstellung zurück."""
        return {
            "value": self.value.isoformat(timespec="minutes"),
            "month_flags": self.month_flags,
        }


@dataclass(frozen=True, slots=True)
class AlarmEntry:
    """Ein einzelner, ausschließlich lesend ermittelter Alarmeintrag."""

    occurred_on: date | None
    code: int
    label: str
    value_byte: int
    metadata_byte: int
    raw_record: str

    def to_dict(self) -> dict[str, object]:
        """Gibt eine JSON-kompatible Darstellung zurück."""
        return {
            "occurred_on": (
                self.occurred_on.isoformat()
                if self.occurred_on is not None
                else None
            ),
            "code": self.code,
            "label": self.label,
            "value_byte": self.value_byte,
            "metadata_byte": self.metadata_byte,
            "raw_record": self.raw_record,
        }


@dataclass(frozen=True, slots=True)
class AlarmList:
    """Verifizierter Heizfehler-Block der Alarmliste."""

    entries: tuple[AlarmEntry, ...]
    raw: str

    def to_dict(self) -> dict[str, object]:
        """Gibt eine JSON-kompatible Darstellung zurück."""
        return {
            "count": len(self.entries),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def build_direct_url(live_url: str, endpoint: str) -> str:
    """Leitet einen bekannten, ausschließlich lesenden Endpunkt ab."""
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ValueError(f"Nicht freigegebener Diagnoseendpunkt: {endpoint!r}.")

    parsed = urlsplit(live_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("WIFIRE_URL ist keine gültige absolute URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] != "direct":
        raise ValueError(
            "WIFIRE_URL muss auf einen Endpunkt unter /direct/ zeigen."
        )

    parts[-1] = endpoint
    return urlunsplit(
        (parsed.scheme, parsed.netloc, "/" + "/".join(parts), "", "")
    )


def build_read_request(live_url: str, endpoint: str) -> Request:
    """Erzeugt einen GET-Request ohne schreibende Nutzlast."""
    return Request(
        build_direct_url(live_url, endpoint),
        headers={
            "Accept": "application/json",
            "Connection": "close",
        },
        method="GET",
    )


def _decode_hex(raw: str) -> bytes:
    try:
        return bytes.fromhex(raw)
    except ValueError as error:
        raise ValueError("Ungültiger Hex-Datensatz.") from error


def _validate_header(data: bytes) -> None:
    if data[:4] != PACKET_HEADER:
        raise ValueError("Unbekannter Paketkopf.")


def decode_controller_time(raw: str) -> ControllerTime:
    """Dekodiert die Antwort von ``GET /direct/22``."""
    data = _decode_hex(raw)
    if len(data) != CLOCK_PACKET_LENGTH:
        raise ValueError(
            "Steuerungszeit-Telegramm hat "
            f"{len(data)} statt {CLOCK_PACKET_LENGTH} Bytes."
        )
    _validate_header(data)
    if data[4] != 0x06 or data[5] != 0x22:
        raise ValueError("Unerwartetes Steuerungszeit-Telegramm.")

    month_flags = data[7] & 0xF0
    try:
        value = datetime(
            2000 + data[6],
            data[7] & 0x0F,
            data[8],
            data[9],
            data[10],
        )
    except ValueError as error:
        raise ValueError("Ungültige Steuerungszeit im Telegramm.") from error

    return ControllerTime(value=value, month_flags=month_flags, raw=raw)


def _decode_alarm_entry(record: bytes) -> AlarmEntry:
    occurred_on: date | None
    try:
        occurred_on = date(
            2000 + record[0],
            record[1] & 0x0F,
            record[2],
        )
    except ValueError:
        occurred_on = None

    code = record[3]
    return AlarmEntry(
        occurred_on=occurred_on,
        code=code,
        label=KNOWN_ALARM_LABELS.get(code, f"Unbekannter Alarm ({code})"),
        value_byte=record[4],
        metadata_byte=record[5],
        raw_record=record.hex(),
    )


def decode_alarm_list(raw: str) -> AlarmList:
    """Dekodiert den verifizierten Heizfehler-Block von ``/direct/04``.

    Die Antwort enthält sieben Blöcke zu je zehn Datensätzen. Nur der letzte
    Block stimmt vollständig mit den zehn in der App sichtbaren
    Heizfehler-Einträgen überein. Die übrigen Blöcke bleiben unangetastet,
    bis ihre Bedeutung separat belegt wurde.
    """
    data = _decode_hex(raw)
    if len(data) != ALARM_PACKET_LENGTH:
        raise ValueError(
            "Alarmtelegramm hat "
            f"{len(data)} statt {ALARM_PACKET_LENGTH} Bytes."
        )
    _validate_header(data)
    if data[4:7] != bytes.fromhex("ffa604"):
        raise ValueError("Unerwartetes Alarmtelegramm.")

    record_data = data[-(ALARM_RECORD_BYTES + 2) : -2]
    entries: list[AlarmEntry] = []
    for offset in range(0, len(record_data), ALARM_RECORD_LENGTH):
        record = record_data[offset : offset + ALARM_RECORD_LENGTH]
        if record == bytes(ALARM_RECORD_LENGTH):
            continue
        entries.append(_decode_alarm_entry(record))

    entries.sort(
        key=lambda entry: entry.occurred_on or date.min,
        reverse=True,
    )
    return AlarmList(entries=tuple(entries), raw=raw)


@dataclass(frozen=True, slots=True)
class DeviceDiagnosticsClient:
    """Liest nur die verifizierten Diagnoseendpunkte 22 und 04."""

    live_url: str
    request_timeout: int = 5
    retry_count: int = 2
    retry_delay_seconds: int | float = 2
    sleeper: Sleeper = time.sleep
    opener: UrlOpener = open_url
    logger: Logger = print

    def __post_init__(self) -> None:
        build_direct_url(self.live_url, CLOCK_ENDPOINT)
        if (
            isinstance(self.request_timeout, bool)
            or not isinstance(self.request_timeout, int)
            or self.request_timeout < 1
        ):
            raise ValueError("request_timeout muss mindestens 1 sein.")
        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or self.retry_count < 1
        ):
            raise ValueError("retry_count muss mindestens 1 sein.")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or self.retry_delay_seconds < 0
        ):
            raise ValueError("retry_delay_seconds darf nicht negativ sein.")

    def _read_raw(self, endpoint: str) -> str:
        last_error: OSError | ValueError | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                request = build_read_request(self.live_url, endpoint)
                with self.opener(
                    request,
                    timeout=self.request_timeout,
                ) as response:
                    result = json.loads(response.read().decode("utf-8"))

                if not isinstance(result, dict):
                    raise ValueError("Diagnoseantwort ist kein JSON-Objekt.")
                raw = result.get("raw")
                if not isinstance(raw, str) or not raw:
                    raise ValueError(
                        "Diagnoseantwort enthält kein gültiges raw-Feld."
                    )
                bytes.fromhex(raw)
                return raw
            except (OSError, ValueError) as error:
                last_error = error
                self.logger(
                    f"Diagnose /direct/{endpoint}, Versuch {attempt}/"
                    f"{self.retry_count} fehlgeschlagen: {error}"
                )
                if attempt < self.retry_count:
                    self.sleeper(self.retry_delay_seconds)

        raise DeviceDiagnosticsReadError(
            f"Diagnose /direct/{endpoint} konnte nach "
            f"{self.retry_count} Versuchen nicht gelesen werden: {last_error}"
        )

    def read_controller_time(self) -> ControllerTime:
        """Liest und dekodiert die interne Steuerungszeit."""
        return decode_controller_time(self._read_raw(CLOCK_ENDPOINT))

    def read_alarms(self) -> AlarmList:
        """Liest den verifizierten Heizfehler-Block der Alarmliste."""
        return decode_alarm_list(self._read_raw(ALARMS_ENDPOINT))
