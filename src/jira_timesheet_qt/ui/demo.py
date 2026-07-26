"""Beispieldaten fuer den Start ohne Jira-Zugang.

Nur zum Ansehen der Oberflaeche gedacht. Faellt weg, sobald die Anbindung an
Jira steht (Stufe 1).
"""

from __future__ import annotations

from datetime import date

from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry

_ROWS: tuple[tuple[int, str, str, float, bool], ...] = (
    (20, "PROJ-0", "Sitefinity Security Advisory auswerten", 2.5, False),
    (20, "PROJ-0", "Fotoupload: AllowMultipleFiles pruefen", 1.5, False),
    (20, "PROJ-0", "Usercentrics DSI-App, V3-Flag nachziehen", 4.0, False),
    (21, "PROJ-0", "Speichergesteuerter Reboot, Schwellwert justieren", 3.0, False),
    (21, "PROJ-0", "GitLab-Deploy ueber OIDC, Federated Credentials", 5.0, False),
    (22, "PROJ-0", "Utility-Kit zentral, Bundle-Ballast entfernen", 6.5, False),
    (22, "", "Abstimmung Release-Planung", 1.5, True),
    (23, "PROJ-0", "Frontend-Logging konsolidieren, Wrapper zusammenfuehren", 4.0, False),
    (23, "PROJ-0", "Angular-Pipeline nach dem Lockdown", 2.5, False),
    (24, "PROJ-0", "Formular-Zusammenfassung als PDF, Fallback pruefen", 7.0, False),
    (27, "PROJ-0", "Linkliste, NRE-Guard in MultiLinkUtils", 3.5, False),
    (27, "PROJ-0", "axios durch fetch ersetzen, Review", 2.0, False),
    (28, "PROJ-0", "Bundle-Minifizierung, per-Output pruefen", 4.5, False),
    (28, "", "Zeiterfassung nachtragen", 0.5, True),
    (29, "PROJ-0", "LockRemover, Aufgabe und Widgets", 6.0, False),
)


def demo_timesheet() -> Timesheet:
    """Baut einen Stundenzettel mit Beispieleintraegen fuer Juli 2026."""
    by_day: dict[int, list[WorklogEntry]] = {}
    for day, ticket, summary, hours, manual in _ROWS:
        entry = WorklogEntry(
            date=date(2026, 7, day),
            ticket=ticket or "MANUELL",
            summary=summary,
            author="Michael Blaess",
            budget="Vertrieb" if not manual else "",
            hours=hours,
            manual=manual,
        )
        by_day.setdefault(day, []).append(entry)

    days = [TimesheetDay(date=date(2026, 7, day), entries=entries) for day, entries in sorted(by_day.items())]
    return Timesheet(
        developer="Michael Blaess",
        email="mail@michaelblaess.de",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        days=days,
    )
