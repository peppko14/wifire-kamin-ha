#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


PACKET_HEADER = bytes.fromhex("aacc3355")

ARCHIVE_LENGTH = 506
ARCHIVE_DATA_START = 22
ARCHIVE_DATA_END = 504


@dataclass(slots=True)
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
