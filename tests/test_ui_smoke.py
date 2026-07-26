"""Rauchtest der Oberflaeche.

Prueft, dass sich das Fenster wirklich aufbauen laesst, das Stylesheet greift,
die Tabelle Daten zeigt, Sortieren und Suchen funktionieren und der
Detailbereich der Auswahl folgt. Laeuft ohne sichtbares Fenster ueber die
Offscreen-Plattform von Qt - siehe conftest.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableView

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.fonts import load_fonts
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import DARK, LIGHT, Mode, build_qss
from jira_timesheet_qt.ui.timesheet_model import COLUMNS, ENTRY_ROLE, TimesheetModel


@pytest.fixture
def window(qapp: QApplication) -> MainWindow:
    """Baut ein Fenster mit Beispieldaten."""
    win = MainWindow(Settings(), Mode.DARK)
    win.set_timesheet(demo_timesheet())
    return win


class TestTheme:
    def test_qss_is_built_for_both_modes(self) -> None:
        for mode, palette in ((Mode.DARK, DARK), (Mode.LIGHT, LIGHT)):
            qss = build_qss(mode, "Segoe UI", "Consolas")
            assert palette.bg_primary in qss
            assert palette.accent in qss
            # Ohne diese Regeln bleiben die Qt-Vorgaben sichtbar.
            assert "QScrollBar" in qss
            assert "QHeaderView::section" in qss

    def test_stylesheet_applies_to_application(self, qapp: QApplication) -> None:
        fonts = load_fonts()
        qapp.setStyleSheet(build_qss(Mode.DARK, fonts.sans, fonts.mono))
        assert DARK.bg_primary in qapp.styleSheet()


class TestModel:
    def test_rows_and_columns(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        assert model.rowCount() == 15
        assert model.columnCount() == len(COLUMNS)

    def test_german_number_and_date_format(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        first = model.index(0, 0).data(Qt.ItemDataRole.DisplayRole)
        hours = model.index(0, 5).data(Qt.ItemDataRole.DisplayRole)
        assert first == "20.07.2026"
        assert hours == "2,50"

    def test_total_hours(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        assert model.total_hours == pytest.approx(54.0)

    def test_period(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        assert model.period == (date(2026, 7, 20), date(2026, 7, 29))

    def test_empty_timesheet_clears_the_model(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        model.set_timesheet(None)
        assert model.rowCount() == 0
        assert model.period is None


class TestWindow:
    def test_table_shows_all_rows(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        assert table.model().rowCount() == 15

    def test_search_filters_rows(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        window._proxy.setFilterFixedString("Usercentrics")
        assert table.model().rowCount() == 1
        window._proxy.setFilterFixedString("")
        assert table.model().rowCount() == 15

    def test_sorting_uses_raw_values_not_display_text(self, window: MainWindow) -> None:
        """Nach Stunden sortiert, nicht nach der Zeichenkette "0,50"."""
        proxy = window._proxy
        proxy.sort(5, Qt.SortOrder.DescendingOrder)
        top = proxy.index(0, 5).data(Qt.ItemDataRole.DisplayRole)
        assert top == "7,00"
        proxy.sort(5, Qt.SortOrder.AscendingOrder)
        assert proxy.index(0, 5).data(Qt.ItemDataRole.DisplayRole) == "0,50"

    def test_selection_updates_the_detail_panel(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        table.selectRow(0)
        entry = window._proxy.index(0, 0).data(ENTRY_ROLE)
        assert entry is not None
        assert window._detail._key.text() == entry.ticket

    def test_view_switch_changes_the_page(self, window: MainWindow) -> None:
        assert window._stack.currentIndex() == 0
        window._sidebar.view_changed.emit(1)
        assert window._stack.currentIndex() == 1

    def test_theme_toggle_reports_the_other_mode(self, window: MainWindow) -> None:
        seen: list[str] = []
        window.theme_changed.connect(seen.append)
        window._toggle_theme()
        assert seen == ["light"]
        assert window.mode is Mode.LIGHT

    def test_header_shows_period_and_count(self, window: MainWindow) -> None:
        assert window._header._title.text() == "Juli 2026"
        assert "15 Einträge" in window._header._subtitle.text()

    def test_empty_state(self, qapp: QApplication) -> None:
        win = MainWindow(Settings(), Mode.DARK)
        win.set_timesheet(None)
        assert win._header._title.text() == "Kein Zeitraum"
        assert win._detail._key.text() == "Kein Eintrag gewählt"
