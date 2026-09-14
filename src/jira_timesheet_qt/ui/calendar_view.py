"""Monatsansicht als Kachelraster.

Zeigt den Monat als Wochenzeilen mit einer Kachel je Tag: oben Tag und
Stunden, darunter ein Balken Ist gegen Soll und eine Zeile je Ticket mit
Beschreibung und Stunden. Feiertage und Wochenenden sind abgesetzt,
vergangene Arbeitstage ohne Buchung fallen sofort auf - genau dafuer ist die
Ansicht da. Heute und die kommenden Tage bleiben neutral, dort kann noch
nichts fehlen.

Gezeichnet wird selbst (paintEvent), nicht aus Widgets zusammengesetzt: bei
sechs Wochen mal sieben Tagen waeren das 42 Widgets, die bei jeder
Groessenaenderung neu vermessen werden muessten.
"""

from __future__ import annotations

import calendar
import html
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QHelpEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.ui.theme import Mode, Palette, palette_for

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


def format_hours(hours: float) -> str:
    """Stunden mit zwei Nachkommastellen und Komma, ohne Einheit."""
    return f"{hours:.2f}".replace(".", ",")


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


class DayState(Enum):
    """Wie eine Kachel auftritt - abgeleitet aus Datum, Buchungen und Feiertag."""

    OUTSIDE = "outside"
    FREE = "free"
    FUTURE = "future"
    UNKNOWN = "unknown"
    TODAY = "today"
    MISSING = "missing"
    BOOKED = "booked"


def day_state(cell: DayCell, today: date, known: bool = True) -> DayState:
    """Ordnet einen Tag ein.

    Fehlen kann nur ein vergangener Arbeitstag. Heute und die kommenden Tage
    sind noch offen - bis 09/2026 waren sie rot umrandet, obwohl dort noch
    niemand buchen konnte.

    Args:
        cell:
            Der Tag im Raster.
        today:
            Der Stichtag. Von aussen hereingegeben, damit Tests nicht am
            Kalender haengen.
        known:
            Ob die Buchungen des Monats vorliegen. Solange sie laden oder der
            Abruf gescheitert ist, kann kein Tag als fehlend gelten - bis
            09/2026 blitzte dann jeder vergangene Tag rot auf.
    """
    if not cell.in_month:
        return DayState.OUTSIDE
    if not cell.is_workday:
        return DayState.FREE
    if cell.day == today:
        return DayState.TODAY
    if cell.day > today:
        return DayState.FUTURE
    if not known:
        return DayState.UNKNOWN
    return DayState.BOOKED if cell.hours > 0 else DayState.MISSING


@dataclass
class TicketRow:
    """Alle Buchungen eines Tages auf ein Ticket, zusammengefasst."""

    ticket: str
    summary: str
    hours: float
    # Der erste Eintrag des Tickets - ihn oeffnet ein Klick auf die Nummer.
    entry: WorklogEntry
    manual: bool


def ticket_rows(entries: list[WorklogEntry]) -> list[TicketRow]:
    """Fasst die Buchungen eines Tages je Ticket zusammen, die groessten zuerst.

    Eintraege ohne Ticketnummer (manuell erfasst) werden nach ihrer
    Beschreibung zusammengefasst - sonst fielen sie aus der Kachel.
    """
    rows: dict[str, TicketRow] = {}
    for entry in entries:
        key = entry.ticket if entry.ticket else f"\0{entry.summary}"
        row = rows.get(key)
        if row is None:
            rows[key] = TicketRow(entry.ticket, entry.summary, entry.hours, entry, entry.manual)
            continue
        row.hours += entry.hours
        row.manual = row.manual or entry.manual
    return sorted(rows.values(), key=lambda row: (-row.hours, row.ticket))


