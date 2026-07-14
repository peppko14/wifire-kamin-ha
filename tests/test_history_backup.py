# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from history.backup import (
    MANIFEST_NAME,
    HistoryBackupError,
    create_backup,
    restore_backup,
    verify_backup,
)


class HistoryBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.history = self.root / "history"
        self.diagnostics = self.root / "history-incomplete"
        self.history.mkdir()
        self.diagnostics.mkdir()
        self.history_file = self.history / "burn.json"
        self.diagnostic_file = self.diagnostics / "diagnostic.json"
        self.history_file.write_text('{"burn_id":"abc"}\n', encoding="utf-8")
        self.diagnostic_file.write_text(
            '{"diagnostic_id":"def"}\n',
            encoding="utf-8",
        )
        self.backup = self.root / "backups" / "history.zip"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self) -> None:
        create_backup(self.history, self.diagnostics, self.backup)

    def rewrite_backup(
        self,
        transform: Callable[
            [list[tuple[str, bytes]]],
            list[tuple[str, bytes]],
        ],
    ) -> None:
        with ZipFile(self.backup, "r") as source:
            entries = [(name, source.read(name)) for name in source.namelist()]
        with ZipFile(self.backup, "w", compression=ZIP_DEFLATED) as target:
            for name, data in transform(entries):
                target.writestr(name, data)

    def test_create_and_verify_backup(self) -> None:
        manifest = create_backup(self.history, self.diagnostics, self.backup)

        self.assertTrue(self.backup.is_file())
        self.assertEqual(manifest.history_count, 1)
        self.assertEqual(manifest.diagnostic_count, 1)
        self.assertEqual(verify_backup(self.backup), manifest)

    def test_create_refuses_existing_backup(self) -> None:
        self.create()

        with self.assertRaises(HistoryBackupError):
            create_backup(self.history, self.diagnostics, self.backup)

    def test_create_can_replace_backup_explicitly(self) -> None:
        self.create()

        manifest = create_backup(
            self.history,
            self.diagnostics,
            self.backup,
            overwrite=True,
        )

        self.assertEqual(len(manifest.entries), 2)

    def test_verify_detects_changed_file(self) -> None:
        self.create()

        def change(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
            return [
                (name, b"changed" if name == "history/burn.json" else data)
                for name, data in entries
            ]

        self.rewrite_backup(change)

        with self.assertRaisesRegex(HistoryBackupError, "Dateigröße"):
            verify_backup(self.backup)

    def test_verify_detects_unlisted_file(self) -> None:
        self.create()

        def add(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
            return [*entries, ("history/unlisted.json", b"{}")]

        self.rewrite_backup(add)

        with self.assertRaisesRegex(HistoryBackupError, "Manifest"):
            verify_backup(self.backup)

    def test_verify_rejects_unsafe_manifest_path(self) -> None:
        self.create()

        def make_unsafe(
            entries: list[tuple[str, bytes]],
        ) -> list[tuple[str, bytes]]:
            result: list[tuple[str, bytes]] = []
            for name, data in entries:
                if name == MANIFEST_NAME:
                    payload = json.loads(data)
                    payload["files"][0]["path"] = "../outside.json"
                    data = json.dumps(payload).encode("utf-8")
                result.append((name, data))
            return result

        self.rewrite_backup(make_unsafe)

        with self.assertRaisesRegex(HistoryBackupError, "Unsicherer"):
            verify_backup(self.backup)

    def test_verify_rejects_windows_style_traversal(self) -> None:
        self.create()

        def make_unsafe(
            entries: list[tuple[str, bytes]],
        ) -> list[tuple[str, bytes]]:
            result: list[tuple[str, bytes]] = []
            for name, data in entries:
                if name == MANIFEST_NAME:
                    payload = json.loads(data)
                    payload["files"][0]["path"] = (
                        "history/..\\outside.json"
                    )
                    data = json.dumps(payload).encode("utf-8")
                result.append((name, data))
            return result

        self.rewrite_backup(make_unsafe)

        with self.assertRaisesRegex(HistoryBackupError, "Unsicherer"):
            verify_backup(self.backup)

    def test_restore_preserves_file_contents(self) -> None:
        self.create()
        destination = self.root / "restored-data"

        manifest = restore_backup(self.backup, destination)

        self.assertEqual(len(manifest.entries), 2)
        self.assertEqual(
            (destination / "history" / "burn.json").read_bytes(),
            self.history_file.read_bytes(),
        )
        self.assertEqual(
            (
                destination / "history-incomplete" / "diagnostic.json"
            ).read_bytes(),
            self.diagnostic_file.read_bytes(),
        )

    def test_restore_refuses_existing_destination(self) -> None:
        self.create()
        destination = self.root / "restored-data"
        destination.mkdir()

        with self.assertRaisesRegex(HistoryBackupError, "existiert bereits"):
            restore_backup(self.backup, destination)


if __name__ == "__main__":
    unittest.main()
