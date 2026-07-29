"""Gemeinsame Spaltendefinition fuer Tabelle und Baum.

Beide Listenmodelle (flach und nach Tag gruppiert) zeigen genau die Spalten,
die in den Einstellungen unter "Spalten" als sichtbar markiert sind - in der
dort festgelegten Reihenfolge und mit der dort gewaehlten Bezeichnung. Damit
richtet sich die Anzeige nach derselben Konfiguration wie der Export.

Rendern und Sortieren jeder Zelle liegt hier zentral, damit Tabelle und Baum
identisch formatieren. Die Modelle halten nur noch die aktive Spaltenliste.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jira_timesheet_qt.models.export_column import (
    DESCRIPTION_KEY,
    ExportColumn,
    default_columns,
    default_label,
)
from jira_timesheet_qt.models.timesheet import WorklogEntry

# Spalten, die bei manuellen Eintraegen direkt in der Tabelle editierbar sind.
# Datum/Kunde bleiben dem vollen Erfassungsdialog vorbehalten (Datum wuerde den
# Eintrag zwischen Tagen/Gruppen verschieben).
EDITABLE_KEYS = (DESCRIPTION_KEY, "hours")

# Zahlenspalten mit Stunden. Sie tragen ihre eigene Bedeutung (Aufwand bzw. die
# Soll-Ist-Ampel der Tagessumme) und werden NICHT von der Markierungsfarbe
# manueller Eintraege eingefaerbt - sonst kollidiert Rot mit der gruenen Summe.
HOUR_KEYS = ("hours", "day_hours")

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


@dataclass(frozen=True)
class _ColumnMeta:
    """Darstellungs-Vorgaben einer Spalte (unabhaengig von der Bezeichnung)."""

    numeric: bool
    width: int


# Vorgaben je Spaltenschluessel. Die Schluessel decken sich mit COLUMN_DEFAULTS
# aus export_column - die Bezeichnung kommt aus der Nutzer-Konfiguration.
_META: dict[str, _ColumnMeta] = {
    "week": _ColumnMeta(numeric=True, width=60),
    "weekday": _ColumnMeta(numeric=False, width=60),
    "date": _ColumnMeta(numeric=False, width=110),
    "ticket": _ColumnMeta(numeric=False, width=130),
    DESCRIPTION_KEY: _ColumnMeta(numeric=False, width=420),
    "customer": _ColumnMeta(numeric=False, width=160),
    "hours": _ColumnMeta(numeric=True, width=100),
    "day_hours": _ColumnMeta(numeric=True, width=130),
}


@dataclass(frozen=True)
class GridColumn:
    """Eine im Grid angezeigte Spalte."""

    key: str
    title: str
    numeric: bool
    width: int
    editable: bool
    stretch: bool


def build_columns(columns: list[ExportColumn]) -> list[GridColumn]:
    """Baut die sichtbaren Grid-Spalten aus der Spalten-Konfiguration.

    Args:
        columns:
            Die Spalten-Konfiguration aus den Einstellungen.

    Returns:
        Die sichtbaren Spalten in konfigurierter Reihenfolge. Ist keine Spalte
        sichtbar, kommen die Standard-Spalten zurueck - eine Tabelle ganz ohne
        Spalten waere unbenutzbar.
    """
    result = [_to_grid(column) for column in columns if column.visible and column.key in _META]
    if result:
        return result
    return [_to_grid(column) for column in default_columns()]


def _to_grid(column: ExportColumn) -> GridColumn:
    meta = _META[column.key]
    return GridColumn(
        key=column.key,
        title=column.label.strip() or default_label(column.key),
        numeric=meta.numeric,
        width=meta.width,
        editable=column.key in EDITABLE_KEYS,
        stretch=column.key == DESCRIPTION_KEY,
    )


def is_day_total_cell(key: str, is_group: bool) -> bool:
    """Zeigt die Zelle eine Tagessumme (fuer die Soll-Ist-Ampel)?

    Args:
        key:
            Spaltenschluessel der Zelle.
        is_group:
            True fuer eine Tages-Gruppenzeile des Baums, False fuer eine
            Eintragszeile (auch in der flachen Tabelle).

    Returns:
        True, wenn die Zelle die Tagessumme traegt - in Gruppenzeilen die
        Stunden- und die Tagessummen-Spalte, in Eintragszeilen nur die
        Tagessummen-Spalte (die Stunden-Spalte zeigt dort den Einzelwert).
    """
    if is_group:
        return key in ("hours", "day_hours")
    return key == "day_hours"


def _fmt_hours(hours: float) -> str:
    """Stunden mit deutschem Dezimalkomma, zwei Nachkommastellen."""
    return f"{hours:.2f}".replace(".", ",")


def display_value(entry: WorklogEntry, key: str, day_total: float, default_customer: str) -> str:
    """Formatiert die Zelle eines Eintrags fuer die Anzeige (deutsche Schreibweise).

    Args:
        entry:
            Der darzustellende Eintrag.
        key:
            Spaltenschluessel.
        day_total:
            Tagessumme des Eintrags (fuer die Spalte "Tagessumme").
        default_customer:
            Vorgabe-Kunde aus den Einstellungen (fuer Jira-Eintraege ohne Kunde).

    Returns:
        Der anzuzeigende Text, leer bei unbekanntem Schluessel.
    """
    if key == "week":
        return f"{entry.date.isocalendar().week:02d}"
    if key == "weekday":
        return _WEEKDAYS[entry.date.weekday()]
    if key == "date":
        return entry.date.strftime("%d.%m.%Y")
    if key == "ticket":
        return entry.ticket
    if key == DESCRIPTION_KEY:
        return entry.summary
    if key == "customer":
        return entry.customer or default_customer
    if key == "hours":
        return _fmt_hours(entry.hours)
    if key == "day_hours":
        return _fmt_hours(day_total)
    return ""


def sort_value(entry: WorklogEntry, key: str, day_total: float, default_customer: str) -> object:
    """Liefert den Rohwert einer Zelle - danach wird sortiert (nicht nach Anzeige)."""
    if key == "week":
        return entry.date.isocalendar().week
    if key == "weekday":
        return entry.date.weekday()
    if key == "date":
        return entry.date
    if key == "hours":
        return entry.hours
    if key == "day_hours":
        return day_total
    return display_value(entry, key, day_total, default_customer).lower()


def group_display(key: str, day: date, entry_count: int, day_total: float) -> str:
    """Formatiert die Zelle einer Tages-Gruppenzeile im Baum.

    Datum, Tag und KW beschreiben den Tag; die Beschreibungs-Spalte traegt die
    Anzahl der Eintraege, die Stunden-Spalten die Tagessumme. Alles andere
    bleibt leer.
    """
    if key == "week":
        return f"{day.isocalendar().week:02d}"
    if key == "weekday":
        return _WEEKDAYS[day.weekday()]
    if key == "date":
        return day.strftime("%d.%m.%Y")
    if key == DESCRIPTION_KEY:
        return "1 Eintrag" if entry_count == 1 else f"{entry_count} Einträge"
    if key in ("hours", "day_hours"):
        return _fmt_hours(day_total)
    return ""


def group_sort(key: str, day: date, day_total: float) -> object:
    """Rohwert einer Gruppenzeile zum Sortieren."""
    if key == "week":
        return day.isocalendar().week
    if key == "date":
        return day
    if key in ("hours", "day_hours"):
        return day_total
    return ""
