"""Tests fuer die Soll-Ist-Ampel der Tagessummen.

Ueber der Soll-Stundenzahl gruen, darunter rot - in der flachen Tabelle auf der
Tagessummen-Spalte, im Baum zusaetzlich auf der Stunden-Spalte der Gruppenzeile.
Die Einzelstunden eines Eintrags bleiben ungefaerbt.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.export_column import default_columns
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.ui.grid_columns import build_columns
from jira_timesheet_qt.ui.timesheet_model import TimesheetModel
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel

FR = Qt.ItemDataRole.ForegroundRole
_KEYS = [c.key for c in build_columns(default_columns())]
_DAY_HOURS = _KEYS.index("day_hours")
_HOURS = _KEYS.index("hours")

OVER = QColor("#2f9e44")
UNDER = QColor("#c92a2a")


MANUAL = QColor("#ff0000")


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


def _timesheet(*day_hours: list[float]) -> Timesheet:
    """Ein Stundenzettel mit je einem Tag pro uebergebener Stundenliste."""
    days = [
        TimesheetDay(date(2026, 7, 1 + i), [_entry(h) for h in hours])
        for i, hours in enumerate(day_hours)
    ]
    return Timesheet(
        developer="a",
        email="a@b.de",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        days=days,
    )


class TestFlatTable:
    def test_day_total_green_when_at_or_over_target(self, qapp: QApplication) -> None:
        model = TimesheetModel()
        model.set_timesheet(_timesheet([8.0]))  # genau Soll
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert model.index(0, _DAY_HOURS).data(FR).name() == OVER.name()

    def test_day_total_red_when_under_target(self, qapp: QApplication) -> None:
        model = TimesheetModel()
        model.set_timesheet(_timesheet([5.0]))
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert model.index(0, _DAY_HOURS).data(FR).name() == UNDER.name()

    def test_hours_column_stays_uncoloured(self, qapp: QApplication) -> None:
        """Nur die Tagessumme traegt die Ampel, nicht die Einzelstunden."""
        model = TimesheetModel()
        model.set_timesheet(_timesheet([5.0]))
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert model.index(0, _HOURS).data(FR) is None

    def test_disabled_leaves_no_colour(self, qapp: QApplication) -> None:
        model = TimesheetModel()
        model.set_timesheet(_timesheet([5.0]))
        model.set_day_total_colors(None, None, target=8.0)
        assert model.index(0, _DAY_HOURS).data(FR) is None


class TestManualColourInteraction:
    """Die Markierung manueller Eintraege bleibt den Zahlenspalten fern."""

    def _model(self) -> TimesheetModel:
        model = TimesheetModel()
        model.set_timesheet(_timesheet([5.0]))  # ein manueller Eintrag
        # Eintrag manuell machen
        model.set_timesheet(
            Timesheet(
                developer="a",
                email="a@b.de",
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 31),
                days=[TimesheetDay(date(2026, 7, 1), [_entry(5.0, manual=True)])],
            )
        )
        model.set_manual_color(MANUAL)
        return model

    def test_text_column_gets_manual_colour(self, qapp: QApplication) -> None:
        model = self._model()
        model.set_day_total_colors(None, None, target=8.0)  # Ampel aus
        ticket = _KEYS.index("ticket")
        assert model.index(0, ticket).data(FR).name() == MANUAL.name()

    def test_hours_column_ignores_manual_colour(self, qapp: QApplication) -> None:
        model = self._model()
        model.set_day_total_colors(None, None, target=8.0)  # Ampel aus
        assert model.index(0, _HOURS).data(FR) is None

    def test_day_total_keeps_ampel_over_manual(self, qapp: QApplication) -> None:
        """Auf der Tagessumme eines manuellen Eintrags gewinnt die Ampel."""
        model = self._model()
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert model.index(0, _DAY_HOURS).data(FR).name() == UNDER.name()  # 5 < 8


class TestTree:
    def _group_index(self, model: TimesheetTreeModel, column: int) -> QModelIndex:
        return model.index(0, column, QModelIndex())

    def test_group_row_hours_are_coloured(self, qapp: QApplication) -> None:
        """Die Gruppenzeile faerbt Stunden- UND Tagessummen-Spalte nach Soll."""
        model = TimesheetTreeModel()
        model.set_timesheet(_timesheet([3.0, 3.0]))  # Tagessumme 6 < 8 -> rot
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert self._group_index(model, _HOURS).data(FR).name() == UNDER.name()
        assert self._group_index(model, _DAY_HOURS).data(FR).name() == UNDER.name()

    def test_group_row_green_over_target(self, qapp: QApplication) -> None:
        model = TimesheetTreeModel()
        model.set_timesheet(_timesheet([5.0, 4.0]))  # 9 >= 8 -> gruen
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        assert self._group_index(model, _DAY_HOURS).data(FR).name() == OVER.name()

    def test_entry_hours_stay_uncoloured(self, qapp: QApplication) -> None:
        """Auf der Eintragszeile bleibt die Einzel-Stundenspalte ungefaerbt."""
        model = TimesheetTreeModel()
        model.set_timesheet(_timesheet([5.0]))
        model.set_day_total_colors(OVER, UNDER, target=8.0)
        group = model.index(0, 0, QModelIndex())
        entry_hours = model.index(0, _HOURS, group)
        assert entry_hours.data(FR) is None
