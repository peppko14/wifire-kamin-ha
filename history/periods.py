# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Stabile Kalender- und Heizsaisonzeiträume für Historienauswertungen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime




@dataclass(frozen=True, order=True, slots=True)
class CalendarMonth:
    """Ein abgeschlossener Kalendermonat, dargestellt durch Jahr und Monat."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < 1:
            raise ValueError("Das Jahr muss größer als null sein.")
        if not 1 <= self.month <= 12:
            raise ValueError("Der Monat muss zwischen 1 und 12 liegen.")

    @classmethod
    def from_datetime(cls, value: datetime) -> CalendarMonth:
        """Erzeugt den Kalendermonat eines Zeitpunkts."""
        return cls(value.year, value.month)

    @property
    def key(self) -> str:
        """Maschinenlesbarer und chronologisch sortierbarer Schlüssel."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def start(self) -> datetime:
        """Inklusiver Monatsanfang."""
        return datetime(self.year, self.month, 1)

    @property
    def end_exclusive(self) -> datetime:
        """Exklusive Grenze am Anfang des Folgemonats."""
        if self.month == 12:
            return datetime(self.year + 1, 1, 1)
        return datetime(self.year, self.month + 1, 1)

    def contains(self, value: datetime) -> bool:
        """Prüft, ob ein Zeitpunkt in diesem Kalendermonat liegt."""
        return value.year == self.year and value.month == self.month


@dataclass(frozen=True, order=True, slots=True)
class HeatingSeason:
    """Heizsaison vom 1. Juli bis zum 30. Juni des Folgejahres."""

    start_year: int

    def __post_init__(self) -> None:
        if self.start_year < 1:
            raise ValueError("Das Startjahr muss größer als null sein.")

    @classmethod
    def from_datetime(cls, value: datetime) -> HeatingSeason:
        """Ordnet einen Zeitpunkt seiner Heizsaison zu."""
        start_year = value.year if value.month >= 7 else value.year - 1
        return cls(start_year)

    @property
    def key(self) -> str:
        """Maschinenlesbarer und chronologisch sortierbarer Schlüssel."""
        return f"{self.start_year:04d}-{self.start_year + 1:04d}"

    @property
    def label(self) -> str:
        """Lesbare Bezeichnung der Saison."""
        return f"{self.start_year:04d}/{self.start_year + 1:04d}"

    @property
    def start(self) -> datetime:
        """Inklusiver Saisonanfang am 1. Juli."""
        return datetime(self.start_year, 7, 1)

    @property
    def end_exclusive(self) -> datetime:
        """Exklusive Grenze am 1. Juli des Folgejahres."""
        return datetime(self.start_year + 1, 7, 1)

    def contains(self, value: datetime) -> bool:
        """Prüft, ob ein Zeitpunkt in dieser Heizsaison liegt."""
        return self.start <= value < self.end_exclusive
