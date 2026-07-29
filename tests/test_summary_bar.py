"""Tests fuer die Summenleisten-Berechnung.

Prueft die reine Funktion build_summary_segments gegen die TUI-Formeln:
Ist = Summe Stunden, Soll = Arbeitstage x Stunden/Tag, Differenz mit Vorzeichen,
manueller Anteil nur bei > 0, Netto/Brutto nur bei Stundensatz > 0.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from jira_timesheet_qt.i18n import load_locale
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.ui.summary_bar import RatioBar, SummaryBar, build_summary_segments


@pytest.fixture(autouse=True)
def _german() -> None:
    load_locale("de")


def _entry(hours: float, *, manual: bool = False) -> WorklogEntry:
    return WorklogEntry(
        date=date(2026, 7, 1),
        ticket="PROJ-1",
        summary="x",
        author="a",
        budget="",
        hours=hours,
        manual=manual,
    )


def _timesheet(days: list[TimesheetDay]) -> Timesheet:
    return Timesheet(
        developer="a",
        email="a@b.de",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        days=days,
    )


def _as_dict(ts: Timesheet, settings: Settings, workdays: int) -> dict[str, str]:
    """Segmente als label->value; leere Labels bekommen den Schluessel 'diff'."""
    result: dict[str, str] = {}
    for seg in build_summary_segments(ts, settings, workdays):
        result[seg.label or "diff"] = seg.value
    return result


class TestSummarySegments:
    def test_basic_totals(self) -> None:
        ts = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(4.0), _entry(4.0)])])
        data = _as_dict(ts, Settings(hours_per_day=8.0), workdays=0)
        assert data["Arbeitstage"] == "1"
        assert data["Ist"] == "8,00 h"
        assert data["Ø"] == "8,00 h/Tag"

    def test_soll_and_negative_diff(self) -> None:
        # 1 Tag mit 6h, aber 2 Soll-Arbeitstage x 8h = 16h Soll -> Diff -10h.
        ts = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(6.0)])])
        data = _as_dict(ts, Settings(hours_per_day=8.0), workdays=2)
        assert data["Soll"] == "16,00 h"
        assert data["diff"] == "-10,00 h"

    def test_positive_diff_has_plus(self) -> None:
        ts = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(10.0)])])
        data = _as_dict(ts, Settings(hours_per_day=8.0), workdays=1)
        assert data["diff"] == "+2,00 h"

    def test_manual_only_when_present(self) -> None:
        ts_no = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(4.0)])])
        assert "davon manuell" not in _as_dict(ts_no, Settings(), 0)

        ts_yes = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(4.0), _entry(2.0, manual=True)])])
        assert _as_dict(ts_yes, Settings(), 0)["davon manuell"] == "2,00 h"

    def test_netto_brutto_only_with_rate(self) -> None:
        ts = _timesheet([TimesheetDay(date(2026, 7, 1), [_entry(10.0)])])
        assert "Netto" not in _as_dict(ts, Settings(hourly_rate=0.0), 0)

        data = _as_dict(ts, Settings(hourly_rate=100.0, vat_rate=19.0), workdays=0)
        assert data["Netto"] == "1.000,00 €"
        assert data["Brutto"] == "1.190,00 €"


class TestSummaryBarWidget:
    def test_calendar_shows_booked_days_and_missing(self, qapp: QApplication) -> None:
        bar = SummaryBar()
        bar.show_calendar(8, 23, 54.0, 184.0, 15)
        texts = [label.text() for label in bar.findChildren(QLabel)]
        assert "8/23 Tage" in texts
        assert "15 Tage" in texts

    def test_year_shows_forecast(self, qapp: QApplication) -> None:
        bar = SummaryBar()
        bar.show_year(2026, 54.0, 2024.0, 910.0)
        texts = [label.text() for label in bar.findChildren(QLabel)]
        assert "2026" in texts
        assert any("910" in text for text in texts)
        assert "Verbleibend" in texts  # Soll - Ist steht jetzt mit dabei

    def test_year_shows_revenue_with_rate(self, qapp: QApplication) -> None:
        """Mit Stundensatz kommen Ist- und Prognose-Umsatz (Netto/Brutto) dazu."""
        bar = SummaryBar()
        bar.show_year(2026, 1000.0, 2000.0, 1800.0, manual=40.0, hourly_rate=100.0, vat_rate=19.0)
        texts = [label.text() for label in bar.findChildren(QLabel)]
        assert "davon manuell" in texts
        assert "Netto" in texts and "Brutto" in texts
        assert "Prognose Netto" in texts and "Prognose Brutto" in texts
        assert "100.000,00 €" in texts  # Ist Netto = 1000 h x 100 EUR
        assert "180.000,00 €" in texts  # Prognose Netto = 1800 h x 100 EUR

    def test_year_hides_revenue_without_rate(self, qapp: QApplication) -> None:
        bar = SummaryBar()
        bar.show_year(2026, 1000.0, 2000.0, 1800.0)
        texts = [label.text() for label in bar.findChildren(QLabel)]
        assert "Netto" not in texts

    def test_ratio_bar_keeps_value(self, qapp: QApplication) -> None:
        bar = RatioBar()
        bar.set_value(1.5, "150 %")
        assert bar._ratio == pytest.approx(1.5)


class TestIstAmpel:
    """Der Ist-Wert traegt dieselbe Soll-Ist-Ampel wie die Tagessummen."""

    def test_ist_color_logic(self, qapp: QApplication) -> None:
        bar = SummaryBar()
        assert bar._ist_color(5.0, 8.0) is None  # ohne gesetzte Farben nichts
        bar.set_day_colors("2f9e44", "c92a2a")
        assert bar._ist_color(8.0, 8.0) == "2f9e44"  # erreicht -> gruen
        assert bar._ist_color(5.0, 8.0) == "c92a2a"  # darunter -> rot
        assert bar._ist_color(5.0, 0.0) is None  # ohne Soll keine Aussage

    def test_ist_panel_is_coloured(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QFrame

        bar = SummaryBar()
        bar.set_day_colors("2f9e44", "c92a2a")
        bar.show_calendar(1, 5, 6.0, 40.0, 4)  # 6 h Ist < 40 h Soll -> rot
        ist_value = None
        for frame in bar.findChildren(QFrame):
            labels = frame.findChildren(QLabel)
            if len(labels) == 2 and labels[0].text() == "Ist":
                ist_value = labels[1]
        assert ist_value is not None
        assert "c92a2a" in ist_value.styleSheet()
