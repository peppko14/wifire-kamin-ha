# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für Kalender- und Heizsaisonzeiträume."""

from __future__ import annotations

from datetime import datetime
import unittest

from history.periods import CalendarMonth, HeatingSeason


class CalendarMonthTests(unittest.TestCase):
    def test_month_is_derived_from_datetime(self) -> None:
        month = CalendarMonth.from_datetime(datetime(2026, 7, 13, 22, 0))

        self.assertEqual(month.key, "2026-07")
        self.assertEqual(month.start, datetime(2026, 7, 1))
        self.assertEqual(month.end_exclusive, datetime(2026, 8, 1))

    def test_december_ends_in_next_year(self) -> None:
        self.assertEqual(
            CalendarMonth(2026, 12).end_exclusive,
            datetime(2027, 1, 1),
        )

    def test_invalid_month_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CalendarMonth(2026, 13)


class HeatingSeasonTests(unittest.TestCase):
    def test_june_belongs_to_season_started_in_previous_year(self) -> None:
        season = HeatingSeason.from_datetime(datetime(2026, 6, 30, 23, 59))

        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.key, "2025-2026")
        self.assertEqual(season.label, "2025/2026")

    def test_july_starts_new_heating_season(self) -> None:
        season = HeatingSeason.from_datetime(datetime(2026, 7, 1))

        self.assertEqual(season.start_year, 2026)
        self.assertEqual(season.start, datetime(2026, 7, 1))
        self.assertEqual(season.end_exclusive, datetime(2027, 7, 1))

    def test_boundaries_are_inclusive_and_exclusive(self) -> None:
        season = HeatingSeason(2025)

        self.assertTrue(season.contains(datetime(2025, 7, 1)))
        self.assertTrue(season.contains(datetime(2026, 6, 30, 23, 59, 59)))
        self.assertFalse(season.contains(datetime(2026, 7, 1)))

    def test_seasons_sort_chronologically(self) -> None:
        seasons = [HeatingSeason(2026), HeatingSeason(2024), HeatingSeason(2025)]

        self.assertEqual(
            sorted(seasons),
            [HeatingSeason(2024), HeatingSeason(2025), HeatingSeason(2026)],
        )
