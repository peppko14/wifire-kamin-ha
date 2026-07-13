#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Prüft die lokale WiFire-Historie vollständig und nur lesend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


__version__ = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.audit import HistoryAudit, audit_history  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prüft Historie und Diagnoseablage nur lesend."
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history",
    )
    parser.add_argument(
        "--diagnostic-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history-incomplete",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _mapping_text(values: tuple[tuple[str, int], ...]) -> str:
    if not values:
        return "keine"
    return ", ".join(f"{key}: {count}" for key, count in values)


def print_text(audit: HistoryAudit) -> None:
    """Gibt den Audit-Bericht lesbar aus."""
    print("WiFire-Kamin Historien-Audit")
    print("----------------------------")
    storage_status = "OK" if audit.storage_is_healthy else "FEHLER"
    print(f"Speicherzustand:           {storage_status}")
    print(f"Historien-Dateien:         {audit.regular_file_count}")
    print(f"Davon lesbar:              {audit.regular_readable_count}")
    print(f"Davon nicht lesbar:        {audit.regular_unreadable_count}")
    print(f"Qualität gültig:           {audit.valid_count}")
    print(f"Qualität mit Warnung:      {audit.warning_count}")
    print(f"Schema-Versionen:          {_mapping_text(audit.schema_versions)}")
    print(f"Warnungsgründe:            {_mapping_text(audit.warning_codes)}")
    print(f"Diagnose-Dateien:          {audit.diagnostic_file_count}")
    print(f"Diagnosen nicht lesbar:    {audit.diagnostic_unreadable_count}")
    print(f"Diagnosegründe:            {_mapping_text(audit.diagnostic_codes)}")


def main() -> int:
    args = parse_args()
    audit = audit_history(args.history_dir, args.diagnostic_dir)
    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_text(audit)
    return 0 if audit.storage_is_healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
