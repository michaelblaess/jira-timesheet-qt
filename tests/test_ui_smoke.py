"""Rauchtest der Oberflaeche.

Prueft, dass sich das Fenster wirklich aufbauen laesst, das Stylesheet greift,
die Tabelle Daten zeigt, Sortieren und Suchen funktionieren und die Auswahl
den aktuellen Eintrag mitfuehrt. Laeuft ohne sichtbares Fenster ueber die
Offscreen-Plattform von Qt - siehe conftest.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QTableView

from jira_timesheet_qt.models.export_column import default_columns
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.fonts import load_fonts
from jira_timesheet_qt.ui.grid_columns import build_columns
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import DARK, LIGHT, Mode, build_palette, build_qss
from jira_timesheet_qt.ui.timesheet_model import ENTRY_ROLE, TimesheetModel

_KEYS = [c.key for c in build_columns(default_columns())]
_DATE_COL = _KEYS.index("date")
_HOURS_COL = _KEYS.index("hours")


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
            # Die strukturellen Flaechen werden per QSS gesetzt, die Farben
            # stammen aus der Palette. Die Steuerelemente bleiben nativ (Fusion).
            assert "#ViewTabs" in qss
            assert "#ToolbarMonth" in qss
            assert "#SummaryBar" in qss
            assert palette.bg_secondary in qss
            assert palette.accent in qss

    def test_stylesheet_applies_to_application(self, qapp: QApplication) -> None:
        fonts = load_fonts()
        qapp.setStyleSheet(build_qss(Mode.DARK, fonts.sans, fonts.mono))
        assert "#ViewTabs" in qapp.styleSheet()

    def test_palette_is_built_for_both_modes(self, qapp: QApplication) -> None:
        for mode, palette in ((Mode.DARK, DARK), (Mode.LIGHT, LIGHT)):
            qpal = build_palette(mode)
            assert qpal.color(QPalette.ColorRole.Window).name() == palette.bg_primary
            assert qpal.color(QPalette.ColorRole.Highlight).name() == palette.accent

    def test_accent_overrides_the_palette(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.theme import ACCENTS, DEFAULT_ACCENT, palette_for, set_accent

        try:
            set_accent("blau")
            assert palette_for(Mode.DARK).accent == ACCENTS["blau"][0].accent
            assert palette_for(Mode.LIGHT).accent == ACCENTS["blau"][1].accent
        finally:
            set_accent(DEFAULT_ACCENT)  # sonst faerbt es folgende Tests ein

    def test_zoom_scales_the_qss_font_sizes(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.theme import set_scale

        base = build_qss(Mode.DARK, "Segoe UI", "Consolas")
        assert "font-size: 13px" in base
        try:
            set_scale(200)
            big = build_qss(Mode.DARK, "Segoe UI", "Consolas")
            assert "font-size: 26px" in big  # 13 px Grundschrift verdoppelt
            assert "font-size: 13px" not in big
        finally:
            set_scale(100)  # sonst zoomt es folgende Tests


class TestModel:
    def test_rows_and_columns(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        assert model.rowCount() == 15
        assert model.columnCount() == len(_KEYS)

    def test_german_number_and_date_format(self) -> None:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        first = model.index(0, _DATE_COL).data(Qt.ItemDataRole.DisplayRole)
        hours = model.index(0, _HOURS_COL).data(Qt.ItemDataRole.DisplayRole)
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

    def test_hidden_columns_are_dropped_from_the_grid(self) -> None:
        """Der Kern des Fixes: Sichtbarkeit aus den Einstellungen steuert das Grid."""
        columns = default_columns()
        for column in columns:
            if column.key in ("customer", "day_hours", "week"):
                column.visible = False
        model = TimesheetModel()
        model.set_columns(columns, "Vertrieb")
        keys = model.column_keys()
        assert "customer" not in keys
        assert "day_hours" not in keys
        assert "week" not in keys
        assert keys == ["weekday", "date", "ticket", "description", "hours"]

    def test_all_hidden_falls_back_to_defaults(self) -> None:
        columns = default_columns()
        for column in columns:
            column.visible = False
        model = TimesheetModel()
        model.set_columns(columns, "Vertrieb")
        assert model.columnCount() == len(_KEYS)

    def test_customer_column_falls_back_to_default(self) -> None:
        model = TimesheetModel()
        model.set_columns(default_columns(), "Musterkunde")
        model.set_timesheet(demo_timesheet())
        customer_col = _KEYS.index("customer")
        # Jira-Zeilen tragen keinen eigenen Kunden -> Vorgabe aus den Einstellungen.
        jira_row = next(r for r in range(model.rowCount()) if not model.entry_at(r).manual)  # type: ignore[union-attr]
        assert model.index(jira_row, customer_col).data(Qt.ItemDataRole.DisplayRole) == "Musterkunde"


class TestWindow:
    def test_table_shows_all_rows(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        assert table.model().rowCount() == 15

    def test_search_filters_rows(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        window._proxy.setFilterFixedString("Consent")
        assert table.model().rowCount() == 1
        window._proxy.setFilterFixedString("")
        assert table.model().rowCount() == 15

    def test_sorting_uses_raw_values_not_display_text(self, window: MainWindow) -> None:
        """Nach Stunden sortiert, nicht nach der Zeichenkette "0,50"."""
        proxy = window._proxy
        proxy.sort(_HOURS_COL, Qt.SortOrder.DescendingOrder)
        top = proxy.index(0, _HOURS_COL).data(Qt.ItemDataRole.DisplayRole)
        assert top == "7,00"
        proxy.sort(_HOURS_COL, Qt.SortOrder.AscendingOrder)
        assert proxy.index(0, _HOURS_COL).data(Qt.ItemDataRole.DisplayRole) == "0,50"

    def test_selection_tracks_the_current_entry(self, window: MainWindow) -> None:
        table = window.findChild(QTableView)
        assert table is not None
        table.selectRow(0)
        entry = window._proxy.index(0, 0).data(ENTRY_ROLE)
        assert entry is not None
        # Der gewaehlte Eintrag wird fuer den Details-Befehl gemerkt.
        assert window._current_entry is entry

    def test_view_switch_changes_the_page(self, window: MainWindow) -> None:
        assert window._stack.currentIndex() == 0
        window._tabs.setCurrentIndex(1)
        assert window._stack.currentIndex() == 1

    def test_theme_toggle_reports_the_other_mode(self, window: MainWindow) -> None:
        seen: list[str] = []
        window.theme_changed.connect(seen.append)
        window._toggle_theme()
        assert seen == ["light"]
        assert window.mode is Mode.LIGHT

    def test_toolbar_shows_the_month(self, window: MainWindow) -> None:
        assert window._month_label.text() == "Juli 2026"

    def test_empty_state(self, qapp: QApplication) -> None:
        """Ohne Daten bleibt der Monat in der Toolbar sichtbar."""
        win = MainWindow(Settings(), Mode.DARK)
        win._year, win._month = 2026, 3
        win.set_timesheet(None)
        assert win._month_label.text() == "März 2026"
        assert win._current_entry is None
