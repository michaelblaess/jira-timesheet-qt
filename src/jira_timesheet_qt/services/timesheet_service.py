"""Service: Worklogs zu Timesheet gruppieren und aufbereiten."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry


class TimesheetService:
    """Erstellt einen Timesheet aus rohen Worklog-Eintraegen."""

    @staticmethod
    def build_timesheet(
        entries: list[WorklogEntry],
        developer: str,
        email: str,
        date_from: date,
        date_to: date,
    ) -> Timesheet:
        """Gruppiert Worklogs nach Tagen und erstellt den Timesheet."""
        days_map: defaultdict[date, list[WorklogEntry]] = defaultdict(list)

        for entry in entries:
            days_map[entry.date].append(entry)

        days: list[TimesheetDay] = []
        for day_date in sorted(days_map.keys()):
            day_entries = days_map[day_date]
            day_entries.sort(key=lambda e: e.ticket)
            days.append(TimesheetDay(date=day_date, entries=day_entries))

        return Timesheet(
            developer=developer,
            email=email,
            date_from=date_from,
            date_to=date_to,
            days=days,
        )
