# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Portabler JSON-Export historischer Brennkurven und Referenzen."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

from history.curve_analysis import CurveAnalysis
from history.curves import SAMPLE_AXIS


CURVE_EXPORT_SCHEMA_VERSION = 1


class CurveExportError(RuntimeError):
    """Brennkurven konnten nicht sicher exportiert werden."""


def build_curve_export(
    analysis: CurveAnalysis,
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Erzeugt die vollständige, portable JSON-Struktur."""
    timestamp = generated_at or datetime.now(UTC)
    representative = analysis.representative_curve.to_dict()
    representative["rmse_to_average_c"] = analysis.representative_rmse_c

    return {
        "schema_version": CURVE_EXPORT_SCHEMA_VERSION,
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "sample_axis": SAMPLE_AXIS,
        "source_curve_count": analysis.source_curve_count,
        "sample_count": analysis.sample_count,
        "filters": {
            "since": (
                analysis.since.isoformat(timespec="seconds")
                if analysis.since is not None
                else None
            ),
            "include_warnings": analysis.include_warnings,
        },
        "average_curve": {
            "sample_axis": SAMPLE_AXIS,
            "sample_count": analysis.sample_count,
            "points": [
                point.to_dict() for point in analysis.average_points
            ],
        },
        "representative_curve": representative,
        "hottest_curve": analysis.hottest_curve.to_dict(),
        "curves": [curve.to_dict() for curve in analysis.curves],
    }


def write_curve_export(
    analysis: CurveAnalysis,
    target: Path,
    *,
    overwrite: bool = False,
    generated_at: datetime | None = None,
) -> Path:
    """Schreibt den JSON-Export atomisch und überschreibt nicht implizit."""
    target = target.resolve()
    if target.exists() and not overwrite:
        raise CurveExportError(f"Exportdatei existiert bereits: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    try:
        payload = build_curve_export(analysis, generated_at=generated_at)
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        return target
    except Exception as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, CurveExportError):
            raise
        raise CurveExportError(
            f"Brennkurvenexport konnte nicht geschrieben werden: {error}"
        ) from error
