"""PDF Export — Stundenzettel als signierbares PDF mit Unicode-Unterstuetzung."""

from __future__ import annotations

import contextlib
import os
from datetime import date
from pathlib import Path

from fpdf import FPDF

from jira_timesheet_qt.models.export_column import (
    ExportColumn,
    default_columns,
    pdf_column_widths,
)
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry

# Arial TTF Pfade (Windows)
_ARIAL_REGULAR = "C:/Windows/Fonts/arial.ttf"
_ARIAL_BOLD = "C:/Windows/Fonts/arialbd.ttf"
_FONT_NAME = "Arial"

_WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


class PdfExporter:
    """Erzeugt eine PDF-Datei im gleichen Layout wie der Excel-Export."""

    def __init__(
        self,
        logo_path: str = "",
        jira_host: str = "",
        hours_per_day: float = 8.0,
        columns: list[ExportColumn] | None = None,
        default_customer: str = "",
        mark_manual: bool = True,
        manual_color: str = "FF0000",
    ) -> None:
        self._logo_path = logo_path
        self._jira_host = jira_host.rstrip("/")
        self._hours_per_day = hours_per_day
        self._default_customer = default_customer
        self._mark_manual = mark_manual
        self._manual_rgb = self._hex_to_rgb(manual_color)
        source = columns if columns is not None else default_columns()
        self._columns = [c for c in source if c.enabled]
        self._widths = pdf_column_widths(self._columns)
        # Rechtsbuendige Spalten (Zahlen).
        self._right_aligned = {"hours", "day_hours"}

    @staticmethod
    def suggested_filename(timesheet: Timesheet) -> str:
        """Liefert einen vorgeschlagenen Dateinamen fuer den Speichern-Dialog."""
        from datetime import datetime

        now = datetime.now()
        return f"Stundenzettel_{timesheet.date_from:%Y-%m-%d}_{timesheet.date_to:%Y-%m-%d}_{now:%Y%m%d_%H%M%S}.pdf"

    def export(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]] | None = None,
        target_hours: float = 0.0,
        output_dir: str = "",
        output_path: str = "",
    ) -> str:
        """Exportiert den Timesheet als .pdf Datei.

        Ist ``output_path`` gesetzt, wird genau dieser Pfad verwendet (z.B. aus
        dem Speichern-Dialog). Andernfalls wird ein Name in ``output_dir`` bzw.
        auf dem Desktop erzeugt.
        """
        if output_path:
            filepath = output_path
        else:
            if not output_dir:
                output_dir = str(Path.home() / "Desktop")
            filepath = os.path.join(output_dir, self.suggested_filename(timesheet))

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_left_margin(10)
        pdf.set_right_margin(10)
        self._register_fonts(pdf)
        pdf.add_page()

        self._add_logo(pdf)
        self._add_header(pdf, timesheet, target_hours)
        self._add_table(pdf, timesheet, missing_days or [])
        self._add_footer(pdf)

        pdf.output(filepath)
        return str(Path(filepath).resolve())

    def _register_fonts(self, pdf: FPDF) -> None:
        """Registriert Arial Unicode-Font fuer Umlaut-Unterstuetzung."""
        if os.path.isfile(_ARIAL_REGULAR):
            pdf.add_font(_FONT_NAME, "", _ARIAL_REGULAR)
        if os.path.isfile(_ARIAL_BOLD):
            pdf.add_font(_FONT_NAME, "B", _ARIAL_BOLD)

    def _font(self, style: str = "", size: int = 10) -> tuple[str, str, int]:
        """Gibt Font-Tupel zurueck, Fallback auf Helvetica."""
        if os.path.isfile(_ARIAL_REGULAR):
            return (_FONT_NAME, style, size)
        return ("Helvetica", style, size)

    def _add_logo(self, pdf: FPDF) -> None:
        """Fuegt das Logo oben links ein."""
        logo = self._find_logo()
        if logo and os.path.isfile(logo):
            with contextlib.suppress(Exception):
                pdf.image(logo, x=10, y=8, w=45)

    def _find_logo(self) -> str:
        """Sucht das Logo: erst Settings-Pfad, dann assets/logo.png."""
        if self._logo_path and os.path.isfile(self._logo_path):
            return self._logo_path

        here = Path(__file__).resolve().parent.parent.parent.parent
        default_logo = here / "assets" / "logo.png"
        if default_logo.is_file():
            return str(default_logo)

        return ""

    def _add_header(self, pdf: FPDF, ts: Timesheet, target_hours: float) -> None:
        """Fuegt Titel, Entwickler, Zeitraum hinzu."""
        pdf.set_y(10)
        pdf.set_x(55)
        pdf.set_font(*self._font("B", 16))
        pdf.cell(0, 10, "Stundenzettel", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
        pdf.set_font(*self._font("B", 10))
        pdf.cell(30, 6, "Entwickler:", new_x="END")
        pdf.set_font(*self._font("", 10))
        pdf.cell(0, 6, ts.developer, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font(*self._font("B", 10))
        pdf.cell(30, 6, "Zeitraum:", new_x="END")
        pdf.set_font(*self._font("", 10))
        date_range = f"{ts.date_from:%d.%m.%Y} - {ts.date_to:%d.%m.%Y}"
        pdf.cell(80, 6, date_range, new_x="END")

        pdf.set_font(*self._font("B", 10))
        pdf.cell(25, 6, "Gesamt (h):", new_x="END")
        pdf.cell(20, 6, f"{ts.total_hours:.2f}", new_x="LMARGIN", new_y="NEXT")

        if target_hours > 0:
            pdf.set_font(*self._font("", 9))
            pdf.set_x(145)
            diff = ts.total_hours - target_hours
            diff_sign = "+" if diff >= 0 else ""
            pdf.cell(
                0, 5, f"Soll: {target_hours:.0f}h  |  Differenz: {diff_sign}{diff:.2f}h", new_x="LMARGIN", new_y="NEXT"
            )

        pdf.ln(4)

    def _add_table(
        self,
        pdf: FPDF,
        ts: Timesheet,
        missing_days: list[tuple[date, str]],
    ) -> None:
        """Fuegt die Daten-Tabelle hinzu."""
        self._add_table_header(pdf)

        day_map = {day.date: day for day in ts.days}
        gap_map = dict(missing_days)
        all_dates = sorted(set(day_map.keys()) | set(gap_map.keys()))

        pdf.set_font(*self._font("", 8))
        row_height = 5.5
        table_width = sum(self._widths)

        for d in all_dates:
            if d in gap_map and d not in day_map:
                if pdf.get_y() + row_height > 190:
                    pdf.add_page()
                    self._add_table_header(pdf)
                    pdf.set_font(*self._font("", 8))

                reason = gap_map[d]
                is_holiday = "—" not in reason

                y_pos = pdf.get_y()
                pdf.set_draw_color(180, 180, 180)
                pdf.line(10, y_pos, 10 + table_width, y_pos)

                if is_holiday:
                    pdf.set_text_color(150, 150, 150)
                else:
                    pdf.set_text_color(200, 0, 0)

                self._write_row(pdf, row_height, self._gap_values(d, reason))
                pdf.set_text_color(0, 0, 0)
                continue

            if d not in day_map:
                continue

            day = day_map[d]
            needed_height = row_height * len(day.entries) + 2
            if pdf.get_y() + needed_height > 190:
                pdf.add_page()
                self._add_table_header(pdf)
                pdf.set_font(*self._font("", 8))

            for i, entry in enumerate(day.entries):
                is_first = i == 0

                if is_first:
                    y_pos = pdf.get_y()
                    pdf.set_draw_color(0, 0, 0)
                    pdf.line(10, y_pos, 10 + table_width, y_pos)

                mark = entry.manual and self._mark_manual
                if mark:
                    pdf.set_text_color(*self._manual_rgb)
                    pdf.set_font(*self._font("B", 8))

                self._write_row(
                    pdf,
                    row_height,
                    self._entry_values(entry, day, is_first),
                    bold_last=is_first,
                )

                if mark:
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font(*self._font("", 8))

    def _gap_values(self, d: date, reason: str) -> list[str]:
        """Zellwerte einer Luecken-/Feiertagszeile fuer die aktiven Spalten."""
        values = {
            "week": str(d.isocalendar()[1]),
            "weekday": _WEEKDAYS[d.weekday()],
            "date": f"{d:%d.%m.}",
            "description": reason,
            "day_hours": "0.00",
        }
        return [values.get(c.key, "") for c in self._columns]

    def _entry_values(self, entry: WorklogEntry, day: TimesheetDay, is_first: bool) -> list[str]:
        """Zellwerte eines Worklog-Eintrags fuer die aktiven Spalten."""
        values = {
            "week": str(entry.date.isocalendar()[1]) if is_first else "",
            "weekday": _WEEKDAYS[entry.date.weekday()] if is_first else "",
            "date": f"{entry.date:%d.%m.}" if is_first else "",
            "ticket": entry.ticket,
            "description": entry.summary,
            "customer": entry.customer or self._default_customer,
            "hours": f"{entry.hours:.2f}",
            "day_hours": f"{day.total_hours:.2f}" if is_first else "",
        }
        return [values.get(c.key, "") for c in self._columns]

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        """Wandelt RRGGBB in ein RGB-Tripel; Fallback Rot bei ungueltiger Eingabe."""
        raw = (value or "").strip().lstrip("#")
        if len(raw) != 6:
            return (255, 0, 0)
        try:
            return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        except ValueError:
            return (255, 0, 0)

    def _add_table_header(self, pdf: FPDF) -> None:
        """Zeichnet die Header-Zeile der Tabelle."""
        pdf.set_font(*self._font("B", 8))
        pdf.set_fill_color(200, 200, 200)
        pdf.set_draw_color(180, 180, 180)

        left = pdf.l_margin
        y = pdf.get_y()
        x = left
        for column, width in zip(self._columns, self._widths, strict=False):
            pdf.set_xy(x, y)
            align = "R" if column.key in self._right_aligned else "L"
            pdf.cell(width, 6, f" {column.label}", border=1, fill=True, align=align)
            x += width
        pdf.set_xy(left, y + 6)

    def _add_footer(self, pdf: FPDF) -> None:
        """Fuegt die Unterschriftszeile hinzu."""
        pdf.ln(10)
        y_pos = pdf.get_y()

        pdf.set_draw_color(0, 0, 0)
        pdf.line(55, y_pos, 250, y_pos)

        pdf.set_font(*self._font("", 9))
        pdf.set_x(55)
        pdf.cell(40, 6, "bestätigt am:", new_x="END")
        pdf.cell(0, 6, "Projektleiter (Blockschrift, Unterschrift)", new_x="LMARGIN", new_y="NEXT")

    def _write_row(
        self,
        pdf: FPDF,
        row_height: float,
        values: list[str],
        bold_last: bool = False,
    ) -> None:
        """Schreibt eine Zeile mit absoluten X-Positionen pro Spalte."""
        left = pdf.l_margin
        y = pdf.get_y()

        pdf.set_draw_color(220, 220, 220)

        x = left
        for i, (width, val) in enumerate(zip(self._widths, values, strict=False)):
            pdf.set_xy(x, y)

            is_right = self._columns[i].key in self._right_aligned
            is_last_col = i == len(self._widths) - 1

            # Text kuerzen bis er in die Spalte passt
            max_w = width - 3
            while val and pdf.get_string_width(val) > max_w:
                val = val[:-1]
                if not val:
                    break
                val_display = val + "\u2026"
            else:
                val_display = val

            if is_last_col and bold_last and val_display:
                pdf.set_font(*self._font("B", 8))

            align = "R" if is_right else "L"
            pdf.cell(width, row_height, val_display, border="LR", align=align)

            if is_last_col and bold_last:
                pdf.set_font(*self._font("", 8))

            x += width

        pdf.set_xy(left, y + row_height)
