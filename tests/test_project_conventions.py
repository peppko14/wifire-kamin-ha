# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "venv",
}


def _decorator_name(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    return None


def dataclasses_without_slots(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        for decorator in node.decorator_list:
            if _decorator_name(decorator) != "dataclass":
                continue

            slots_enabled = False
            if isinstance(decorator, ast.Call):
                slots_enabled = any(
                    keyword.arg == "slots"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in decorator.keywords
                )

            if not slots_enabled:
                violations.append(f"{filename}:{node.lineno}: {node.name}")
            break

    return violations


def project_python_files() -> list[Path]:
    return sorted(
        path
        for path in PROJECT_ROOT.rglob("*.py")
        if not any(part in IGNORED_DIRECTORIES for part in path.parts)
    )


class DataclassConventionTests(unittest.TestCase):
    def test_all_project_dataclasses_use_slots(self) -> None:
        violations: list[str] = []

        for path in project_python_files():
            relative_path = path.relative_to(PROJECT_ROOT).as_posix()
            violations.extend(
                dataclasses_without_slots(
                    path.read_text(encoding="utf-8"),
                    relative_path,
                )
            )

        self.assertEqual(
            violations,
            [],
            "Dataclasses ohne slots=True:\n" + "\n".join(violations),
        )

    def test_validator_detects_missing_slots(self) -> None:
        source = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Item:\n"
            "    value: int\n"
        )

        self.assertEqual(
            dataclasses_without_slots(source, "example.py"),
            ["example.py:3: Item"],
        )

    def test_validator_rejects_slots_false(self) -> None:
        source = (
            "from dataclasses import dataclass\n"
            "@dataclass(slots=False)\n"
            "class Item:\n"
            "    value: int\n"
        )

        self.assertEqual(
            dataclasses_without_slots(source, "example.py"),
            ["example.py:3: Item"],
        )

    def test_validator_accepts_slots_true(self) -> None:
        source = (
            "from dataclasses import dataclass\n"
            "@dataclass(slots=True)\n"
            "class Item:\n"
            "    value: int\n"
        )

        self.assertEqual(
            dataclasses_without_slots(source, "example.py"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