def split_rows(rows: list[TicketRow], capacity: int) -> tuple[list[TicketRow], list[TicketRow]]:
    """Teilt die Zeilen in sichtbare und zusammengefasste.

    Passen nicht alle, bleibt die letzte Zeile fuer "+ N weitere" frei - mit
    deren Stunden, damit die Summe der Kachel nachvollziehbar bleibt.

    Returns:
        (sichtbare Zeilen, zusammengefasste Zeilen).
    """
    if capacity <= 0:
        return [], list(rows)
    if len(rows) <= capacity:
        return list(rows), []
    return list(rows[: capacity - 1]), list(rows[capacity - 1 :])


def bar_fractions(hours: float, target: float) -> tuple[float, float]:
    """Anteile des Balkens Ist gegen Soll.

    Die Schiene reicht bis zum groesseren von Ist und Soll. Bis zum Soll wird
    in der Ampelfarbe gefuellt, was darueber liegt, laeuft als Ueberstunden
    in der Akzentfarbe weiter.

    Returns:
        (Anteil bis zum Soll, Anteil der Ueberstunden), beide bezogen auf die
        volle Balkenbreite.
    """
    if hours <= 0 or target <= 0:
        return 0.0, 0.0
    scale = max(hours, target)
    return min(hours, target) / scale, max(0.0, hours - target) / scale


def tooltip_html(cell: DayCell, target_hours: float) -> str:
    """Hinweistext einer Kachel: Datum, Stunden gegen Soll und alle Eintraege.

    Als HTML, damit die Eintraege als Tabelle ausgerichtet stehen. Alle Texte
    aus Jira laufen durch html.escape - eine Beschreibung mit spitzen
    Klammern zerlegte sonst das Markup.

    Returns:
        Der Text, oder "" fuer Tage ausserhalb des Monats.
    """
    if not cell.in_month:
        return ""
    lines = [f"<b>{_WEEKDAYS[cell.day.weekday()]}, {cell.day:%d.%m.%Y}</b>"]
    if cell.holiday:
        lines.append(html.escape(cell.holiday))
    if cell.is_workday:
        lines.append(f"{format_hours(cell.hours)} h von {format_hours(target_hours)} h")
    elif cell.hours > 0:
        lines.append(f"{format_hours(cell.hours)} h")
    if not cell.entries:
        lines.append("Keine Buchung")
        return "<br>".join(lines)

    table = ["<table cellspacing='0' cellpadding='2'>"]
    for entry in sorted(cell.entries, key=lambda item: (-item.hours, item.ticket)):
        details = html.escape(entry.summary)
        if entry.customer:
            details += f" ({html.escape(entry.customer)})"
        if entry.manual:
            details += " - manuell"
        table.append(
            f"<tr><td>{html.escape(entry.ticket)}</td><td>{details}</td>"
            f"<td align='right'>{format_hours(entry.hours)}</td></tr>"
        )
    table.append("</table>")
    return "<br>".join(lines) + "".join(table)


