"""Domain Models fuer Stundenzettel-Daten."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class WorklogEntry:
    """Einzelner Worklog-Eintrag aus Jira."""

    date: date
    ticket: str
    summary: str
    author: str
    budget: str
    hours: float
    status: str = ""
    issuetype: str = ""
    epic: str = ""
    components: str = ""
    labels: str = ""
    priority: str = ""
    resolution: str = ""
    assignee: str = ""
    created: str = ""
    updated: str = ""
    total_logged: str = ""
    # Manuell im Tool erfasst statt aus Jira geholt. Wird NICHT im Jira-Cache
    # abgelegt - die Quelle ist die SQLite-Tabelle manual_entries.
    manual: bool = False
    # Id des zugehoerigen Datensatzes in manual_entries; 0 bei Jira-Eintraegen.
    manual_id: int = 0
    # Kunde/Kostenstelle. Bei Jira-Eintraegen leer; die Exporte fallen dann
    # auf die Einstellung default_customer zurueck.
    customer: str = ""


@dataclass
class TimesheetDay:
    """Alle Worklogs eines Tages mit Tagessumme."""

    date: date
    entries: list[WorklogEntry] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        """Summe aller Stunden des Tages."""
        return sum(entry.hours for entry in self.entries)


@dataclass
class Timesheet:
    """Kompletter Stundenzettel fuer einen Zeitraum."""

    developer: str
    email: str
    date_from: date
    date_to: date
    days: list[TimesheetDay] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        """Gesamtstunden ueber alle Tage."""
        return sum(day.total_hours for day in self.days)

    @property
    def working_days(self) -> int:
        """Anzahl Tage mit mindestens einem Eintrag."""
        return len(self.days)

    @property
    def average_hours(self) -> float:
        """Durchschnittliche Stunden pro Arbeitstag."""
        if self.working_days == 0:
            return 0.0
        return self.total_hours / self.working_days

    @property
    def all_entries(self) -> list[WorklogEntry]:
        """Alle Eintraege flach als Liste."""
        result: list[WorklogEntry] = []
        for day in self.days:
            result.extend(day.entries)
        return result
