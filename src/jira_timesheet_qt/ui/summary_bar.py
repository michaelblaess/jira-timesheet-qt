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

from dataclasses import dataclass, replace

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from jira_timesheet_qt.i18n import format_eur, format_number
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.ui.theme import Mode, palette_for


@dataclass(frozen=True)
class SummarySegment:
    """Ein Abschnitt der Leiste: Beschriftung (optional), Wert und Farbe.

    color ist ein Hex-Wert ohne fuehrendes # (z.B. die Soll-Ist-Ampel des
    Ist-Werts) oder None fuer die normale Textfarbe.
    """

    label: str
    value: str
    color: str | None = None
    tooltip: str = ""


# Erklaerungen je Kennzahl (Tooltip). Sagen, WAS das Feld bedeutet und WIE es
# gerechnet wird - bewusst als Formel, nicht mit den Live-Zahlen.
_TOOLTIPS: dict[str, str] = {
    "Arbeitstage": "Arbeitstage im Zeitraum (Mo-Fr ohne Feiertage des Bundeslandes).",
    "Ist": "Ist-Stunden: Summe aller tatsaechlich gebuchten Stunden.",
    "davon manuell": "Anteil der Ist-Stunden, der manuell (ohne Jira) erfasst wurde.",
    "Soll": "Soll-Stunden: Arbeitstage x Stunden pro Tag aus den Einstellungen.",
    "Verbleibend": "Noch offen bis zum Soll: Soll minus Ist (nie negativ).",
    "Prognose": "Hochrechnung aufs Jahresende: Ist der abgelaufenen Monate + Soll der restlichen.",
    "Ø": "Durchschnittliche Stunden je gebuchtem Arbeitstag.",
    "Netto": "Ist-Umsatz netto: Ist-Stunden x Stundensatz.",
    "Brutto": "Ist-Umsatz brutto: Netto zuzueglich Mehrwertsteuer.",
    "Prognose Netto": "Prognostizierter Jahresumsatz netto: Prognose-Stunden x Stundensatz.",
    "Prognose Brutto": "Prognostizierter Jahresumsatz brutto: Prognose netto zuzueglich MwSt.",
    "Gebucht": "Arbeitstage des Monats mit mindestens einer Buchung, von allen Arbeitstagen.",
    "Fehlt": "Arbeitstage des Monats noch ganz ohne Buchung.",
}
# Der Differenz-Abschnitt hat kein Label - sein Tooltip haengt am Sonderschluessel.
_DIFF_TOOLTIP = "Differenz Ist zu Soll (+ Ueberstunden, - noch fehlend)."


