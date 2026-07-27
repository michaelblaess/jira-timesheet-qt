"""Tests fuer die nach Tag gruppierte Ansicht (Baum-Modell + Umschalter)."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.timesheet_model import COLUMNS, ENTRY_ROLE
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel

_HOURS_COL = next(i for i, c in enumerate(COLUMNS) if c.key == "hours")
_SUMMARY_COL = next(i for i, c in enumerate(COLUMNS) if c.key == "summary")
_TICKET_COL = next(i for i, c in enumerate(COLUMNS) if c.key == "ticket")


def _model() -> TimesheetTreeModel:
    model = TimesheetTreeModel()
    model.set_timesheet(demo_timesheet())
    return model


class TestTreeModel:
    def test_groups_by_distinct_day(self, qapp: QApplication) -> None:
        model = _model()
        # Die Demodaten haben Eintraege an acht verschiedenen Tagen.
        assert model.rowCount() == 8
        # Der erste Tag (20.07.) hat drei Eintraege.
        first_group = model.index(0, 0)
        assert model.rowCount(first_group) == 3

    def test_group_row_shows_daily_sum_and_count(self, qapp: QApplication) -> None:
        model = _model()
        # 20.07.: 2,5 + 1,5 + 4,0 = 8,00 h
        sum_cell = model.index(0, _HOURS_COL)
        assert model.data(sum_cell, Qt.ItemDataRole.DisplayRole) == "8,00"
        count_cell = model.index(0, _SUMMARY_COL)
        assert model.data(count_cell, Qt.ItemDataRole.DisplayRole) == "3 Einträge"

    def test_group_row_is_bold(self, qapp: QApplication) -> None:
        model = _model()
        font = model.data(model.index(0, 0), Qt.ItemDataRole.FontRole)
        assert font is not None and font.bold()

    def test_entry_row_has_ticket_and_empty_date(self, qapp: QApplication) -> None:
        model = _model()
        group = model.index(0, 0)
        # Datum-Spalte des Kindes ist leer - sie steht in der Gruppenzeile.
        assert model.data(model.index(0, 0, group), Qt.ItemDataRole.DisplayRole) == ""
        ticket = model.data(model.index(0, _TICKET_COL, group), Qt.ItemDataRole.DisplayRole)
        assert ticket == "PROJ-0"

    def test_entry_role_and_helpers(self, qapp: QApplication) -> None:
        model = _model()
        group = model.index(0, 0)
        child = model.index(0, 0, group)
        assert model.entry_at_index(child) is not None
        assert model.entry_at_index(group) is None  # Gruppe hat keinen Eintrag
        assert model.day_at_index(group) == date(2026, 7, 20)
        assert model.day_at_index(child) == date(2026, 7, 20)
        # ENTRY_ROLE liefert denselben Eintrag (fuer den Detailbereich).
        assert model.index(0, 0, group).data(ENTRY_ROLE) is model.entry_at_index(child)

    def test_parent_of_child_is_its_group(self, qapp: QApplication) -> None:
        model = _model()
        group = model.index(0, 0)
        child = model.index(0, 0, group)
        assert model.parent(child) == group
        assert not model.parent(group).isValid()  # Gruppen haengen an der Wurzel


class TestGroupingToggle:
    def test_toggle_switches_the_list_page(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_group_toggled(False)
        assert window._list_stack.currentIndex() == 1  # flache Liste
        window._on_group_toggled(True)
        assert window._grouped is True
        assert window._list_stack.currentIndex() == 2  # gruppiert

    def test_search_filters_the_grouped_view_recursively(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_group_toggled(True)
        window._on_search_changed("Bundle")
        # "Bundle" kommt an zwei Tagen vor (22.07. und 28.07.) - die Gruppen
        # bleiben erhalten, weil ein Kind den Begriff enthaelt.
        assert window._tree_proxy.rowCount() == 2
