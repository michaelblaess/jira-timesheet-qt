"""Summen-/Statistikleiste unter den Ansichten.

Ersetzt die einzelne "SUMME"-Zahl durch die volle Leiste der TUI:
Arbeitstage | Ist | (davon manuell) | Soll | Differenz | Durchschnitt |
(Netto | Brutto). Die Berechnung liegt als reine Funktion daneben, damit sie
ohne Qt testbar ist.

Farbliche Hervorhebung (rot bei Unterdeckung o.ae.) kommt bewusst erst mit der
spaeteren Look-Ueberarbeitung - hier zaehlt zunaechst die Vollstaendigkeit.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from jira_timesheet_qt.i18n import format_eur, format_number
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet


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


class SummaryBar(QWidget):
    """Zeigt die Summenleiste; wird bei jedem Stundenzettel neu befuellt."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SummaryBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(18, 6, 18, 6)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self._placeholder()

    def show_timesheet(self, timesheet: Timesheet | None, settings: Settings, target_workdays: int) -> None:
        """Aktualisiert die Leiste fuer einen Stundenzettel (oder leert sie)."""
        if timesheet is None:
            self._placeholder()
            return
        self._render(build_summary_segments(timesheet, settings, target_workdays))

    def _placeholder(self) -> None:
        """Setzt einen dezenten Platzhalter, solange nichts geladen ist."""
        self._render([SummarySegment("", "Noch keine Daten")])

    def _render(self, segments: list[SummarySegment]) -> None:
        """Baut die Leiste aus den Abschnitten neu auf."""
        self._clear()
        for index, segment in enumerate(segments):
            if index > 0:
                self._layout.addWidget(self._separator())
            if segment.label:
                self._layout.addWidget(self._label(segment.label, "SummaryStatLabel"))
            self._layout.addWidget(self._label(segment.value, "SummaryStatValue"))
        self._layout.addStretch(1)

    def _clear(self) -> None:
        """Entfernt alle bisherigen Elemente (auch den End-Stretch)."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # setParent(None) entfernt das Widget SOFORT aus der Anzeige.
                # deleteLater allein wuerde es bis zum naechsten Event-Loop-Lauf
                # als Geist an seiner alten Stelle stehen lassen (ueberlappt die
                # neuen Werte, bis der Platzhalter endlich geloescht ist).
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
