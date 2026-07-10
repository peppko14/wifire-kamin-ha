#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


PACKET_HEADER = bytes.fromhex("aacc3355")

LIVE_MIN_LENGTH = 19

ARCHIVE_LENGTH = 506
ARCHIVE_DATA_START = 22
ARCHIVE_DATA_END = 504


@dataclass
class LiveStatus:
    temperature_c: int
    flap_percent: int
    flap_moving: bool
    burn_hours: int
    burn_minutes: int
    burn_total_minutes: int
    burn_time: str
    door_open: bool
    door_state: str
    fan_raw: int
    status_raw: int
    raw: str


@dataclass
class ArchiveRecord:
    archive_number: int
    timestamp: datetime | None
    stage_90_minute: int | None
    stage_75_minute: int | None
    stage_50_minute: int | None
    stage_25_minute: int | None
    stage_0_minute: int | None
    temperatures: list[int]
    active_or_incomplete: bool
    raw: str

    @property
    def max_temperature_c(self) -> int | None:
        if not self.temperatures:
            return None

        return max(self.temperatures)

    @property
    def max_temperature_minute(self) -> int | None:
        if not self.temperatures:
            return None

        maximum = max(self.temperatures)
        return self.temperatures.index(maximum)

    @property
    def start_temperature_c(self) -> int | None:
        if not self.temperatures:
            return None

        return self.temperatures[0]

    @property
    def end_temperature_c(self) -> int | None:
        if not self.temperatures:
            return None

        return self.temperatures[-1]

    @property
    def measurement_count(self) -> int:
        return len(self.temperatures)


def _decode_hex(raw: str) -> bytes:
    try:
        return bytes.fromhex(raw)
    except ValueError as error:
        raise ValueError("Ungültiger Hex-Datensatz.") from error


def _validate_header(data: bytes) -> None:
    if data[:4] != PACKET_HEADER:
        raise ValueError("Unbekannter Paketkopf.")


def decode_live_status(raw: str) -> LiveStatus:
    data = _decode_hex(raw)

    if len(data) < LIVE_MIN_LENGTH:
        raise ValueError(
            f"Live-Datensatz zu kurz: {len(data)} Bytes."
        )

    _validate_header(data)

    door_open = bool(data[6] & 0x10)

    temperature_c = int.from_bytes(
        data[7:9],
        byteorder="big",
        signed=False,
    )

    flap_raw = data[9]

    if flap_raw > 100:
        flap_percent = max(0, min(100, flap_raw - 150))
        flap_moving = True
    else:
        flap_percent = flap_raw
        flap_moving = False

    burn_hours = data[10]
    burn_minutes = data[11]
    burn_total_minutes = burn_hours * 60 + burn_minutes

    return LiveStatus(
        temperature_c=temperature_c,
        flap_percent=flap_percent,
        flap_moving=flap_moving,
        burn_hours=burn_hours,
        burn_minutes=burn_minutes,
        burn_total_minutes=burn_total_minutes,
        burn_time=f"{burn_hours}:{burn_minutes:02d}",
        door_open=door_open,
        door_state="offen" if door_open else "geschlossen",
        fan_raw=data[18],
        status_raw=data[6],
        raw=raw,
    )


def _decode_archive_timestamp(data: bytes) -> datetime | None:
    try:
        year = 2000 + data[8]
        month = data[9] & 0x0F
        day = data[10]
        hour = data[11]
        minute = data[12]

        return datetime(year, month, day, hour, minute)
    except (ValueError, IndexError):
        return None


def _decode_optional_minute(value: int) -> int | None:
    if value == 0:
        return None

    return value


def _decode_archive_temperatures(
    data: bytes,
) -> tuple[list[int], bool]:
    temperatures: list[int] = []
    active_or_incomplete = False

    for position in range(
        ARCHIVE_DATA_START,
        ARCHIVE_DATA_END,
        2,
    ):
        value = data[position] | (data[position + 1] << 8)

        if value == 0xFFFF:
            break

        temperatures.append(value)

    while temperatures and temperatures[-1] == 0:
        temperatures.pop()
        active_or_incomplete = True

    if len(temperatures) < 121:
        active_or_incomplete = True

    return temperatures, active_or_incomplete


def decode_archive_record(raw: str) -> ArchiveRecord:
    data = _decode_hex(raw)

    if len(data) != ARCHIVE_LENGTH:
        raise ValueError(
            f"Archivdatensatz hat {len(data)} statt "
            f"{ARCHIVE_LENGTH} Bytes."
        )

    _validate_header(data)

    temperatures, incomplete = _decode_archive_temperatures(data)

    return ArchiveRecord(
        archive_number=data[7],
        timestamp=_decode_archive_timestamp(data),
        stage_90_minute=_decode_optional_minute(data[13]),
        stage_75_minute=_decode_optional_minute(data[15]),
        stage_50_minute=_decode_optional_minute(data[17]),
        stage_25_minute=_decode_optional_minute(data[19]),
        stage_0_minute=_decode_optional_minute(data[21]),
        temperatures=temperatures,
        active_or_incomplete=incomplete,
        raw=raw,
    )