class CalendarView(QWidget):
    """Monatsraster mit den Buchungen eines Stundenzettels."""

    day_selected = Signal(object)
    day_activated = Signal(object)
    # Klick auf eine Ticketnummer in der Kachel - meldet den Eintrag zur Detailanzeige.
    ticket_activated = Signal(object)

    HEADER_HEIGHT = 26
    PADDING = 14
    # Breite der Wochensummen-Spalte rechts (KW, Wochenstunden, Soll und Balken).
    SUMMARY_WIDTH = 104
    # Abstand zwischen Nummer, Beschreibung und Stunden einer Ticketzeile.
    GAP = 8
    # Schmaler als das lohnt keine Beschreibung mehr - dann faellt sie weg.
    MIN_SUMMARY_WIDTH = 60
    BAR_HEIGHT = 4

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._cells: list[DayCell] = []
        self._year = date.today().year
        self._month = date.today().month
        self._selected: date | None = None
        # Soll-Stunden je Arbeitstag - Grundlage der Farbkodierung der Tage.
        self._target_hours = 8.0
        # Farbe manueller Eintraege aus den Einstellungen, None = nicht hervorheben.
        self._manual_color: QColor | None = None
        # Ob die Buchungen des gezeigten Monats vorliegen (siehe day_state).
        self._has_data = False
        # Trefferflaechen der gezeichneten Ticketnummern (fuer Hover/Klick), je
        # (Rechteck, Eintrag). Wird bei jedem paintEvent neu aufgebaut.
        self._ticket_hits: list[tuple[QRectF, WorklogEntry]] = []
        self._hovered_ticket: WorklogEntry | None = None
        self.setMinimumHeight(360)
        self.setMouseTracking(True)

    # --- Inhalte --------------------------------------------------------

    def set_month(
        self,
        year: int,
        month: int,
        timesheet: Timesheet | None,
        federal_state: str = "SN",
        hours_per_day: float = 8.0,
    ) -> None:
        """Baut das Raster fuer einen Monat auf."""
        self._year, self._month = year, month
        self._target_hours = hours_per_day if hours_per_day > 0 else 8.0
        # Der zuletzt ueberfahrene Eintrag gehoert zum alten Monat - verwerfen.
        self._hovered_ticket = None
        # Ohne Stundenzettel ist offen, was gebucht ist - dann fehlt auch nichts.
        self._has_data = timesheet is not None
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

    def set_manual_color(self, color: QColor | None) -> None:
        """Faerbt die Ticketzeilen manuell erfasster Eintraege, None schaltet es ab."""
        self._manual_color = color
        self.update()

    @property
    def cells(self) -> list[DayCell]:
        """Alle Kacheln des Rasters."""
        return self._cells

    def missing_workdays(self, today: date | None = None) -> list[DayCell]:
        """Vergangene Arbeitstage des Monats ohne Buchung.

        Heute und die kommenden Tage zaehlen nicht - dort kann noch nichts fehlen.
        Solange keine Buchungen vorliegen, ist die Liste leer.
        """
        stichtag = today if today is not None else date.today()
        return [c for c in self._cells if day_state(c, stichtag, self._has_data) is DayState.MISSING]

    def week_summaries(self) -> list[tuple[int, float]]:
        """Je Rasterzeile die Kalenderwoche und die Summe ihrer Stunden.

        Returns:
            Liste aus (KW-Nummer, Wochenstunden) - eine je Zeile, von oben nach
            unten. Jede Zeile ist eine volle ISO-Woche (Montag bis Sonntag).
        """
        rows = len(self._cells) // 7
        summaries: list[tuple[int, float]] = []
        for row in range(rows):
            week = self._cells[row * 7 : row * 7 + 7]
            kw = week[0].day.isocalendar().week
            summaries.append((kw, sum(cell.hours for cell in week)))
        return summaries

    def week_targets(self) -> list[float]:
        """Je Rasterzeile das Soll: Arbeitstage dieses Monats in der Woche mal Tagessoll.

        Tage des Nachbarmonats zaehlen nicht mit - deren Stunden stehen auch
        nicht in der Wochensumme.
        """
        rows = len(self._cells) // 7
        return [
            sum(self._target_hours for cell in self._cells[row * 7 : row * 7 + 7] if cell.in_month and cell.is_workday)
            for row in range(rows)
        ]

    # --- Zeichnen -------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p = palette_for(self._mode)
        painter.fillRect(self.rect(), QColor(p.bg_primary))

        if not self._cells:
            painter.end()
            return

        area, cell_w, cell_h, rows = self._geometry()
        today = date.today()

        # Trefferflaechen der Ticketnummern bei jedem Zeichnen neu aufbauen.
        self._ticket_hits = []

        self._paint_header(painter, area.x(), area.y(), cell_w)

        for index, cell in enumerate(self._cells):
            column, row = index % 7, index // 7
            rect = QRectF(
                area.x() + column * cell_w,
                area.y() + self.HEADER_HEIGHT + row * cell_h,
                cell_w - 4,
                cell_h - 4,
            )
            self._paint_cell(painter, rect, cell, today)

        # Wochensummen-Spalte rechts.
        summary_x = area.x() + 7 * cell_w
        weeks = zip(self.week_summaries(), self.week_targets(), strict=True)
        for row, ((kw, total), target) in enumerate(weeks):
            rect = QRectF(
                summary_x,
                area.y() + self.HEADER_HEIGHT + row * cell_h,
                self.SUMMARY_WIDTH - 4,
                cell_h - 4,
            )
            self._paint_summary(painter, rect, kw, total, target)
        painter.end()

    def _geometry(self) -> tuple[QRectF, float, float, int]:
        """Liefert Zeichenflaeche, Tagesbreite, Zeilenhoehe und Zeilenzahl.

        Die Wochensummen-Spalte rechts belegt SUMMARY_WIDTH, die sieben Tage
        teilen sich den Rest. Paint und Trefferpruefung nutzen dieselbe Rechnung.
        """
        rows = len(self._cells) // 7
        area = QRectF(self.rect().adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING))
        cell_w = (area.width() - self.SUMMARY_WIDTH) / 7
        cell_h = (area.height() - self.HEADER_HEIGHT) / max(1, rows)
        return area, cell_w, cell_h, rows

    def _paint_header(self, painter: QPainter, x: float, y: float, cell_w: float) -> None:
        """Zeichnet die Wochentagsleiste samt Kopf der Wochensummen-Spalte."""
        p = palette_for(self._mode)
        painter.setFont(scaled_font(self.font(), -2, bold=True))
        painter.setPen(QColor(p.text_tertiary))
        for column, name in enumerate(_WEEKDAYS):
            rect = QRectF(x + column * cell_w, y, cell_w - 4, self.HEADER_HEIGHT)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), f" {name}")
        summary_rect = QRectF(x + 7 * cell_w, y, self.SUMMARY_WIDTH - 4, self.HEADER_HEIGHT)
        painter.drawText(summary_rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), "Σ h")

    def _paint_summary(self, painter: QPainter, rect: QRectF, kw: int, total: float, target: float) -> None:
        """Zeichnet eine Wochensummen-Kachel: KW, Stunden, Soll der Woche und Balken."""
        p = palette_for(self._mode)
        painter.setBrush(QColor(p.bg_secondary))
        painter.setPen(QColor(p.border))
        painter.drawRoundedRect(rect, 8, 8)

        inner = rect.adjusted(8, 6, -8, -6)
        right_top = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        small = scaled_font(self.font(), -3, bold=True)
        painter.setFont(small)
        painter.setPen(QColor(p.text_tertiary))
        painter.drawText(inner, right_top, f"KW {kw}")
        y = inner.y() + QFontMetricsF(small).height() + 2

        if total <= 0 and target <= 0:
            return

        big = scaled_font(self.font(), 1, bold=True)
        painter.setFont(big)
        painter.setPen(QColor(p.green if target > 0 and total + 1e-6 >= target else p.text_secondary))
        painter.drawText(QRectF(inner.x(), y, inner.width(), inner.bottom() - y), right_top, f"{format_hours(total)} h")
        y += QFontMetricsF(big).height() + 1

        if target <= 0:
            return
        hint = scaled_font(self.font(), -3)
        painter.setFont(hint)
        painter.setPen(QColor(p.text_tertiary))
        painter.drawText(QRectF(inner.x(), y, inner.width(), inner.bottom() - y), right_top, f"von {format_hours(target)} h")
        y += QFontMetricsF(hint).height() + 4

        if y + self.BAR_HEIGHT <= inner.bottom():
            fill = QColor(p.green if total + 1e-6 >= target else p.orange)
            self._paint_bar(painter, QRectF(inner.x(), y, inner.width(), self.BAR_HEIGHT), total, target, fill, p)

    def _paint_bar(
        self, painter: QPainter, rect: QRectF, hours: float, target: float, fill: QColor, p: Palette
    ) -> None:
        """Zeichnet einen Balken Ist gegen Soll samt Ueberstunden (siehe bar_fractions)."""
        radius = rect.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.border))
        painter.drawRoundedRect(rect, radius, radius)

        regular, overtime = bar_fractions(hours, target)
        if regular <= 0:
            return
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * regular, rect.height()), radius, radius)
        if overtime > 0:
            start = rect.x() + rect.width() * regular
            painter.setBrush(QColor(p.accent))
            painter.drawRoundedRect(QRectF(start, rect.y(), rect.width() * overtime, rect.height()), radius, radius)
            # Marke dort, wo das Soll endete.
            painter.setBrush(QColor(p.text_primary))
            painter.drawRect(QRectF(start - 1, rect.y() - 2, 2, rect.height() + 4))

    def _paint_cell(self, painter: QPainter, rect: QRectF, cell: DayCell, today: date) -> None:
        """Zeichnet eine Tageskachel."""
        p = palette_for(self._mode)
        state = day_state(cell, today, self._has_data)

        background = QColor(p.bg_tertiary)
        if state is DayState.OUTSIDE:
            background = QColor(p.bg_primary)
        elif state is DayState.FREE:
            background = QColor(p.bg_secondary)

        border = QPen(QColor(p.border), 1)
        if cell.in_month and cell.day == self._selected:
            border = QPen(QColor(p.accent), 2)
        elif state is DayState.TODAY:
            border = QPen(QColor(p.accent_hover), 2)
        elif state is DayState.MISSING:
            # Vergangener Arbeitstag ohne Buchung - der Grund fuer diese Ansicht.
            border = QPen(QColor(p.red), 1)
        elif cell.in_month and cell.holiday:
            border = QPen(QColor(p.purple), 1)
        painter.setPen(border)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 8, 8)

        # Fehlende Tage leicht rot, Feiertage leicht violett getoent - beide
        # sollen beim Ueberfliegen des Monats auffallen, ohne zu schreien.
        tint_color = p.red if state is DayState.MISSING else p.purple if cell.in_month and cell.holiday else ""
        if tint_color:
            tint = QColor(tint_color)
            tint.setAlpha(28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            painter.drawRoundedRect(rect, 8, 8)

        if state is DayState.OUTSIDE:
            return

        inner = rect.adjusted(8, 5, -8, -6)
        left_top = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        right_top = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        # Tageszahl - genauso gross wie die Stundenzahl (beide +2), oben ausgerichtet.
        head_font = scaled_font(self.font(), 2, bold=state is DayState.TODAY)
        painter.setFont(head_font)
        painter.setPen(QColor(p.accent_hover if state is DayState.TODAY else p.text_secondary))
        painter.drawText(inner, left_top, str(cell.day.day))

        if cell.hours > 0:
            painter.setFont(scaled_font(self.font(), 2, bold=True))
            painter.setPen(self._hours_color(cell, p))
            painter.drawText(inner, right_top, f"{format_hours(cell.hours)} h")
        elif state is DayState.MISSING:
            painter.setFont(scaled_font(self.font(), 0, bold=True))
            painter.setPen(QColor(p.red))
            painter.drawText(inner, right_top, "fehlt")

        # Die Balkenzeile ist immer reserviert, damit die Ticketzeilen aller
        # Kacheln einer Woche auf gleicher Hoehe beginnen.
        y = inner.y() + QFontMetricsF(head_font).height() + 4
        if cell.is_workday and (cell.hours > 0 or state not in (DayState.FUTURE, DayState.UNKNOWN)):
            bar = QRectF(inner.x(), y, inner.width(), self.BAR_HEIGHT)
            self._paint_bar(painter, bar, cell.hours, self._target_hours, self._hours_color(cell, p), p)
        y += self.BAR_HEIGHT + 8

        area = QRectF(inner.x(), y, inner.width(), max(0.0, inner.bottom() - y))
        if cell.holiday:
            font = scaled_font(self.font(), -1, bold=True)
            metrics = QFontMetricsF(font)
            painter.setFont(font)
            painter.setPen(QColor(p.purple))
            name = metrics.elidedText(cell.holiday, Qt.TextElideMode.ElideRight, area.width())
            painter.drawText(QPointF(area.x(), area.y() + metrics.ascent()), name)
            area.setTop(min(area.bottom(), area.top() + metrics.height() + 4))

        self._paint_rows(painter, area, cell, p)

    def _hours_color(self, cell: DayCell, p: Palette) -> QColor:
        """Farbe der Tagesstunden: gruen ab Soll, orange darunter, sonst neutral."""
        if not cell.is_workday:
            return QColor(p.text_primary)
        if cell.hours + 1e-6 >= self._target_hours:
            return QColor(p.green)
        return QColor(p.orange)

    def _paint_rows(self, painter: QPainter, area: QRectF, cell: DayCell, p: Palette) -> None:
        """Zeichnet eine Zeile je Ticket: Nummer, Beschreibung, Stunden.

        Die Kachel passt sich ihrer Breite an. Reicht der Platz nicht fuer die
        Beschreibung, faellt sie weg. Reicht er nicht einmal fuer Nummer und
        Stunden, bleiben die Nummern als Fliesstext. Was in der Hoehe nicht
        passt, fasst die letzte Zeile als "+ N weitere" zusammen.
        """
        rows = ticket_rows(cell.entries)
        if not rows or area.height() <= 0:
            return

        font = scaled_font(self.font(), -1)
        metrics = QFontMetricsF(font)
        hours_w = metrics.horizontalAdvance("00,00")
        ticket_w = max((metrics.horizontalAdvance(row.ticket) for row in rows if row.ticket), default=0.0)
        if area.width() < ticket_w + self.GAP + hours_w:
            self._paint_ticket_flow(painter, area, rows, p)
            return
        show_summary = area.width() >= ticket_w + hours_w + 2 * self.GAP + self.MIN_SUMMARY_WIDTH

        line_h = metrics.height() + 2
        visible, rest = split_rows(rows, int(area.height() // line_h))
        if not visible and not rest:
            return

        y = area.y()
        for row in visible:
            line = QRectF(area.x(), y, area.width(), line_h)
            self._paint_row(painter, line, row, ticket_w, hours_w, show_summary, font, p)
            y += line_h

        if rest and y + line_h <= area.bottom() + 1:
            painter.setFont(font)
            painter.setPen(QColor(p.text_tertiary))
            align_left = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            align_right = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            painter.drawText(QRectF(area.x(), y, area.width(), line_h), align_left, f"+ {len(rest)} weitere")
            painter.drawText(
                QRectF(area.x(), y, area.width(), line_h), align_right, format_hours(sum(row.hours for row in rest))
            )

    def _paint_row(
        self,
        painter: QPainter,
        line: QRectF,
        row: TicketRow,
        ticket_w: float,
        hours_w: float,
        show_summary: bool,
        font: QFont,
        p: Palette,
    ) -> None:
        """Zeichnet eine Ticketzeile und merkt sich die Trefferflaeche der Nummer."""
        metrics = QFontMetricsF(font)
        baseline = line.y() + (line.height() - metrics.height()) / 2 + metrics.ascent()
        manual_color = self._manual_color if row.manual else None
        text_color = manual_color if manual_color is not None else QColor(p.text_secondary)
        summary_color = manual_color if manual_color is not None else QColor(p.text_tertiary)

        summary_left = line.x()
        if row.ticket:
            hovered = self._hovered_ticket is row.entry
            token_font = QFont(font)
            token_font.setUnderline(hovered)
            painter.setFont(token_font)
            painter.setPen(QColor(p.accent) if hovered else text_color)
            painter.drawText(QPointF(line.x(), baseline), row.ticket)
            width = metrics.horizontalAdvance(row.ticket)
            self._ticket_hits.append((QRectF(line.x(), line.y(), width, line.height()), row.entry))
            summary_left = line.x() + ticket_w + self.GAP

        painter.setFont(font)
        hours_left = line.right() - hours_w
        if show_summary or not row.ticket:
            summary_w = hours_left - self.GAP - summary_left
            if summary_w > 0:
                painter.setPen(summary_color)
                text = metrics.elidedText(row.summary, Qt.TextElideMode.ElideRight, summary_w)
                painter.drawText(QPointF(summary_left, baseline), text)

        painter.setPen(text_color)
        painter.drawText(
            QRectF(hours_left, line.y(), hours_w, line.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            format_hours(row.hours),
        )

    def _paint_ticket_flow(self, painter: QPainter, area: QRectF, rows: list[TicketRow], p: Palette) -> None:
        """Schmale Kachel: nur die Ticketnummern als Fliesstext mit Umbruch.

        Jede Nummer wird einzeln gezeichnet und bekommt ein eigenes
        Trefferrechteck - so oeffnet ein Klick genau die angeklickte Nummer.
        """
        base = scaled_font(self.font(), -2)
        metrics = QFontMetricsF(base)
        line_height = metrics.height()
        comma_width = metrics.horizontalAdvance(", ")
        x, y = area.x(), area.y()
        tickets = [row for row in rows if row.ticket]
        for index, row in enumerate(tickets):
            width = metrics.horizontalAdvance(row.ticket)
            if x > area.x() and x + width > area.right():  # Zeilenumbruch
                x, y = area.x(), y + line_height
            if y + line_height > area.bottom() + 2:  # kein Platz mehr in der Kachel
                break

            hovered = self._hovered_ticket is row.entry
            token_font = QFont(base)
            token_font.setUnderline(hovered)
            painter.setFont(token_font)
            painter.setPen(QColor(p.accent if hovered else p.text_tertiary))
            painter.drawText(QPointF(x, y + metrics.ascent()), row.ticket)
            # Etwas hoehere Trefferflaeche macht das Anklicken leichter.
            self._ticket_hits.append((QRectF(x, y - 1, width, line_height + 2), row.entry))
            x += width

            if index < len(tickets) - 1:
                painter.setFont(base)
                painter.setPen(QColor(p.text_tertiary))
                painter.drawText(QPointF(x, y + metrics.ascent()), ",")
                x += comma_width

    # --- Auswahl --------------------------------------------------------

    def event(self, event: QEvent) -> bool:
        """Zeigt beim Verweilen ueber einer Kachel alle ihre Eintraege."""
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            cell = self._cell_at(event.pos().x(), event.pos().y())
            text = tooltip_html(cell, self._target_hours) if cell is not None else ""
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # Klick auf eine Ticketnummer oeffnet genau diesen Eintrag (Link-Verhalten).
        entry = self._ticket_at(event.position().x(), event.position().y())
        if entry is not None:
            self.ticket_activated.emit(entry)
            return
        cell = self._cell_at(event.position().x(), event.position().y())
        if cell is not None and cell.in_month:
            self._selected = cell.day
            self.update()
            self.day_selected.emit(cell)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Hebt eine ueberfahrene Ticketnummer hervor (Hand-Cursor + Unterstrich)."""
        entry = self._ticket_at(event.position().x(), event.position().y())
        if entry is not self._hovered_ticket:
            self._hovered_ticket = entry
            self.setCursor(Qt.CursorShape.PointingHandCursor if entry is not None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Verlaesst die Maus das Widget, verschwindet die Hervorhebung."""
        if self._hovered_ticket is not None:
            self._hovered_ticket = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def _ticket_at(self, x: float, y: float) -> WorklogEntry | None:
        """Liefert den Eintrag, dessen Ticketnummer unter dem Punkt liegt, sonst None."""
        point = QPointF(x, y)
        for rect, entry in self._ticket_hits:
            if rect.contains(point):
                return entry
        return None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Doppelklick auf eine Kachel meldet den Tag zur Detailanzeige."""
        cell = self._cell_at(event.position().x(), event.position().y())
        if cell is not None and cell.in_month:
            self._selected = cell.day
            self.update()
            self.day_activated.emit(cell)

    def _cell_at(self, x: float, y: float) -> DayCell | None:
        """Findet die Kachel unter einem Punkt (Wochensummen-Spalte ausgenommen)."""
        if not self._cells:
            return None
        area, cell_w, cell_h, rows = self._geometry()

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
