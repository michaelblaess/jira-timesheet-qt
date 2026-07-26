"""Tests fuer Domain Models."""

from __future__ import annotations

from datetime import date

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry


class TestWorklogEntry:
    def test_create_entry(self) -> None:
        entry = WorklogEntry(
            date=date(2026, 3, 2),
            ticket="PROJ-1234",
            summary="Culture is not supported",
            author="Mustermann, Max",
            budget="nicht zugeordnet",
            hours=2.5,
        )
        assert entry.ticket == "PROJ-1234"
        assert entry.hours == 2.5


class TestTimesheetDay:
    def test_total_hours(self) -> None:
        day = TimesheetDay(
            date=date(2026, 3, 2),
            entries=[
                WorklogEntry(date=date(2026, 3, 2), ticket="A-1", summary="Task A", author="Dev", budget="", hours=3.0),
                WorklogEntry(date=date(2026, 3, 2), ticket="B-2", summary="Task B", author="Dev", budget="", hours=5.0),
            ],
        )
        assert day.total_hours == 8.0

    def test_empty_day(self) -> None:
        day = TimesheetDay(date=date(2026, 3, 2))
        assert day.total_hours == 0.0


class TestTimesheet:
    def test_properties(self) -> None:
        ts = Timesheet(
            developer="Dev",
            email="dev@example.com",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            days=[
                TimesheetDay(
                    date=date(2026, 3, 2),
                    entries=[
                        WorklogEntry(
                            date=date(2026, 3, 2), ticket="A-1", summary="X", author="Dev", budget="", hours=8.0
                        ),
                    ],
                ),
                TimesheetDay(
                    date=date(2026, 3, 3),
                    entries=[
                        WorklogEntry(
                            date=date(2026, 3, 3), ticket="A-2", summary="Y", author="Dev", budget="", hours=6.0
                        ),
                    ],
                ),
            ],
        )
        assert ts.total_hours == 14.0
        assert ts.working_days == 2
        assert ts.average_hours == 7.0
        assert len(ts.all_entries) == 2


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.theme == "system"
        assert s.federal_state == "SN"
        assert s.hours_per_day == 8.0
        assert s.max_yearly_hours == 1720.0

    def test_to_dict_roundtrip(self) -> None:
        s = Settings(jira_host="https://jira.example.com", email="test@example.com")
        d = s.to_dict()
        assert d["jira_host"] == "https://jira.example.com"
        assert d["email"] == "test@example.com"
        assert "federal_state" in d
