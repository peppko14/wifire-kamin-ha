# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zentrale, levelbasierte Protokollierung der Bridge-Anwendung."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import sys
from typing import Callable, TextIO


Logger = Callable[[str], None]

_LOGGER_NAME = "wifire_kamin"
_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class _BelowWarningFilter(logging.Filter):
    """Lässt ausschließlich DEBUG- und INFO-Einträge passieren."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


@dataclass(frozen=True, slots=True)
class ApplicationLogger:
    """Aufrufbarer Logger für bestehende Dependency-Injection-Schnittstellen."""

    backend: logging.Logger

    def __call__(self, message: str) -> None:
        self.info(message)

    def debug(self, message: str) -> None:
        self.backend.debug(message)

    def info(self, message: str) -> None:
        self.backend.info(message)

    def warning(self, message: str) -> None:
        self.backend.warning(message)

    def error(self, message: str) -> None:
        self.backend.error(message)

    def critical(self, message: str) -> None:
        self.backend.critical(message)


def _log_with_level(
    logger: Logger,
    method_name: str,
    message: str,
) -> None:
    method = getattr(logger, method_name, None)
    if callable(method):
        method(message)
        return
    logger(message)


def log_warning(logger: Logger, message: str) -> None:
    """Schreibt eine Warnung und unterstützt einfache Test-Callables."""
    _log_with_level(logger, "warning", message)


def log_error(logger: Logger, message: str) -> None:
    """Schreibt einen Fehler und unterstützt einfache Test-Callables."""
    _log_with_level(logger, "error", message)


def configure_logging(
    level: object = "INFO",
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> ApplicationLogger:
    """Konfiguriert einen zentralen Logger mit getrennten Ausgabekanälen."""
    if not isinstance(level, str):
        raise ValueError("LOG_LEVEL muss eine Zeichenkette sein.")

    normalized = level.strip().upper()
    if normalized not in _LOG_LEVELS:
        allowed = ", ".join(_LOG_LEVELS)
        raise ValueError(f"LOG_LEVEL muss einer von {allowed} sein.")

    numeric_level = _LOG_LEVELS[normalized]
    backend = logging.getLogger(_LOGGER_NAME)
    backend.setLevel(numeric_level)
    backend.propagate = False

    for handler in tuple(backend.handlers):
        backend.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    standard_handler = logging.StreamHandler(
        stdout if stdout is not None else sys.stdout
    )
    standard_handler.setLevel(numeric_level)
    standard_handler.addFilter(_BelowWarningFilter())
    standard_handler.setFormatter(formatter)

    warning_handler = logging.StreamHandler(
        stderr if stderr is not None else sys.stderr
    )
    warning_handler.setLevel(max(numeric_level, logging.WARNING))
    warning_handler.setFormatter(formatter)

    backend.addHandler(standard_handler)
    backend.addHandler(warning_handler)
    return ApplicationLogger(backend)
