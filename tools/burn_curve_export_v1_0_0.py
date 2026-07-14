#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Exportiert historische WiFire-Brennkurven und Referenzen als JSON."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


__version__ = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.curve_analysis import (  # noqa: E402
    CurveAnalysisError,
    analyze_curves,
)
from history.curve_export import (  # noqa: E402
    CurveExportError,
    write_curve_export,
)
from history.curves import BurnCurveError, load_burn_curves  # noqa: E402


def parse_since(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--since benötigt YYYY-MM-DD oder einen ISO-Zeitstempel."
        ) from error


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exportiert Durchschnitt und historische Brennkurven."
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "data" / "exports" / "burn-curves.json",
    )
    parser.add_argument("--since", type=parse_since)
    parser.add_argument("--exclude-warnings", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    include_warnings = not args.exclude_warnings
    try:
        curves = load_burn_curves(
            args.history_dir,
            since=args.since,
            include_warnings=include_warnings,
        )
        analysis = analyze_curves(
            curves,
            since=args.since,
            include_warnings=include_warnings,
        )
        target = write_curve_export(
            analysis,
            args.output,
            overwrite=args.overwrite,
        )
    except (BurnCurveError, CurveAnalysisError, CurveExportError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1

    print("WiFire-Kamin Brennkurvenexport")
    print("--------------------------------")
    print(f"Exportierte Kurven:       {analysis.source_curve_count}")
    print(f"Messpunkte je Kurve:      {analysis.sample_count}")
    print(
        "Referenzabbrand:         "
        f"{analysis.representative_curve.start.isoformat(timespec='minutes')}"
    )
    print(
        "Referenzabweichung:      "
        f"{analysis.representative_rmse_c:.3f} °C RMSE"
    )
    print(
        "Heißester Abbrand:       "
        f"{analysis.hottest_curve.start.isoformat(timespec='minutes')} "
        f"mit {analysis.hottest_curve.max_temperature_c} °C"
    )
    print(f"Zieldatei:                {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
