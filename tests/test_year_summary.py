"""Tests fuer die Jahres-Kennzahlen (Ist/Soll/Prognose) und die Aggregation."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.year_view import MonthCell, YearView, compute_year_summary


def _cells(hours_by_month: dict[int, float], target: float = 160.0) -> list[MonthCell]:
    return [
        MonthCell(
            month=m,
            hours=hours_by_month.get(m, 0.0),
            target=target,
            entries=1 if m in hours_by_month else 0,
        )
        for m in range(1, 13)
    ]


class TestComputeYearSummary:
    def test_actual_and_target_are_sums(self) -> None:
        summary = compute_year_summary(_cells({1: 100.0, 2: 150.0}, target=160.0), 12)
        assert summary.actual == 250.0
        assert summary.target == 160.0 * 12

    def test_all_months_elapsed_forecast_equals_actual(self) -> None:
        summary = compute_year_summary(_cells({1: 100.0, 2: 150.0}), 12)
        assert summary.forecast == summary.actual == 250.0

    def test_all_months_future_forecast_equals_target(self) -> None:
        summary = compute_year_summary(_cells({}, target=160.0), 0)
        assert summary.forecast == 160.0 * 12

    def test_mixed_forecast_is_actual_plus_remaining_target(self) -> None:
        # Bis Monat 2 abgelaufen: Ist(1,2) + Soll(3..12).
        summary = compute_year_summary(_cells({1: 100.0, 2: 120.0}, target=160.0), 2)
        assert summary.forecast == 220.0 + 10 * 160.0


class TestYearViewSummary:
    def test_past_year_forecast_is_actual(self, qapp: QApplication) -> None:
        view = YearView()
        view.set_year(2020, {1: 100.0}, {1: 5}, hours_per_day=8.0, federal_state="SN")
        # 2020 liegt komplett in der Vergangenheit -> Prognose == Ist.
        assert view.summary.actual == 100.0
        assert view.summary.forecast == 100.0
        assert view.summary.target > 0.0  # Soll aus Arbeitstagen berechnet


class TestYearAggregation:
    def test_on_year_loaded_groups_by_month(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._year = 2026
        timesheet = Timesheet(
            developer="x", email="", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
            days=[
                TimesheetDay(date=date(2026, 1, 10), entries=[
                    WorklogEntry(date=date(2026, 1, 10), ticket="A", summary="s",
                                 author="", budget="", hours=3.0),
                ]),
                TimesheetDay(date=date(2026, 3, 5), entries=[
                    WorklogEntry(date=date(2026, 3, 5), ticket="B", summary="s",
                                 author="", budget="", hours=2.0),
                ]),
                TimesheetDay(date=date(2026, 3, 6), entries=[
                    WorklogEntry(date=date(2026, 3, 6), ticket="C", summary="s",
                                 author="", budget="", hours=4.0),
                ]),
            ],
        )
        window._on_year_loaded(timesheet)
        assert window._year_hours[1] == 3.0
        assert window._year_hours[3] == 6.0
        assert window._year_entries[3] == 2
        assert window._year_loaded_for == 2026
        # Die Jahresansicht kennt die Summen.
        assert window._year_view.summary.actual == 9.0
