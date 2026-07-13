#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zeigt Statistiken aus der lokalen WiFire-Abbrandhistorie an."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


__version__ = "1.0.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.statistics import (  # noqa: E402
    HistoryStatistics,
    HistoryStatisticsError,
    calculate_history_statistics,
)
from history.storage import HistoryStorage, HistoryStorageError  # noqa: E402


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


def load_statistics(history_dir: Path) -> HistoryStatistics:
    """Lädt die lokale Historie und berechnet ihre Statistik."""
    records = HistoryStorage(history_dir).list_records()
    return calculate_history_statistics(records)


def _number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "–"
    return f"{value}{suffix}"


def format_report(statistics: HistoryStatistics) -> str:
    """Formatiert die Statistik als kompakten deutschen Textbericht."""
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
        f"Gespeicherte Abbrände:       {statistics.burn_count}",
        f"Erster Abbrand:              {first}",
        f"Neuester Abbrand:            {latest}",
        (
            "Gesamtdauer:                 "
            f"{statistics.total_duration_minutes} min"
        ),
        (
            "Durchschnittliche Dauer:     "
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        statistics = load_statistics(args.history_dir)
    except (HistoryStorageError, HistoryStatisticsError) as error:
        print(f"Statistikfehler: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                statistics.to_dict(),
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(format_report(statistics))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
