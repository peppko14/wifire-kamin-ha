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


if __name__ == "__main__":
    unittest.main()
