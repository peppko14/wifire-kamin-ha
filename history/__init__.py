# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Historienverwaltung für WiFire-Abbrände."""

from .audit import HistoryAudit, audit_history
from .diagnostics import (
    DIAGNOSTIC_SCHEMA_VERSION,
    HistoryDiagnosticError,
    HistoryDiagnosticStorage,
)
from .identifiers import build_burn_id, build_canonical_burn_text

__all__ = [
    "DIAGNOSTIC_SCHEMA_VERSION",
    "HistoryAudit",
    "HistoryDiagnosticError",
    "HistoryDiagnosticStorage",
    "audit_history",
    "build_burn_id",
    "build_canonical_burn_text",
]
