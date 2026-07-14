# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Erzeugt und veröffentlicht kompakte historische Brennkurven."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from bridge.dashboard import (
    DashboardCurveSnapshot,
    build_dashboard_snapshot,
)
from history.curve_analysis import analyze_curves
from history.curves import BurnCurve, load_burn_curves



Logger = Callable[[str], None]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CurveLoader(Protocol):
    def __call__(
        self,
        directory: Path,
        *,
        since: datetime | None,
        include_warnings: bool,
    ) -> tuple[BurnCurve, ...]:
        ...


class DashboardPublisherLike(Protocol):
    def publish_dashboard_snapshot(
        self,
        snapshot: DashboardCurveSnapshot,
    ) -> None:
        ...


def parse_dashboard_since(value: object) -> datetime | None:
    """Liest den optionalen inklusiven Kurvenfilter."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(
            "DASHBOARD_CURVES_SINCE muss None oder ein ISO-Datum sein."
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "DASHBOARD_CURVES_SINCE erwartet YYYY-MM-DD oder einen "
            "ISO-Zeitstempel."
        ) from error


@dataclass(frozen=True, slots=True)
class DashboardCurveReporter:
    """Liest die Historie und veröffentlicht genau drei Referenzkurven."""

    history_directory: Path
    publisher: DashboardPublisherLike
    since: datetime | None = None
    include_warnings: bool = True
    logger: Logger = print
    now: Clock = _utc_now
    curve_loader: CurveLoader = load_burn_curves

    def __post_init__(self) -> None:
        if not isinstance(self.history_directory, Path):
            raise ValueError("history_directory muss ein pathlib.Path sein.")
        if self.since is not None and not isinstance(self.since, datetime):
            raise ValueError("since muss ein Zeitstempel oder null sein.")
        if not isinstance(self.include_warnings, bool):
            raise ValueError("include_warnings muss boolesch sein.")

    def refresh(self) -> DashboardCurveSnapshot | None:
        """Veröffentlicht eine neue retained Momentaufnahme der Historie."""
        curves = self.curve_loader(
            self.history_directory,
            since=self.since,
            include_warnings=self.include_warnings,
        )
        if not curves:
            self.logger(
                "Brennkurven-Vergleich nicht veröffentlicht: "
                "keine passenden Abbrände."
            )
            return None

        analysis = analyze_curves(
            curves,
            since=self.since,
            include_warnings=self.include_warnings,
        )
        snapshot = build_dashboard_snapshot(
            analysis,
            generated_at=self.now(),
        )
        self.publisher.publish_dashboard_snapshot(snapshot)
        self.logger(
            "Brennkurven-Vergleich veröffentlicht: "
            f"{snapshot.source_curve_count} Abbrände, "
            f"{snapshot.sample_count} Messpunkte, "
            f"{snapshot.payload_size_bytes} Bytes."
        )
        return snapshot
