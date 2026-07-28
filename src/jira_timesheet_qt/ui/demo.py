"""Beispieldaten fuer den Start ohne Jira-Zugang.

Nur zum Ansehen der Oberflaeche gedacht. Faellt weg, sobald die Anbindung an
Jira steht (Stufe 1).
"""

from __future__ import annotations

from datetime import date

from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry

# Frei erfundene Eintraege - KEINE realen Ticketdaten. Struktur (Tage, Stunden,
# manuelle Eintraege) so gewaehlt, dass Summen, Wochensummen und Kalender die
# Oberflaeche gut zeigen.
_ROWS: tuple[tuple[int, str, str, float, bool], ...] = (
    (20, "PROJ-101", "Sicherheitshinweis auswerten", 2.5, False),
    (20, "PROJ-102", "Datei-Upload pruefen", 1.5, False),
    (20, "PROJ-103", "Consent-Dialog nachziehen", 4.0, False),
    (21, "PROJ-104", "Neustart-Schwellwert justieren", 3.0, False),
    (21, "PROJ-105", "Deploy ueber OIDC einrichten", 5.0, False),
    (22, "PROJ-106", "Bibliothek zentralisieren, Bundle-Ballast entfernen", 6.5, False),
    (22, "", "Abstimmung Release-Planung", 1.5, True),
    (23, "PROJ-107", "Logging konsolidieren, Wrapper zusammenfuehren", 4.0, False),
    (23, "PROJ-108", "Build-Pipeline anpassen", 2.5, False),
    (24, "PROJ-109", "PDF-Zusammenfassung, Fallback pruefen", 7.0, False),
    (27, "PROJ-110", "Linkliste, NRE-Guard ergaenzen", 3.5, False),
    (27, "PROJ-111", "HTTP-Client ersetzen, Review", 2.0, False),
    (28, "PROJ-112", "Bundle minifizieren, per-Output pruefen", 4.5, False),
    (28, "", "Zeiterfassung nachtragen", 0.5, True),
    (29, "PROJ-113", "Sperr-Werkzeug, Aufgabe und Widgets", 6.0, False),
)


def demo_timesheet() -> Timesheet:
    """Baut einen Stundenzettel mit Beispieleintraegen fuer Juli 2026."""
    by_day: dict[int, list[WorklogEntry]] = {}
    for day, ticket, summary, hours, manual in _ROWS:
        entry = WorklogEntry(
            date=date(2026, 7, day),
            ticket=ticket or "MANUELL",
            summary=summary,
            author="Max Mustermann",
            budget="Vertrieb" if not manual else "",
            hours=hours,
            manual=manual,
        )
        by_day.setdefault(day, []).append(entry)

    days = [TimesheetDay(date=date(2026, 7, day), entries=entries) for day, entries in sorted(by_day.items())]
    return Timesheet(
        developer="Max Mustermann",
        email="max.mustermann@example.com",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        days=days,
    )
