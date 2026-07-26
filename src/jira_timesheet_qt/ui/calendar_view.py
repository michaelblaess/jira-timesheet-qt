"""Monatsansicht als Kachelraster.

Zeigt den Monat als Wochenzeilen mit einer Kachel je Tag: Stunden, Anzahl der
Eintraege und die Vorgangsschluessel. Feiertage und Wochenenden sind abgesetzt,
Arbeitstage ohne Buchung fallen dadurch sofort auf - genau dafuer ist die
Ansicht da.

Gezeichnet wird selbst (paintEvent), nicht aus Widgets zusammengesetzt: bei
sechs Wochen mal sieben Tagen waeren das 42 Widgets, die bei jeder
Groessenaenderung neu vermessen werden muessten.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.ui.theme import Mode, palette_for

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def scaled_font(base: QFont, delta: int = 0, bold: bool = False) -> QFont:
    """Liefert eine Schrift mit veraenderter Groesse.

    Das Stylesheet setzt die Groesse in Pixeln. Dann ist pointSizeF() gleich
    -1, und jede Rechnung darauf ergibt eine unsichtbar kleine Schrift - genau
    das hat die Stundenzahlen im Kalender verschluckt. Deshalb zuerst
    pixelSize() abfragen und nur ersatzweise auf Punkt ausweichen.
    """
    font = QFont(base)
    font.setBold(bold)
    if base.pixelSize() > 0:
        font.setPixelSize(max(7, base.pixelSize() + delta))
    else:
        font.setPointSizeF(max(6.0, base.pointSizeF() + delta))
    return font



@dataclass
class DayCell:
    """Ein Tag im Raster."""

    day: date
    in_month: bool
    hours: float = 0.0
    entries: list[WorklogEntry] = field(default_factory=list)
    holiday: str = ""

    @property
    def is_weekend(self) -> bool:
        """True fuer Samstag und Sonntag."""
        return self.day.weekday() >= 5

    @property
    def is_workday(self) -> bool:
        """True fuer Arbeitstage ohne Feiertag."""
        return not self.is_weekend and not self.holiday


class CalendarView(QWidget):
    """Monatsraster mit den Buchungen eines Stundenzettels."""

    day_selected = Signal(object)

    HEADER_HEIGHT = 26
    PADDING = 14

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._cells: list[DayCell] = []
        self._year = date.today().year
        self._month = date.today().month
        self._selected: date | None = None
        self.setMinimumHeight(360)
        self.setMouseTracking(True)

    # --- Inhalte --------------------------------------------------------

    def set_month(
        self,
        year: int,
        month: int,
        timesheet: Timesheet | None,
        federal_state: str = "SN",
    ) -> None:
        """Baut das Raster fuer einen Monat auf."""
        self._year, self._month = year, month
        holidays = HolidayService(federal_state)

        by_day: dict[date, list[WorklogEntry]] = {}
        if timesheet is not None:
            for entry in timesheet.all_entries:
                by_day.setdefault(entry.date, []).append(entry)

        self._cells = []
        for day in _grid_days(year, month):
            entries = by_day.get(day, [])
            self._cells.append(
                DayCell(
                    day=day,
                    in_month=day.month == month,
                    hours=sum(e.hours for e in entries),
                    entries=entries,
                    holiday=holidays.get_holiday_name(day),
                )
            )
        self.update()

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        self.update()

    @property
    def cells(self) -> list[DayCell]:
        """Alle Kacheln des Rasters."""
        return self._cells

    def missing_workdays(self) -> list[DayCell]:
        """Arbeitstage des Monats ohne Buchung."""
        return [c for c in self._cells if c.in_month and c.is_workday and c.hours == 0.0]

    # --- Zeichnen -------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p = palette_for(self._mode)
        painter.fillRect(self.rect(), QColor(p.bg_primary))

        if not self._cells:
            painter.end()
            return

        rows = len(self._cells) // 7
        area = self.rect().adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        cell_w = area.width() / 7
        cell_h = (area.height() - self.HEADER_HEIGHT) / max(1, rows)

        self._paint_header(painter, area.x(), area.y(), cell_w)

        for index, cell in enumerate(self._cells):
            column, row = index % 7, index // 7
            rect = QRectF(
                area.x() + column * cell_w,
                area.y() + self.HEADER_HEIGHT + row * cell_h,
                cell_w - 4,
                cell_h - 4,
            )
            self._paint_cell(painter, rect, cell)
        painter.end()

    def _paint_header(self, painter: QPainter, x: float, y: float, cell_w: float) -> None:
        """Zeichnet die Wochentagsleiste."""
        p = palette_for(self._mode)
        painter.setFont(scaled_font(self.font(), -2, bold=True))
        painter.setPen(QColor(p.text_tertiary))
        for column, name in enumerate(_WEEKDAYS):
            rect = QRectF(x + column * cell_w, y, cell_w - 4, self.HEADER_HEIGHT)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), f" {name}")

    def _paint_cell(self, painter: QPainter, rect: QRectF, cell: DayCell) -> None:
        """Zeichnet eine Tageskachel."""
        p = palette_for(self._mode)
        today = date.today()

        if not cell.in_month:
            background = QColor(p.bg_primary)
        elif cell.holiday or cell.is_weekend:
            background = QColor(p.bg_secondary)
        else:
            background = QColor(p.bg_tertiary)
        painter.setBrush(background)

        border = QColor(p.border)
        if cell.day == self._selected:
            border = QColor(p.accent)
        elif cell.in_month and cell.is_workday and cell.hours == 0.0:
            # Arbeitstag ohne Buchung - der Grund fuer diese Ansicht.
            border = QColor(p.orange)
        painter.setPen(border)
        painter.drawRoundedRect(rect, 8, 8)

        if not cell.in_month:
            return

        # Tageszahl
        painter.setFont(scaled_font(self.font(), 0, bold=cell.day == today))
        painter.setPen(QColor(p.accent_hover if cell.day == today else p.text_secondary))
        painter.drawText(
            rect.adjusted(8, 5, -8, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            str(cell.day.day),
        )

        # Stunden
        if cell.hours > 0:
            painter.setFont(scaled_font(self.font(), 2, bold=True))
            painter.setPen(QColor(p.text_primary))
            painter.drawText(
                rect.adjusted(8, 5, -8, 0),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop),
                f"{cell.hours:.2f}".replace(".", ","),
            )

        # Vorgaenge oder Feiertagsname
        painter.setFont(scaled_font(self.font(), -2))
        painter.setPen(QColor(p.text_tertiary))
        detail = cell.holiday if cell.holiday else ", ".join(dict.fromkeys(e.ticket for e in cell.entries))
        if detail:
            painter.drawText(
                rect.adjusted(8, 26, -8, -6),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                detail,
            )

    # --- Auswahl --------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        cell = self._cell_at(event.position().x(), event.position().y())
        if cell is not None and cell.in_month:
            self._selected = cell.day
            self.update()
            self.day_selected.emit(cell)

    def _cell_at(self, x: float, y: float) -> DayCell | None:
        """Findet die Kachel unter einem Punkt."""
        if not self._cells:
            return None
        rows = len(self._cells) // 7
        area = self.rect().adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        cell_w = area.width() / 7
        cell_h = (area.height() - self.HEADER_HEIGHT) / max(1, rows)

        column = int((x - area.x()) // cell_w)
        row = int((y - area.y() - self.HEADER_HEIGHT) // cell_h)
        if not (0 <= column < 7 and 0 <= row < rows):
            return None
        index = row * 7 + column
        return self._cells[index] if 0 <= index < len(self._cells) else None


def _grid_days(year: int, month: int) -> list[date]:
    """Alle Tage des Rasters, von Montag der ersten bis Sonntag der letzten Woche."""
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    return [day for week in weeks for day in week]
