"""Anonymisiert Timesheet-Daten fuer Screenshots und Demos."""

from __future__ import annotations

import random

from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry

# Zentrale Fake-Werte fuer den Anonymisierungs-Modus (Screenshots). Werden auch
# vom ConfigPanel-Header, der Log-Zensur und dem Detail-Dialog verwendet.
FAKE_EMAIL = "user@example.com"
FAKE_HOST = "https://jira.example.com"

_FAKE_PROJECTS = ["PROJ", "TASK", "FEAT", "DEV", "OPS", "INFRA", "WEB", "APP"]

_FAKE_SUMMARIES = [
    "Update user authentication flow",
    "Fix pagination in dashboard",
    "Refactor database connection pool",
    "Add export functionality",
    "Improve error handling",
    "Update dependencies to latest",
    "Fix responsive layout issues",
    "Implement caching layer",
    "Add unit tests for services",
    "Optimize API response time",
    "Fix memory leak in worker",
    "Update CI/CD pipeline",
    "Add logging and monitoring",
    "Refactor configuration module",
    "Implement retry logic",
    "Fix date formatting bug",
    "Add input validation",
    "Update documentation",
    "Performance optimization",
    "Security patch for auth module",
    "Implement search feature",
    "Fix timezone handling",
    "Add CSV export option",
    "Refactor event handling",
    "Update email templates",
    "Fix broken links in navigation",
    "Add dark mode support",
    "Implement webhook handler",
    "Fix concurrent access issue",
    "Add health check endpoint",
]

_FAKE_AUTHORS = [
    "Mueller, Thomas",
    "Schmidt, Anna",
    "Mustermann, Max",
    "Fischer, Laura",
    "Wagner, Stefan",
]

_FAKE_COMPONENTS = [
    "Frontend",
    "Backend",
    "API",
    "Database",
    "Infrastructure",
    "Security",
    "Testing",
    "DevOps",
    "UI/UX",
    "",
]

_FAKE_BUDGETS = [
    "Projekt Alpha",
    "Projekt Beta",
    "Wartung",
    "nicht zugeordnet",
]


def anonymize_timesheet(timesheet: Timesheet) -> Timesheet:
    """Erzeugt eine anonymisierte Kopie des Timesheets.

    Ticket-Keys, Beschreibungen, Autoren und Komponenten werden ersetzt.
    Stunden, Daten und Struktur bleiben erhalten.
    """
    rng = random.Random(42)
    ticket_map: dict[str, str] = {}
    summary_idx = 0

    anon_days: list[TimesheetDay] = []

    for day in timesheet.days:
        anon_entries: list[WorklogEntry] = []

        for entry in day.entries:
            if entry.ticket not in ticket_map:
                project = rng.choice(_FAKE_PROJECTS)
                num = len(ticket_map) + 1001
                ticket_map[entry.ticket] = f"{project}-{num}"

            anon_ticket = ticket_map[entry.ticket]
            anon_summary = _FAKE_SUMMARIES[summary_idx % len(_FAKE_SUMMARIES)]
            summary_idx += 1

            anon_entries.append(
                WorklogEntry(
                    date=entry.date,
                    ticket=anon_ticket,
                    summary=anon_summary,
                    author=rng.choice(_FAKE_AUTHORS),
                    budget=rng.choice(_FAKE_BUDGETS),
                    hours=entry.hours,
                    status=entry.status,
                    issuetype=entry.issuetype,
                    epic="",
                    components=rng.choice(_FAKE_COMPONENTS),
                    labels="",
                    priority=entry.priority,
                    resolution=entry.resolution,
                    assignee=rng.choice(_FAKE_AUTHORS),
                    created=entry.created,
                    updated=entry.updated,
                    total_logged=entry.total_logged,
                )
            )

        anon_days.append(TimesheetDay(date=day.date, entries=anon_entries))

    return Timesheet(
        developer=rng.choice(_FAKE_AUTHORS),
        email=FAKE_EMAIL,
        date_from=timesheet.date_from,
        date_to=timesheet.date_to,
        days=anon_days,
    )
