# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Strukturelle Tests für die lokale und entfernte Qualitätssicherung."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CiConfigurationTests(unittest.TestCase):
    def test_pyproject_targets_minimum_python_version(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
            config = tomllib.load(handle)

        self.assertEqual(config["tool"]["ruff"]["target-version"], "py311")
        self.assertEqual(config["tool"]["mypy"]["python_version"], "3.11")

    def test_development_tools_are_pinned(self) -> None:
        requirements = (
            PROJECT_ROOT / "requirements-dev.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("mypy==2.2.0", requirements.splitlines())
        self.assertIn("ruff==0.15.14", requirements.splitlines())

    def test_runtime_dependencies_are_hash_locked(self) -> None:
        source = (PROJECT_ROOT / "requirements.in").read_text(
            encoding="utf-8"
        )
        lock = (PROJECT_ROOT / "requirements.lock").read_text(
            encoding="utf-8"
        )

        self.assertIn("paho-mqtt>=2.1,<3", source.splitlines())
        self.assertIn("--only-binary :all:", lock.splitlines())
        self.assertIn("paho-mqtt==2.1.0 \\", lock.splitlines())
        self.assertIn(
            "--hash=sha256:"
            "6db9ba9b34ed5bc6b6e3812718c7e06e2fd7444540df2455d2c51bd58808feee",
            lock,
        )
        self.assertFalse((PROJECT_ROOT / "requirements.txt").exists())

    def test_workflow_runs_tests_lint_and_type_check(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('python-version: ["3.11", "3.13"]', workflow)
        self.assertIn("python -m unittest discover", workflow)
        self.assertIn("python -m ruff check .", workflow)
        self.assertIn("python -m mypy", workflow)

    def test_workflow_uses_read_only_repository_permission(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)

    def test_workflow_enforces_runtime_hash_verification(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(workflow.count("--require-hashes"), 2)
        self.assertEqual(workflow.count("--only-binary=:all:"), 2)
        self.assertEqual(workflow.count("-r requirements.lock"), 2)
        self.assertNotIn("requirements.txt", workflow)


if __name__ == "__main__":
    unittest.main()
