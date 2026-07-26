"""Bindet die Exporter an die Oberflaeche.

Die Exporter selbst stammen unveraendert aus der TUI und kennen keine
Oberflaeche. Hier entstehen nur der Speichern-Dialog, die Vorbelegung des
Dateinamens und die Druckvorschau.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QDesktopServices, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog, QWidget

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.services.excel_exporter import ExcelExporter
from jira_timesheet_qt.services.pdf_exporter import PdfExporter


@dataclass(frozen=True)
class ExportResult:
    """Ergebnis eines Exports."""

    path: str
    cancelled: bool = False


class ExportService:
    """Erzeugt Dateien aus einem Stundenzettel und zeigt die Druckvorschau."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- Dateien --------------------------------------------------------

    def export_excel(
        self,
        timesheet: Timesheet,
        parent: QWidget,
        missing_days: list[tuple[date, str]] | None = None,
    ) -> ExportResult:
        """Fragt nach dem Ziel und schreibt die Arbeitsmappe."""
        target = self._ask_target(parent, ExcelExporter.suggested_filename(timesheet), "Arbeitsmappe (*.xlsx)")
        if not target:
            return ExportResult("", cancelled=True)

        s = self._settings
        exporter = ExcelExporter(
            logo_path=s.logo_path,
            jira_host=s.jira_host,
            hours_per_day=s.hours_per_day,
            show_ticket_links=s.show_ticket_links_in_export,
            columns=s.export_columns,
            default_customer=s.default_customer,
            mark_manual=s.mark_manual_entries,
            manual_color=s.manual_entry_color,
        )
        path = exporter.export(
            timesheet,
            missing_days=missing_days or [],
            target_hours=self._target_hours(timesheet) if s.show_target_hours_in_export else 0.0,
            output_path=target,
        )
        return ExportResult(path)

    def export_pdf(
        self,
        timesheet: Timesheet,
        parent: QWidget,
        missing_days: list[tuple[date, str]] | None = None,
    ) -> ExportResult:
        """Fragt nach dem Ziel und schreibt das PDF."""
        target = self._ask_target(parent, PdfExporter.suggested_filename(timesheet), "PDF-Dokument (*.pdf)")
        if not target:
            return ExportResult("", cancelled=True)

        s = self._settings
        exporter = PdfExporter(
            logo_path=s.logo_path,
            jira_host=s.jira_host,
            hours_per_day=s.hours_per_day,
            columns=s.export_columns,
            default_customer=s.default_customer,
            mark_manual=s.mark_manual_entries,
            manual_color=s.manual_entry_color,
        )
        path = exporter.export(
            timesheet,
            missing_days=missing_days or [],
            target_hours=self._target_hours(timesheet) if s.show_target_hours_in_export else 0.0,
            output_path=target,
        )
        return ExportResult(path)

    @staticmethod
    def open_file(path: str) -> None:
        """Oeffnet die erzeugte Datei im Standardprogramm."""
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path))))

    # --- Druckvorschau --------------------------------------------------

    def show_print_preview(self, timesheet: Timesheet, parent: QWidget) -> None:
        """Zeigt die Druckvorschau des Stundenzettels.

        In der TUI gab es das nicht - Drucken ging nur ueber den Umweg PDF.
        """
        document = QTextDocument()
        document.setDefaultStyleSheet(_PRINT_CSS)
        document.setHtml(self.build_print_html(timesheet))

        dialog = QPrintPreviewDialog(parent)
        dialog.setWindowTitle("Druckvorschau")
        dialog.resize(1000, 760)

        def render(printer: object) -> None:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))  # type: ignore[attr-defined]
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)  # type: ignore[attr-defined]
            printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)  # type: ignore[attr-defined]
            document.print_(printer)  # type: ignore[arg-type]

        dialog.paintRequested.connect(render)
        dialog.exec()

    def build_print_html(self, timesheet: Timesheet) -> str:
        """Baut die Druckfassung als HTML.

        Bewusst eigenes Markup statt der PDF-Ausgabe: die Vorschau soll
        aussehen wie die Liste auf dem Bildschirm, nicht wie das
        Export-Formular.
        """
        rows: list[str] = []
        for day in timesheet.days:
            first = True
            for entry in day.entries:
                day_cell = f"{day.date:%d.%m.%Y}" if first else ""
                sum_cell = _hours(day.total_hours) if first else ""
                rows.append(
                    "<tr>"
                    f"<td>{day_cell}</td>"
                    f"<td>{_escape(entry.ticket)}</td>"
                    f"<td>{_escape(entry.summary)}</td>"
                    f'<td class="num">{_hours(entry.hours)}</td>'
                    f'<td class="num">{sum_cell}</td>'
                    "</tr>"
                )
                first = False

        period = f"{timesheet.date_from:%d.%m.%Y} bis {timesheet.date_to:%d.%m.%Y}"
        return (
            f"<h1>Stundenzettel</h1>"
            f"<p class='meta'>{_escape(timesheet.developer)}<br>{period}</p>"
            "<table>"
            "<thead><tr><th>Datum</th><th>Vorgang</th><th>Beschreibung</th>"
            "<th class='num'>Stunden</th><th class='num'>Tagessumme</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            f"<p class='total'>Gesamt: {_hours(timesheet.total_hours)} Stunden an "
            f"{timesheet.working_days} Arbeitstagen</p>"
        )

    # --- Hilfen ---------------------------------------------------------

    def _target_hours(self, timesheet: Timesheet) -> float:
        """Sollstunden des Zeitraums nach Arbeitstagen."""
        from jira_timesheet_qt.services.holiday_service import HolidayService

        service = HolidayService(self._settings.federal_state)
        workdays = service.count_workdays(timesheet.date_from, timesheet.date_to)
        return workdays * self._settings.hours_per_day

    def _ask_target(self, parent: QWidget, suggestion: str, file_filter: str) -> str:
        """Speichern-Dialog, vorbelegt mit dem zuletzt genutzten Verzeichnis."""
        start = str(Path(self._settings.last_export_dir or str(Path.home() / "Desktop")) / suggestion)
        target, _ = QFileDialog.getSaveFileName(parent, "Speichern unter", start, file_filter)
        if target:
            # Beim naechsten Mal dort wieder anfangen.
            self._settings.last_export_dir = str(Path(target).parent)
            self._settings.save()
        return target


def _hours(value: float) -> str:
    """Stunden mit deutschem Dezimalkomma."""
    return f"{value:.2f}".replace(".", ",")


def _escape(text: str) -> str:
    """Macht Zeichen unschaedlich, die als Auszeichnung gelesen wuerden."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Druckfassung bewusst schwarz auf weiss - unabhaengig vom Erscheinungsbild.
_PRINT_CSS = """
h1 { font-size: 16pt; margin-bottom: 2pt; }
p.meta { color: #555; font-size: 9pt; margin-top: 0; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; }
th { text-align: left; border-bottom: 1px solid #333; padding: 4px; font-size: 8pt; }
td { border-bottom: 1px solid #ddd; padding: 4px; }
td.num, th.num { text-align: right; }
p.total { margin-top: 10pt; font-size: 10pt; font-weight: bold; }
"""
