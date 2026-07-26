"""Tests fuer Services."""

from __future__ import annotations

from datetime import date

from jira_timesheet_qt.models.timesheet import WorklogEntry
from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.services.timesheet_service import TimesheetService


class TestTimesheetService:
    def test_build_groups_by_date(self) -> None:
        entries = [
            WorklogEntry(date=date(2026, 3, 3), ticket="B-1", summary="Y", author="Dev", budget="", hours=3.0),
            WorklogEntry(date=date(2026, 3, 2), ticket="A-1", summary="X", author="Dev", budget="", hours=5.0),
            WorklogEntry(date=date(2026, 3, 2), ticket="A-2", summary="Z", author="Dev", budget="", hours=2.0),
        ]
        ts = TimesheetService.build_timesheet(entries, "Dev", "dev@test.com", date(2026, 3, 1), date(2026, 3, 31))

        assert ts.working_days == 2
        assert ts.days[0].date == date(2026, 3, 2)
        assert ts.days[1].date == date(2026, 3, 3)
        assert ts.days[0].total_hours == 7.0
        assert ts.days[1].total_hours == 3.0

    def test_empty_entries(self) -> None:
        ts = TimesheetService.build_timesheet([], "Dev", "dev@test.com", date(2026, 3, 1), date(2026, 3, 31))
        assert ts.working_days == 0
        assert ts.total_hours == 0.0


class TestHolidayService:
    def test_saxony_holidays(self) -> None:
        svc = HolidayService("SN")
        assert svc.is_holiday(date(2026, 1, 1))
        assert not svc.is_holiday(date(2026, 1, 2))

    def test_workday(self) -> None:
        svc = HolidayService("SN")
        assert svc.is_workday(date(2026, 3, 2))  # Montag
        assert not svc.is_workday(date(2026, 3, 7))  # Samstag
        assert not svc.is_workday(date(2026, 1, 1))  # Feiertag

    def test_count_workdays_march(self) -> None:
        svc = HolidayService("SN")
        count = svc.count_workdays(date(2026, 3, 1), date(2026, 3, 31))
        assert count == 22

    def test_missing_workdays(self) -> None:
        svc = HolidayService("SN")
        worked = {date(2026, 3, 2), date(2026, 3, 4)}
        missing = svc.get_missing_workdays(date(2026, 3, 2), date(2026, 3, 6), worked)
        missing_dates = [d for d, _ in missing]
        assert date(2026, 3, 3) in missing_dates
        assert date(2026, 3, 5) in missing_dates
        assert date(2026, 3, 6) in missing_dates

    def test_holidays_in_range(self) -> None:
        svc = HolidayService("SN")
        h = svc.get_holidays_in_range(date(2026, 4, 1), date(2026, 4, 30))
        assert date(2026, 4, 3) in h  # Karfreitag
        assert date(2026, 4, 6) in h  # Ostermontag
