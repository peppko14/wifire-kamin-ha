#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Zeitsteuerung der WiFire-Kamin-Bridge."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable




RunningCheck = Callable[[], bool]
SleepFunction = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class InterruptibleSleeper:
    """Wartet in kurzen Abschnitten und reagiert auf Stoppsignale."""

    is_running: RunningCheck
    sleep: SleepFunction = time.sleep

    def __call__(self, seconds: int | float) -> None:
        """Wartet höchstens die angegebene Zeit."""
        steps = max(1, int(seconds * 10))

        for _ in range(steps):
            if not self.is_running():
                break
            self.sleep(0.1)


@dataclass(slots=True)
class IntervalSchedule:
    """Verwaltet einen wiederkehrenden Zeitplan."""

    interval_seconds: int | float
    last_update: float = 0.0

    def is_due(self, now: float) -> bool:
        """Gibt an, ob die nächste Ausführung fällig ist."""
        return now - self.last_update >= self.interval_seconds

    def mark_updated(self, now: float) -> None:
        """Speichert den Zeitpunkt der letzten Ausführung."""
        self.last_update = now
