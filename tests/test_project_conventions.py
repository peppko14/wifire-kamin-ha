# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ast
import re
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
IGNORED_DIRECTORY_PREFIXES = ("package-",)
TOOL_VERSION_PATTERN = re.compile(
    r"_v(?P<major>\d+)[._](?P<minor>\d+)[._](?P<patch>\d+)\.py$"
)


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


def module_version_assignments(
    source: str,
    filename: str,
) -> list[str]:
    """Findet lokale __version__-Zuweisungen auf Modulebene."""
    tree = ast.parse(source, filename=filename)
    assignments: list[str] = []

    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)

        if any(
            isinstance(target, ast.Name)
            and target.id == "__version__"
            for target in targets
        ):
            assignments.append(f"{filename}:{node.lineno}")

    return assignments


def declared_tool_version(source: str, filename: str) -> str | None:
    """Liest die konstante Werkzeugversion aus dem Quelltext."""
    tree = ast.parse(source, filename=filename)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "__version__"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(
            node.value.value,
            str,
        ):
            return node.value.value

    return None


def project_python_files() -> list[Path]:
    return sorted(
        path
        for path in PROJECT_ROOT.rglob("*.py")
        if not any(part in IGNORED_DIRECTORIES for part in path.parts)
        and not any(
            part.startswith(IGNORED_DIRECTORY_PREFIXES)
            for part in path.parts
        )
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


class VersionConventionTests(unittest.TestCase):
    def test_project_modules_have_no_local_version(self) -> None:
        violations: list[str] = []

        for path in project_python_files():
            relative = path.relative_to(PROJECT_ROOT)
            if relative.parts[0] == "tools":
                continue
            relative_name = relative.as_posix()
            violations.extend(
                module_version_assignments(
                    path.read_text(encoding="utf-8"),
                    relative_name,
                )
            )

        self.assertEqual(
            violations,
            [],
            "Lokale Modulversionen gefunden:\n" + "\n".join(violations),
        )

    def test_tool_versions_match_their_filenames(self) -> None:
        violations: list[str] = []

        for path in sorted((PROJECT_ROOT / "tools").glob("*.py")):
            match = TOOL_VERSION_PATTERN.search(path.name)
            if match is None:
                violations.append(f"{path.name}: keine Version im Dateinamen")
                continue

            filename_version = ".".join(match.groups())
            source_version = declared_tool_version(
                path.read_text(encoding="utf-8"),
                path.name,
            )
            if source_version != filename_version:
                violations.append(
                    f"{path.name}: {source_version!r} statt "
                    f"{filename_version!r}"
                )

        self.assertEqual(
            violations,
            [],
            "Werkzeugversionen sind nicht synchron:\n"
            + "\n".join(violations),
        )

    def test_version_assignment_detector(self) -> None:
        source = '__version__ = "1.2.3"\n'

        self.assertEqual(
            module_version_assignments(source, "example.py"),
            ["example.py:1"],
        )


class RepositoryTextConventionTests(unittest.TestCase):
    def test_git_enforces_lf_for_text_files(self) -> None:
        attributes = (PROJECT_ROOT / ".gitattributes").read_text(
            encoding="utf-8"
        )

        self.assertIn("* text=auto eol=lf", attributes.splitlines())


if __name__ == "__main__":
    unittest.main()
