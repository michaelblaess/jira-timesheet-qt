"""Summen-/Statistikleiste unter den Ansichten - dynamisch je Ansicht.

Ersetzt die einzelne "SUMME"-Zahl durch die volle Leiste der TUI und passt den
Inhalt an die aktive Ansicht an:
- Liste: Arbeitstage | Ist | (manuell) | Soll | Differenz | Ø | (Netto | Brutto)
- Kalender: gebuchte Tage | Ist | Soll | (Fehlt) - Fortschritt = gebuchte Tage
- Jahr: Jahr | Ist | Soll | Prognose - Fortschritt = Ist/Soll

Links sitzt ein schlanker Fortschrittsbalken (RatioBar). Die Berechnung der
Listen-Abschnitte liegt als reine Funktion daneben, damit sie ohne Qt testbar ist.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from jira_timesheet_qt.i18n import format_eur, format_number
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.ui.theme import Mode, palette_for


@dataclass(frozen=True)
class SummarySegment:
    """Ein Abschnitt der Leiste: Beschriftung (optional) und Wert."""

    label: str
    value: str


def build_summary_segments(
    timesheet: Timesheet,
    settings: Settings,
    target_workdays: int,
) -> list[SummarySegment]:
    """Baut die Abschnitte der Summenleiste aus einem Stundenzettel.

    Reine Funktion ohne Qt - die Formeln entsprechen der Textual-TUI.

    Args:
        timesheet:
            Der aktuell geladene Stundenzettel.
        settings:
            Die Einstellungen (Stunden/Tag, Stundensatz, Steuersatz).
        target_workdays:
            Anzahl der Soll-Arbeitstage im Zeitraum (Mo-Fr ohne Feiertag).

    Returns:
        Liste der anzuzeigenden Abschnitte in fester Reihenfolge.
    """
    total = timesheet.total_hours
    manual = sum(entry.hours for entry in timesheet.all_entries if entry.manual)
    target_hours = target_workdays * settings.hours_per_day
    diff = total - target_hours

    segments: list[SummarySegment] = [
        SummarySegment("Arbeitstage", str(timesheet.working_days)),
        SummarySegment("Ist", f"{format_number(total)} h"),
    ]

    if manual > 0:
        segments.append(SummarySegment("davon manuell", f"{format_number(manual)} h"))

    if target_hours > 0:
        segments.append(SummarySegment("Soll", f"{format_number(target_hours)} h"))
        sign = "+" if diff >= 0 else "-"
        segments.append(SummarySegment("", f"{sign}{format_number(abs(diff))} h"))

    segments.append(SummarySegment("Ø", f"{format_number(timesheet.average_hours)} h/Tag"))

    if settings.hourly_rate > 0:
        netto = total * settings.hourly_rate
        brutto = netto * (1.0 + settings.vat_rate / 100.0)
        segments.append(SummarySegment("Netto", format_eur(netto)))
        segments.append(SummarySegment("Brutto", format_eur(brutto)))

    return segments


class RatioBar(QWidget):
    """Schlanker Fortschrittsbalken mit Prozenttext.

    Gruen ab dem Sollwert (Anteil >= 1), sonst in der Akzentfarbe. Selbst
    gezeichnet, damit die Farbe am Wert haengt - ein QProgressBar liesse das
    ueber QSS nur umstaendlich zu.
    """

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._ratio = 0.0
        self._text = ""
        self.setFixedWidth(160)
        self.setMinimumHeight(20)

    def set_value(self, ratio: float, text: str) -> None:
        """Setzt Fuellstand (0..1+, Anzeige bei 1 gekappt) und Beschriftung."""
        self._ratio = max(0.0, ratio)
        self._text = text
        self.update()

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p = palette_for(self._mode)
        rect = QRectF(0, (self.height() - 16) / 2, self.width(), 16)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.bg_tertiary))
        painter.drawRoundedRect(rect, 8, 8)

        if self._ratio > 0:
            fill = QRectF(rect)
            fill.setWidth(rect.width() * min(1.0, self._ratio))
            painter.setBrush(QColor(p.green if self._ratio >= 1.0 else p.accent))
            painter.drawRoundedRect(fill, 8, 8)

        if self._text:
            painter.setPen(QColor(p.text_primary))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._text)
        painter.end()


class SummaryBar(QWidget):
    """Zeigt die ansichtsabhaengige Summenleiste samt Fortschrittsbalken."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SummaryBar")
        self._mode = mode

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 6, 18, 6)
        outer.setSpacing(14)

        self._bar = RatioBar(mode)
        outer.addWidget(self._bar)

        # Eigenes Layout fuer die Abschnitte, damit der Balken beim Neuaufbau
        # stehen bleibt.
        self._segments = QHBoxLayout()
        self._segments.setContentsMargins(0, 0, 0, 0)
        self._segments.setSpacing(8)
        outer.addLayout(self._segments, 1)

        self.clear()

    # --- Ansichten ------------------------------------------------------

    def show_list(self, timesheet: Timesheet | None, settings: Settings, target_workdays: int) -> None:
        """Liste: volle Summenleiste, Fortschritt Ist gegen Soll."""
        if timesheet is None:
            self.clear()
            return
        self._render(build_summary_segments(timesheet, settings, target_workdays))
        target = target_workdays * settings.hours_per_day
        self._set_ratio(timesheet.total_hours, target)

    def show_calendar(
        self,
        booked_days: int,
        total_workdays: int,
        total_hours: float,
        target_hours: float,
        missing_days: int,
    ) -> None:
        """Kalender: gebuchte Arbeitstage, Ist/Soll; Fortschritt = gebuchte Tage."""
        segments = [
            SummarySegment("Gebucht", f"{booked_days}/{total_workdays} Tage"),
            SummarySegment("Ist", f"{format_number(total_hours)} h"),
            SummarySegment("Soll", f"{format_number(target_hours)} h"),
        ]
        if missing_days > 0:
            segments.append(SummarySegment("Fehlt", f"{missing_days} Tage"))
        self._render(segments)
        self._set_ratio(booked_days, total_workdays)

    def show_year(self, year: int, actual: float, target: float, forecast: float) -> None:
        """Jahr: Ist/Soll/Prognose; Fortschritt = Ist gegen Soll."""
        self._render(
            [
                SummarySegment("Jahr", str(year)),
                SummarySegment("Ist", f"{format_number(actual)} h"),
                SummarySegment("Soll", f"{format_number(target)} h"),
                SummarySegment("Prognose", f"{format_number(forecast)} h"),
            ]
        )
        self._set_ratio(actual, target)

    def clear(self) -> None:
        """Leert die Leiste - ohne Daten bleiben Balken und Text unsichtbar."""
        self._render([])
        self._bar.setVisible(False)

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild (faerbt den Balken um)."""
        self._mode = mode
        self._bar.apply_mode(mode)

    # --- Aufbau ---------------------------------------------------------

    def _set_ratio(self, actual: float, target: float) -> None:
        """Setzt den Fortschrittsbalken aus Ist und Soll (Prozenttext)."""
        ratio = actual / target if target > 0 else 0.0
        self._bar.setVisible(True)
        self._bar.set_value(ratio, f"{ratio * 100:.0f} %" if target > 0 else "")

    def _render(self, segments: list[SummarySegment]) -> None:
        """Baut die Abschnitte neu auf (der Balken bleibt stehen)."""
        self._clear_segments()
        self._segments.addStretch(1)
        for index, segment in enumerate(segments):
            if index > 0:
                self._segments.addWidget(self._separator())
            if segment.label:
                self._segments.addWidget(self._label(segment.label, "SummaryStatLabel"))
            self._segments.addWidget(self._label(segment.value, "SummaryStatValue"))
        self._segments.addStretch(1)

    def _clear_segments(self) -> None:
        """Entfernt die bisherigen Abschnitte (auch die Stretch-Elemente)."""
        while self._segments.count():
            item = self._segments.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # setParent(None) entfernt das Widget SOFORT aus der Anzeige;
                # deleteLater allein liesse es als Geist stehen (ueberlappt die
                # neuen Werte bis zum naechsten Event-Loop-Lauf).
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    @staticmethod
    def _separator() -> QLabel:
        sep = QLabel("|")
        sep.setObjectName("SummarySep")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return sep
