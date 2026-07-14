#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Erstellt, prüft und restauriert WiFire-Historien-Backups."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


__version__ = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from history.backup import (  # noqa: E402
    BackupManifest,
    HistoryBackupError,
    create_backup,
    restore_backup,
    verify_backup,
)


def default_backup_path() -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return PROJECT_DIR / "data" / "backups" / f"wifire-history_{timestamp}.zip"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sichert und prüft die lokale WiFire-Historie."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Backup erstellen und prüfen")
    create.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history",
    )
    create.add_argument(
        "--diagnostic-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "history-incomplete",
    )
    create.add_argument("--output", type=Path)
    create.add_argument("--overwrite", action="store_true")

    verify = commands.add_parser("verify", help="Backup vollständig prüfen")
    verify.add_argument("backup", type=Path)

    restore = commands.add_parser(
        "restore",
        help="Backup in ein neues Zielverzeichnis restaurieren",
    )
    restore.add_argument("backup", type=Path)
    restore.add_argument("--target", type=Path, required=True)
    return parser


def print_manifest(manifest: BackupManifest) -> None:
    print(f"Historien-Dateien:  {manifest.history_count}")
    print(f"Diagnose-Dateien:   {manifest.diagnostic_count}")
    print(f"Dateien insgesamt:  {len(manifest.entries)}")
    print(f"Erstellt:           {manifest.created_at}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create":
            output = args.output or default_backup_path()
            manifest = create_backup(
                args.history_dir,
                args.diagnostic_dir,
                output,
                overwrite=args.overwrite,
            )
            print("Historien-Backup erfolgreich erstellt und verifiziert.")
            print(f"Backup:             {output.resolve()}")
        elif args.command == "verify":
            manifest = verify_backup(args.backup)
            print("Historien-Backup ist vollständig und unverändert.")
            print(f"Backup:             {args.backup.resolve()}")
        else:
            manifest = restore_backup(args.backup, args.target)
            print("Historien-Backup erfolgreich wiederhergestellt.")
            print(f"Ziel:               {args.target.resolve()}")
        print_manifest(manifest)
        return 0
    except HistoryBackupError as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