def _seg(label: str, value: str) -> SummarySegment:
    """Baut einen Abschnitt und haengt die passende Erklaerung als Tooltip an."""
    return SummarySegment(label, value, tooltip=_TOOLTIPS.get(label, ""))


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
        _seg("Arbeitstage", str(timesheet.working_days)),
        _seg("Ist", f"{format_number(total)} h"),
    ]

    if manual > 0:
        segments.append(_seg("davon manuell", f"{format_number(manual)} h"))

    if target_hours > 0:
        segments.append(_seg("Soll", f"{format_number(target_hours)} h"))
        sign = "+" if diff >= 0 else "-"
        segments.append(SummarySegment("", f"{sign}{format_number(abs(diff))} h", tooltip=_DIFF_TOOLTIP))

    segments.append(_seg("Ø", f"{format_number(timesheet.average_hours)} h/Tag"))

    if settings.hourly_rate > 0:
        netto = total * settings.hourly_rate
        brutto = netto * (1.0 + settings.vat_rate / 100.0)
        segments.append(_seg("Netto", format_eur(netto)))
        segments.append(_seg("Brutto", format_eur(brutto)))

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
        self.setFixedWidth(200)
        self.setMinimumHeight(28)
        self.setToolTip("Fortschritt: erreichter Anteil in Prozent (gruen ab dem Soll).")

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
        bar_height = 22
        rect = QRectF(0, (self.height() - bar_height) / 2, self.width(), bar_height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.bg_tertiary))
        painter.drawRect(rect)

        if self._ratio > 0:
            fill = QRectF(rect)
            fill.setWidth(rect.width() * min(1.0, self._ratio))
            painter.setBrush(QColor(p.green if self._ratio >= 1.0 else p.accent))
            painter.drawRect(fill)

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

        # Ampel-Farben fuer den Ist-Wert (Hex ohne #), None = keine Faerbung.
        self._over_color: str | None = None
        self._under_color: str | None = None

        self.clear()

    def set_day_colors(self, over: str | None, under: str | None) -> None:
        """Setzt die Ampel-Farben (Hex ohne #) fuer den Ist-Wert; None = keine."""
        self._over_color = over
        self._under_color = under

    def _ist_color(self, actual: float, target: float) -> str | None:
        """Ampel-Farbe des Ist-Werts: ueber Soll gruen, darunter rot (sonst None)."""
        if self._over_color is None or self._under_color is None or target <= 0:
            return None
        return self._over_color if actual >= target else self._under_color

    # --- Ansichten ------------------------------------------------------

    def show_list(self, timesheet: Timesheet | None, settings: Settings, target_workdays: int) -> None:
        """Liste: volle Summenleiste, Fortschritt Ist gegen Soll."""
        if timesheet is None:
            self.clear()
            return
        target = target_workdays * settings.hours_per_day
        segments = build_summary_segments(timesheet, settings, target_workdays)
        self._render(self._colour_ist(segments, timesheet.total_hours, target))
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
            _seg("Gebucht", f"{booked_days}/{total_workdays} Tage"),
            _seg("Ist", f"{format_number(total_hours)} h"),
            _seg("Soll", f"{format_number(target_hours)} h"),
        ]
        if missing_days > 0:
            segments.append(_seg("Fehlt", f"{missing_days} Tage"))
        self._render(self._colour_ist(segments, total_hours, target_hours))
        self._set_ratio(booked_days, total_workdays)

    def show_year(
        self,
        actual: float,
        target: float,
        forecast: float,
        *,
        manual: float = 0.0,
        hourly_rate: float = 0.0,
        vat_rate: float = 0.0,
    ) -> None:
        """Jahr: Ist, davon manuell, Soll, Verbleibend, Prognose und die Umsatz-Summen.

        Das Jahr selbst steht schon in der Toolbar und ist hier weggelassen.
        Netto/Brutto (Ist und Prognose) nur bei hinterlegtem Stundensatz. Der
        Fortschritt ist Ist gegen Soll.
        """
        segments = [_seg("Ist", f"{format_number(actual)} h")]
        if manual > 0:
            segments.append(_seg("davon manuell", f"{format_number(manual)} h"))
        segments += [
            _seg("Soll", f"{format_number(target)} h"),
            _seg("Verbleibend", f"{format_number(max(0.0, target - actual))} h"),
            _seg("Prognose", f"{format_number(forecast)} h"),
        ]
        if hourly_rate > 0:
            factor = 1.0 + vat_rate / 100.0
            netto = actual * hourly_rate
            forecast_netto = forecast * hourly_rate
            segments += [
                _seg("Netto", format_eur(netto)),
                _seg("Brutto", format_eur(netto * factor)),
                _seg("Prognose Netto", format_eur(forecast_netto)),
                _seg("Prognose Brutto", format_eur(forecast_netto * factor)),
            ]
        self._render(self._colour_ist(segments, actual, target))
        self._set_ratio(actual, target)

    def show_board(self, segments: list[SummarySegment]) -> None:
        """Ticket-Ansichten: freie Kennzahlen, kein Fortschrittsbalken.

        Der Balken zeigt sonst Ist gegen Soll in Stunden - fuer eine
        Ticketliste gibt es keine solche Groesse, und ein Balken ohne
        Bedeutung ist schlimmer als keiner.

        Args:
            segments:
                Die anzuzeigenden Kennzahlen.
        """
        self._render(segments)
        self._bar.setVisible(False)

    def _colour_ist(self, segments: list[SummarySegment], actual: float, target: float) -> list[SummarySegment]:
        """Faerbt den Ist-Abschnitt nach der Soll-Ist-Ampel (gruen/rot)."""
        color = self._ist_color(actual, target)
        if color is None:
            return segments
        return [replace(s, color=color) if s.label == "Ist" else s for s in segments]

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
        """Baut die Abschnitte neu auf (der Balken bleibt stehen).

        Jede Kennzahl sitzt in einem eigenen gerahmten Panel (wie die
        Statusleisten von DevExpress/Infragistics), getrennt statt mit "|".
        """
        self._clear_segments()
        self._segments.addStretch(1)
        for segment in segments:
            self._segments.addWidget(self._panel(segment))
        self._segments.addStretch(1)

    def _panel(self, segment: SummarySegment) -> QFrame:
        """Baut ein gerahmtes Statusleisten-Panel aus Beschriftung und Wert.

        Der Tooltip haengt am Panel UND an beiden Labels - Qt zeigt sonst nur
        den Tooltip des Widgets direkt unter dem Zeiger, nicht den des Elterns.
        """
        frame = QFrame()
        frame.setObjectName("SummaryPanel")
        row = QHBoxLayout(frame)
        row.setContentsMargins(9, 2, 9, 2)
        row.setSpacing(6)
        widgets = [frame]
        if segment.label:
            caption = self._label(segment.label, "SummaryStatLabel")
            row.addWidget(caption)
            widgets.append(caption)
        value = self._label(segment.value, "SummaryStatValue")
        if segment.color:
            # Nur die Farbe ueberschreiben - Groesse/Fettung bleiben aus dem QSS.
            value.setStyleSheet(f"color: #{segment.color};")
        row.addWidget(value)
        widgets.append(value)
        if segment.tooltip:
            for widget in widgets:
                widget.setToolTip(segment.tooltip)
        return frame

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
