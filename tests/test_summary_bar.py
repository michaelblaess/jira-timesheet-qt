"""Tests fuer die Summenleisten-Berechnung.

Prueft die reine Funktion build_summary_segments gegen die TUI-Formeln:
Ist = Summe Stunden, Soll = Arbeitstage x Stunden/Tag, Differenz mit Vorzeichen,
manueller Anteil nur bei > 0, Netto/Brutto nur bei Stundensatz > 0.
"""

from __future__ import annotations

from datetime import date

import pytest

from jira_timesheet_qt.i18n import load_locale
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.ui.summary_bar import build_summary_segments


@pytest.fixture(autouse=True)
def _german() -> None:
    load_locale("de")


def _entry(hours: float, *, manual: bool = False) -> WorklogEntry:
    return WorklogEntry(
        date=date(2026, 7, 1),
        ticket="PROJ-0",
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
