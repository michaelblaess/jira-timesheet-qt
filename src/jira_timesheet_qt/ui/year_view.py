"""Jahresansicht: zwoelf Monatskacheln mit Summen und Auslastung.

In der TUI war das ein eigener Vollbild-Dialog, weil nichts anderes danebenpasste.
Hier ist es eine Ansicht wie jede andere - der Wechsel kostet einen Klick, und
die Auswahl eines Monats fuehrt direkt in die Liste.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.ui.theme import Mode, Palette, palette_for

_MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


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
class MonthCell:
    """Kennzahlen eines Monats."""

    month: int
    hours: float = 0.0
    target: float = 0.0
    entries: int = 0

    @property
    def ratio(self) -> float:
        """Anteil der gebuchten an den Sollstunden, hoechstens 1."""
        return min(1.0, self.hours / self.target) if self.target > 0 else 0.0

    @property
    def has_data(self) -> bool:
        """True, wenn fuer den Monat Buchungen vorliegen."""
        return self.entries > 0


@dataclass
class YearSummary:
    """Kennzahlen ueber das ganze Jahr."""

    actual: float    # Ist gesamt (Summe der gebuchten Stunden)
    target: float    # Soll gesamt (Arbeitstage x Stunden/Tag ueber alle Monate)
    forecast: float  # Hochrechnung: Ist der abgelaufenen + Soll der Restmonate


def compute_year_summary(cells: list[MonthCell], elapsed_through_month: int) -> YearSummary:
    """Berechnet Ist, Soll und die Jahresend-Hochrechnung.

    Die Hochrechnung ist bewusst transparent und ohne Annahmen ueber den
    Verlauf: fuer die bereits abgelaufenen Monate (bis einschliesslich
    elapsed_through_month) zaehlt das tatsaechlich Gebuchte, fuer die noch
    offenen Monate das Soll - also "wenn der Rest des Jahres das Soll trifft".

    Args:
        cells:
            Die zwoelf Monatskacheln mit Ist- und Sollstunden.
        elapsed_through_month:
            Letzter als abgelaufen zaehlender Monat (1-12). 0 = ganzes Jahr
            liegt in der Zukunft (nur Soll), 12 = ganzes Jahr abgelaufen.

    Returns:
        Die Jahres-Kennzahlen.
    """
    actual = sum(cell.hours for cell in cells)
    target = sum(cell.target for cell in cells)
    forecast = sum(
        cell.hours if cell.month <= elapsed_through_month else cell.target for cell in cells
    )
    return YearSummary(actual=actual, target=target, forecast=forecast)


class YearView(QWidget):
    """Zwoelf Monatskacheln in drei Reihen."""

    month_selected = Signal(int)

    COLUMNS = 4
    PADDING = 16
    GAP = 10
    SUMMARY_H = 46  # Kopfstreifen fuer Ist/Soll/Prognose

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._year = date.today().year
        self._cells: list[MonthCell] = [MonthCell(m) for m in range(1, 13)]
        self._summary = YearSummary(0.0, 0.0, 0.0)
        self.setMinimumHeight(400)

    # --- Inhalte --------------------------------------------------------

    def set_year(
        self,
        year: int,
        hours_by_month: dict[int, float],
        entries_by_month: dict[int, int],
        hours_per_day: float = 8.0,
        federal_state: str = "SN",
    ) -> None:
        """Uebernimmt die Summen eines Jahres."""
        self._year = year
        holidays = HolidayService(federal_state)
        self._cells = []
        for month in range(1, 13):
            first = date(year, month, 1)
            last = date(year, month, _days_in_month(year, month))
            self._cells.append(
                MonthCell(
                    month=month,
                    hours=hours_by_month.get(month, 0.0),
                    target=holidays.count_workdays(first, last) * hours_per_day,
                    entries=entries_by_month.get(month, 0),
                )
            )
        self._summary = compute_year_summary(self._cells, self._elapsed_month())
        self.update()

    def _elapsed_month(self) -> int:
        """Bis zu welchem Monat gilt das Jahr als abgelaufen (fuer die Prognose)."""
        today = date.today()
        if self._year < today.year:
            return 12
        if self._year > today.year:
            return 0
        return today.month

    @property
    def summary(self) -> YearSummary:
        """Die Jahres-Kennzahlen (Ist, Soll, Prognose)."""
        return self._summary

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        self.update()

    @property
    def cells(self) -> list[MonthCell]:
        """Die zwoelf Monatskacheln."""
        return self._cells

    @property
    def total_hours(self) -> float:
        """Summe ueber das ganze Jahr."""
        return sum(cell.hours for cell in self._cells)

    # --- Zeichnen -------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p = palette_for(self._mode)
        painter.fillRect(self.rect(), QColor(p.bg_primary))

        self._paint_summary(painter, p)
        for index, cell in enumerate(self._cells):
            self._paint_cell(painter, self._rect_for(index), cell)
        painter.end()

    def _paint_summary(self, painter: QPainter, p: Palette) -> None:
        """Zeichnet den Kopfstreifen mit Jahr, Ist, Soll und Prognose."""
        top = float(self.PADDING)
        height = float(self.SUMMARY_H - self.GAP)
        right = float(self.width() - self.PADDING)
        x = float(self.PADDING)

        # Jahreszahl in der Akzentfarbe.
        x = self._draw_text(painter, x, top, height, right, str(self._year),
                            scaled_font(self.font(), 3, bold=True), p.accent) + 18.0

        summary = self._summary
        for label, value in (
            ("Ist", summary.actual),
            ("Soll", summary.target),
            ("Prognose", summary.forecast),
        ):
            x = self._draw_text(painter, x, top, height, right, label,
                                scaled_font(self.font(), 0), p.text_tertiary) + 5.0
            x = self._draw_text(painter, x, top, height, right, f"{value:.2f} h".replace(".", ","),
                                scaled_font(self.font(), 3, bold=True), p.text_primary) + 20.0

    def _draw_text(
        self, painter: QPainter, x: float, top: float, height: float, right: float,
        text: str, font: QFont, color: str,
    ) -> float:
        """Zeichnet Text ab x (vertikal zentriert) und liefert das rechte Ende."""
        painter.setFont(font)
        painter.setPen(QColor(color))
        rect = QRectF(x, top, max(0.0, right - x), height)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        return x + QFontMetrics(font).horizontalAdvance(text)

    def _rect_for(self, index: int) -> QRectF:
        """Platz einer Monatskachel."""
        rows = 12 // self.COLUMNS
        area = self.rect().adjusted(
            self.PADDING, self.PADDING + self.SUMMARY_H, -self.PADDING, -self.PADDING
        )
        cell_w = (area.width() - self.GAP * (self.COLUMNS - 1)) / self.COLUMNS
        cell_h = (area.height() - self.GAP * (rows - 1)) / rows
        column, row = index % self.COLUMNS, index // self.COLUMNS
        return QRectF(
            area.x() + column * (cell_w + self.GAP),
            area.y() + row * (cell_h + self.GAP),
            cell_w,
            cell_h,
        )

    def _paint_cell(self, painter: QPainter, rect: QRectF, cell: MonthCell) -> None:
        """Zeichnet eine Monatskachel mit Balken."""
        p = palette_for(self._mode)
        today = date.today()
        current = self._year == today.year and cell.month == today.month

        painter.setBrush(QColor(p.bg_tertiary if cell.has_data else p.bg_secondary))
        painter.setPen(QColor(p.accent if current else p.border))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setFont(scaled_font(self.font(), 0, bold=True))
        painter.setPen(QColor(p.text_primary if cell.has_data else p.text_tertiary))
        painter.drawText(
            rect.adjusted(14, 10, -14, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            _MONTHS[cell.month - 1],
        )

        # Stundensumme
        painter.setFont(scaled_font(self.font(), 6, bold=True))
        painter.setPen(QColor(p.text_primary if cell.has_data else p.text_tertiary))
        painter.drawText(
            rect.adjusted(14, 32, -14, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            f"{cell.hours:.2f} h".replace(".", ","),
        )

        # Sollwert
        painter.setFont(scaled_font(self.font(), -2))
        painter.setPen(QColor(p.text_tertiary))
        painter.drawText(
            rect.adjusted(14, 62, -14, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            f"von {cell.target:.0f} h Soll",
        )

        # Auslastungsbalken am unteren Rand
        bar_area = QRectF(rect.x() + 14, rect.bottom() - 20, rect.width() - 28, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.border))
        painter.drawRoundedRect(bar_area, 3, 3)
        if cell.ratio > 0:
            filled = QRectF(bar_area)
            filled.setWidth(bar_area.width() * cell.ratio)
            painter.setBrush(QColor(p.green if cell.ratio >= 0.98 else p.accent))
            painter.drawRoundedRect(filled, 3, 3)

    # --- Auswahl --------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        for index in range(12):
            if self._rect_for(index).contains(event.position()):
                self.month_selected.emit(index + 1)
                return


def _days_in_month(year: int, month: int) -> int:
    """Anzahl der Tage eines Monats."""
    import calendar

    return calendar.monthrange(year, month)[1]
