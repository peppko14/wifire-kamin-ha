# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Adapter zwischen bestehendem Archivdecoder und neuem BurnRecord-Modell."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from protocol.models import BurnRecord




class ArchiveRecordLike(Protocol):
    """Benötigte Schnittstelle des bestehenden Archivdatensatzes."""

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


def archive_record_to_burn_record(
    record: ArchiveRecordLike,
) -> BurnRecord:
    """Wandelt einen bestehenden Archivdatensatz in BurnRecord um."""
    return BurnRecord(
        start=record.timestamp,
        temperatures_c=tuple(record.temperatures),
        source_archive_number=record.archive_number,
        stage_90_minute=record.stage_90_minute,
        stage_75_minute=record.stage_75_minute,
        stage_50_minute=record.stage_50_minute,
        stage_25_minute=record.stage_25_minute,
        stage_0_minute=record.stage_0_minute,
        active_or_incomplete=record.active_or_incomplete,
        raw=record.raw,
    )
