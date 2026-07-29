"""Rauchtest der Oberflaeche.

Prueft, dass sich das Fenster wirklich aufbauen laesst, das Stylesheet greift,
die Tabelle Daten zeigt, Sortieren und Suchen funktionieren und die Auswahl
den aktuellen Eintrag mitfuehrt. Laeuft ohne sichtbares Fenster ueber die
Offscreen-Plattform von Qt - siehe conftest.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QModelIndex, Qt
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

    def test_all_columns_are_resizable(self, window: MainWindow) -> None:
        """Jede Spalte ist frei ziehbar - keine fixe oder zwangsgestreckte Spalte."""
        from PySide6.QtWidgets import QHeaderView

        header = window._table.horizontalHeader()
        assert header.stretchLastSection() is False
        modes = {header.sectionResizeMode(i) for i in range(window._model.columnCount())}
        assert modes == {QHeaderView.ResizeMode.Interactive}

    def test_user_column_width_is_remembered(self, window: MainWindow) -> None:
        """Eine gezogene Spaltenbreite landet nach Spaltenschluessel in den Einstellungen."""
        keys = window._model.column_keys()
        window._on_section_resized(window._model, keys.index("ticket"), 222)
        assert window._settings.column_widths["ticket"] == 222

    def test_description_fills_available_width(self, window: MainWindow) -> None:
        """Die Beschreibung waechst in den freien Platz, statt abgeschnitten zu bleiben."""
        window._table.resize(1600, 400)
        QApplication.processEvents()  # Viewport uebernimmt die neue Breite erst im Event-Loop
        di = window._model.column_keys().index("description")
        window._fill_description(window._table, window._model)
        assert window._table.columnWidth(di) > window._model.column_width(di)

    def test_user_description_width_survives_fill(self, window: MainWindow) -> None:
        """Eine selbst gezogene Beschreibungsbreite bleibt von der Fuellung unangetastet."""
        window._settings.column_widths["description"] = 300
        window._table.resize(1600, 400)
        window._apply_column_layout(window._table, window._model)
        di = window._model.column_keys().index("description")
        assert window._table.columnWidth(di) == 300

    def test_group_toggle_collapses_and_persists(self, window: MainWindow) -> None:
        """Der Kontextmenue-Toggle klappt die gruppierte Liste zu und merkt sich das."""
        group0 = window._tree_proxy.index(0, 0, QModelIndex())
        assert window._tree.isExpanded(group0)
        window._toggle_group_state()
        assert window._groups_collapsed is True
        assert not window._tree.isExpanded(group0)

    def test_group_state_survives_model_reset(self, window: MainWindow) -> None:
        """Ein Modell-Reset (wie beim Speichern der Settings) klappt nicht ungewollt zu."""
        window._tree_model.set_columns(window._settings.export_columns, window._settings.default_customer)
        window._apply_group_state()
        assert window._tree.isExpanded(window._tree_proxy.index(0, 0, QModelIndex()))

    def test_summary_lives_in_status_bar(self, window: MainWindow) -> None:
        """Die Summenleiste sitzt jetzt als Panel in der echten QStatusBar."""
        from jira_timesheet_qt.ui.summary_bar import SummaryBar

        assert window.statusBar().findChild(SummaryBar) is not None

    def test_toast_shows_message_with_icon(self, window: MainWindow) -> None:
        """Die Toast-Benachrichtigung nimmt Text UND ein Icon an, ohne zu stuerzen."""
        from jira_timesheet_qt.ui.toast import Toast

        window.show_toast("Einstellungen gespeichert")
        toast = window.findChild(Toast)
        assert toast is not None
        assert toast._label.text() == "Einstellungen gespeichert"
        assert not toast._icon.pixmap().isNull()  # Haekchen-Icon gesetzt

    def test_host_label_strips_scheme(self, qapp: QApplication) -> None:
        """Die Verbindungsmeldung zeigt den Host ohne Schema und Schraegstrich."""
        win = MainWindow(Settings(jira_host="https://firma.atlassian.net/"), Mode.DARK)
        assert win._host_label() == "firma.atlassian.net"

    def test_restore_offer_recovers_access(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fehlt der Zugang und eine Sicherung hat ihn, stellt der Prompt ihn wieder her."""
        from PySide6.QtWidgets import QMessageBox

        # Goldene Kopie mit vollem Zugang anlegen (Ordner via conftest isoliert).
        Settings(jira_host="https://h", email="e@x.de", jira_token="TOK").save()
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        win = MainWindow(Settings(jira_host="https://h"), Mode.DARK)  # Zugang unvollstaendig
        assert not win._settings_complete()
        win._maybe_offer_restore()
        assert win._settings_complete()

    def test_hero_releases_image_when_hidden(self, window: MainWindow) -> None:
        """Das Hintergrundbild wird geladen wenn sichtbar und beim Verbergen freigegeben."""
        from PySide6.QtGui import QHideEvent, QShowEvent

        from jira_timesheet_qt.ui.hero_background import HeroBackground

        hero = window.findChild(HeroBackground)
        assert hero is not None
        assert hero.has_image()
        hero.showEvent(QShowEvent())
        assert not hero._pixmap.isNull()  # sichtbar -> geladen
        hero.hideEvent(QHideEvent())
        assert hero._pixmap.isNull()  # verborgen -> Speicher frei

    def test_ctrl_wheel_zooms(self, window: MainWindow) -> None:
        """Ctrl+Mausrad vergroessert die Oberflaeche (wie im Browser)."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QWheelEvent

        from jira_timesheet_qt.ui.theme import current_scale, set_scale

        try:
            before = current_scale()
            event = QWheelEvent(
                QPoint(10, 10),
                QPoint(10, 10),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            window.wheelEvent(event)
            assert current_scale() > before
        finally:
            set_scale(100)  # sonst zoomt es folgende Tests

    def test_empty_state(self, qapp: QApplication) -> None:
        """Ohne Daten bleibt der Monat in der Toolbar sichtbar."""
        win = MainWindow(Settings(), Mode.DARK)
        win._year, win._month = 2026, 3
        win.set_timesheet(None)
        assert win._month_label.text() == "März 2026"
        assert win._current_entry is None
