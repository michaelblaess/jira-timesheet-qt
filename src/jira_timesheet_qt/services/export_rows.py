"""Die Zellwerte einer Stundenzettel-Zeile, unabhaengig vom Ausgabeformat.

PDF und Markdown zeichnen dieselbe Tabelle mit unterschiedlichen Mitteln.
Damit eine geaenderte Spaltenlogik nicht an zwei Stellen nachgezogen werden
muss, steht die Berechnung der Werte hier - die Exporter kuemmern sich nur
noch um die Darstellung.

Public API:
    - `WEEKDAYS` - die Kurznamen der Wochentage, Montag zuerst.
    - `gap_values()` - Zellwerte einer Luecken- oder Feiertagszeile.
    - `entry_values()` - Zellwerte eines Worklog-Eintrags.
"""

from __future__ import annotations

from datetime import date

from jira_timesheet_qt.models.export_column import ExportColumn
from jira_timesheet_qt.models.timesheet import TimesheetDay, WorklogEntry

WEEKDAYS: tuple[str, ...] = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
"""Kurznamen der Wochentage in der Reihenfolge von `date.weekday()`."""


def gap_values(columns: list[ExportColumn], day_date: date, reason: str) -> list[str]:
    """Zellwerte einer Luecken- oder Feiertagszeile.

    Args:
        columns: Die aktiven Spalten in ihrer Reihenfolge.
        day_date: Der Tag ohne Buchung.
        reason: Der Grund, z.B. der Name des Feiertags.

    Returns:
        Ein Wert je Spalte, leer wo die Spalte hier nichts zu zeigen hat.
    """

    values = {
        "week": str(day_date.isocalendar()[1]),
        "weekday": WEEKDAYS[day_date.weekday()],
        "date": f"{day_date:%d.%m.}",
        "description": reason,
        "day_hours": "0.00",
    }
    return [values.get(c.key, "") for c in columns]


def entry_values(
    columns: list[ExportColumn],
    entry: WorklogEntry,
    day: TimesheetDay,
    is_first: bool,
    default_customer: str = "",
) -> list[str]:
    """Zellwerte eines Worklog-Eintrags.

    Args:
        columns: Die aktiven Spalten in ihrer Reihenfolge.
        entry: Der Eintrag.
        day: Der Tag, zu dem der Eintrag gehoert.
        is_first: True beim ersten Eintrag des Tages. Nur dort stehen
            Kalenderwoche, Wochentag, Datum und Tagessumme - bei den weiteren
            Eintraegen bleiben diese Zellen leer, damit der Tag als Block lesbar ist.
        default_customer: Faellt ein, wenn der Eintrag selbst keinen Kunden traegt.

    Returns:
        Ein Wert je Spalte, leer wo die Spalte hier nichts zu zeigen hat.
    """

    values = {
        "week": str(entry.date.isocalendar()[1]) if is_first else "",
        "weekday": WEEKDAYS[entry.date.weekday()] if is_first else "",
        "date": f"{entry.date:%d.%m.}" if is_first else "",
        "ticket": entry.ticket,
        "description": entry.summary,
        "customer": entry.customer or default_customer,
        "hours": f"{entry.hours:.2f}",
        "day_hours": f"{day.total_hours:.2f}" if is_first else "",
    }
    return [values.get(c.key, "") for c in columns]
