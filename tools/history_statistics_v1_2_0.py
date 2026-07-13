#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zeigt Gesamt-, Monats- und Saisonstatistiken der Abbrandhistorie an."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Sequence


__version__ = "1.2.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.period_statistics import (  # noqa: E402
    HeatingSeasonStatistics,
    MonthlyStatistics,
    calculate_heating_season_statistics,
    calculate_monthly_statistics,
)
from history.statistics import (  # noqa: E402
    HistoryStatistics,
    HistoryStatisticsError,
    calculate_history_statistics,
)
from history.storage import HistoryStorage, HistoryStorageError  # noqa: E402


def parse_since(value: str) -> datetime:
    """Liest ein ISO-Datum oder einen ISO-Zeitstempel inklusiv ein."""
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--since erwartet YYYY-MM-DD oder einen ISO-Zeitstempel."
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wertet die lokale WiFire-Abbrandhistorie aus."
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history",
        help="Pfad zum Historienordner (Standard: data/history)",
    )
    parser.add_argument(
        "--since",
        type=parse_since,
        help="Nur Abbrände ab diesem Datum berücksichtigen (inklusiv)",
    )
    grouping = parser.add_mutually_exclusive_group()
    grouping.add_argument(
        "--monthly",
        action="store_true",
        help="Statistik nach Kalendermonaten gruppieren",
    )
    grouping.add_argument(
        "--seasons",
        action="store_true",
        help="Statistik nach Heizsaisons von Juli bis Juni gruppieren",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Ausgabe als JSON statt als lesbarer Bericht",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def load_records(history_dir: Path) -> list[dict[str, object]]:
    """Lädt alle lokalen Historiendatensätze."""
    return HistoryStorage(history_dir).list_records()


def load_statistics(
    history_dir: Path,
    *,
    since: datetime | None = None,
) -> HistoryStatistics:
    """Lädt die lokale Historie und berechnet ihre Gesamtstatistik."""
    return calculate_history_statistics(load_records(history_dir), since=since)


def load_monthly_statistics(
    history_dir: Path,
    *,
    since: datetime | None = None,
) -> tuple[MonthlyStatistics, ...]:
    """Lädt die lokale Historie und berechnet Monatsstatistiken."""
    return calculate_monthly_statistics(load_records(history_dir), since=since)


def load_season_statistics(
    history_dir: Path,
    *,
    since: datetime | None = None,
) -> tuple[HeatingSeasonStatistics, ...]:
    """Lädt die lokale Historie und berechnet Heizsaisonstatistiken."""
    return calculate_heating_season_statistics(
        load_records(history_dir),
        since=since,
    )


def _number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "–"
    return f"{value}{suffix}"


def format_report(statistics: HistoryStatistics) -> str:
    """Formatiert die Gesamtstatistik als kompakten deutschen Bericht."""
    first = (
        statistics.first_burn_start.isoformat(timespec="minutes")
        if statistics.first_burn_start is not None
        else "–"
    )
    latest = (
        statistics.latest_burn_start.isoformat(timespec="minutes")
        if statistics.latest_burn_start is not None
        else "–"
    )
    highest_start = (
        statistics.highest_temperature_start.isoformat(timespec="minutes")
        if statistics.highest_temperature_start is not None
        else "–"
    )

    lines = [
        "WiFire-Kamin Abbrandstatistik",
        "-----------------------------",
        f"Gespeicherte Datensätze:      {statistics.source_record_count}",
        f"Berücksichtigte Abbrände:     {statistics.burn_count}",
        f"Ausgefilterte Datensätze:     {statistics.excluded_record_count}",
        f"Abbrände mit Dauer:           {statistics.duration_record_count}",
        f"Erster Abbrand:               {first}",
        f"Neuester Abbrand:             {latest}",
        (
            "Gesamte Abbrenndauer:        "
            f"{statistics.total_duration_minutes} min"
        ),
        (
            "Mittlere Abbrenndauer:       "
            f"{_number(statistics.average_duration_minutes, ' min')}"
        ),
        (
            "Mittlere Maximaltemperatur:  "
            f"{_number(statistics.average_max_temperature_c, ' °C')}"
        ),
        (
            "Höchste Temperatur:          "
            f"{_number(statistics.highest_temperature_c, ' °C')}"
        ),
        f"Zeitpunkt des Maximums:       {highest_start}",
        (
            "Mittlere Starttemperatur:    "
            f"{_number(statistics.average_start_temperature_c, ' °C')}"
        ),
        (
            "Mittlere Endtemperatur:      "
            f"{_number(statistics.average_end_temperature_c, ' °C')}"
        ),
    ]
    return "\n".join(lines)


def _period_line(label: str, statistics: HistoryStatistics) -> str:
    duration = _number(statistics.average_duration_minutes)
    average_maximum = _number(statistics.average_max_temperature_c)
    maximum = _number(statistics.highest_temperature_c)
    return (
        f"{label:<10} | {statistics.burn_count:>8} | "
        f"{statistics.total_duration_minutes:>9} | {duration:>8} | "
        f"{average_maximum:>7} | {maximum:>7}"
    )


def _format_period_report(
    title: str,
    rows: Sequence[tuple[str, HistoryStatistics]],
) -> str:
    lines = [
        title,
        "-" * len(title),
        "Zeitraum   | Abbrände | Dauer min | Ø Dauer | Ø Max °C | Max °C",
        "-----------+----------+-----------+----------+---------+--------",
    ]
    lines.extend(_period_line(label, statistics) for label, statistics in rows)
    if not rows:
        lines.append("Keine Abbrände im gewählten Zeitraum.")
    return "\n".join(lines)


def format_monthly_report(statistics: Sequence[MonthlyStatistics]) -> str:
    """Formatiert chronologische Monatsstatistiken als Tabelle."""
    return _format_period_report(
        "WiFire-Kamin Monatsstatistik",
        [(item.month.key, item.statistics) for item in statistics],
    )


def format_season_report(
    statistics: Sequence[HeatingSeasonStatistics],
) -> str:
    """Formatiert chronologische Heizsaisonstatistiken als Tabelle."""
    return _format_period_report(
        "WiFire-Kamin Heizsaisonstatistik",
        [(item.season.label, item.statistics) for item in statistics],
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.monthly:
            periods = load_monthly_statistics(
                args.history_dir,
                since=args.since,
            )
            payload: object = {
                "group_by": "month",
                "periods": [item.to_dict() for item in periods],
            }
            report = format_monthly_report(periods)
        elif args.seasons:
            periods = load_season_statistics(
                args.history_dir,
                since=args.since,
            )
            payload = {
                "group_by": "heating_season",
                "periods": [item.to_dict() for item in periods],
            }
            report = format_season_report(periods)
        else:
            statistics = load_statistics(
                args.history_dir,
                since=args.since,
            )
            payload = statistics.to_dict()
            report = format_report(statistics)
    except (HistoryStorageError, HistoryStatisticsError) as error:
        print(f"Statistikfehler: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
