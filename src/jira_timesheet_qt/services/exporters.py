"""Die Auswahl des Exporters zu einem Format.

Alle vier Exporter koennen dasselbe: einen Stundenzettel an einen Pfad
schreiben. Was sie unterscheidet, sind ihre Konstruktoren - der eine braucht
ein Logo, der naechste die Spaltenbreiten, der dritte nichts davon. Diese
Datei kapselt genau das, damit die Oberflaeche nur noch `build_exporter()`
ruft und `export()` aufruft.

Die Importe der Exporter stehen bewusst in der Funktion: fpdf und openpyxl
sind schwer, und wer nur nach JSON schreibt, soll nicht auf sie warten.

Public API:
    - `TimesheetExporter` - was ein Exporter koennen muss.
    - `build_exporter()` - der Exporter zu einem Format.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from jira_timesheet_qt.models.export_format import ExportFormat, suggested_name
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet


class TimesheetExporter(Protocol):
    """Was jeder Exporter koennen muss."""

    def export(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]] | None = None,
        target_hours: float = 0.0,
        output_dir: str = "",
        output_path: str = "",
    ) -> str:
        """Schreibt den Stundenzettel und liefert den geschriebenen Pfad."""
        ...


def build_exporter(export_format: ExportFormat, settings: Settings) -> TimesheetExporter:
    """Baut den Exporter zu einem Format.

    Args:
        export_format: Das gewaehlte Ausgabeformat.
        settings: Die geladenen Einstellungen.

    Returns:
        Der fertig eingestellte Exporter.

    Raises:
        ValueError: Wenn zu dem Format kein Exporter bekannt ist.
    """

    if export_format.key == "excel":
        from jira_timesheet_qt.services.excel_exporter import ExcelExporter

        return ExcelExporter(
            logo_path=settings.logo_path,
            jira_host=settings.jira_host,
            hours_per_day=settings.hours_per_day,
            show_ticket_links=settings.show_ticket_links_in_export,
            columns=settings.export_columns,
            default_customer=settings.default_customer,
            mark_manual=settings.mark_manual_entries,
            manual_color=settings.manual_entry_color,
        )

    if export_format.key == "pdf":
        from jira_timesheet_qt.services.pdf_exporter import PdfExporter

        return PdfExporter(
            logo_path=settings.logo_path,
            jira_host=settings.jira_host,
            hours_per_day=settings.hours_per_day,
            columns=settings.export_columns,
            default_customer=settings.default_customer,
            mark_manual=settings.mark_manual_entries,
            manual_color=settings.manual_entry_color,
        )

    if export_format.key == "json":
        from jira_timesheet_qt.services.json_exporter import JsonExporter

        return JsonExporter(
            jira_host=settings.jira_host,
            hours_per_day=settings.hours_per_day,
            default_customer=settings.default_customer,
        )

    if export_format.key == "markdown":
        from jira_timesheet_qt.services.markdown_exporter import MarkdownExporter

        return MarkdownExporter(
            jira_host=settings.jira_host,
            hours_per_day=settings.hours_per_day,
            show_ticket_links=settings.show_ticket_links_in_export,
            columns=settings.export_columns,
            default_customer=settings.default_customer,
            mark_manual=settings.mark_manual_entries,
        )

    raise ValueError(f"Kein Exporter fuer Format {export_format.key}")


def suggested_filename(export_format: ExportFormat, timesheet: Timesheet) -> str:
    """Der vorgeschlagene Dateiname fuer ein Format.

    Args:
        export_format: Das gewaehlte Ausgabeformat.
        timesheet: Der zu exportierende Stundenzettel.

    Returns:
        Der Dateiname, ohne Verzeichnis.
    """

    return suggested_name(export_format, timesheet.date_from, timesheet.date_to)
