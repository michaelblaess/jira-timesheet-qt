"""Tests fuer Kalender, Jahresansicht, Export und Absturzschutz."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.ui.calendar_view import CalendarView
from jira_timesheet_qt.ui.crash_guard import ErrorDialog, format_report
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.export_service import ExportService
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.year_view import YearView


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


class TestCalendarView:
    def test_grid_covers_whole_weeks(self, qapp: QApplication) -> None:
        """Das Raster beginnt montags und endet sonntags."""
        view = CalendarView()
        view.set_month(2026, 7, demo_timesheet())
        assert len(view.cells) % 7 == 0
        assert view.cells[0].day.weekday() == 0
        assert view.cells[-1].day.weekday() == 6

    def test_hours_land_on_the_right_day(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 7, demo_timesheet())
        cell = next(c for c in view.cells if c.day == date(2026, 7, 20))
        # Drei Buchungen am 20.07.: 2,5 + 1,5 + 4,0
        assert cell.hours == pytest.approx(8.0)
        assert len(cell.entries) == 3

    def test_days_outside_the_month_are_marked(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 7, None)
        assert any(not c.in_month for c in view.cells)
        assert all(c.day.month == 7 for c in view.cells if c.in_month)

    def test_holidays_are_recognised(self, qapp: QApplication) -> None:
        """Der 3. Oktober ist bundesweit Feiertag."""
        view = CalendarView()
        view.set_month(2026, 10, None, "SN")
        cell = next(c for c in view.cells if c.day == date(2026, 10, 3))
        assert cell.holiday
        assert not cell.is_workday

    def test_missing_workdays_are_found(self, qapp: QApplication) -> None:
        """Genau dafuer ist die Ansicht da: Lücken sehen."""
        view = CalendarView()
        view.set_month(2026, 7, demo_timesheet())
        missing = view.missing_workdays()
        assert all(c.hours == 0.0 for c in missing)
        assert all(c.is_workday for c in missing)
        # Der 20.07. ist gebucht und darf nicht auftauchen.
        assert date(2026, 7, 20) not in [c.day for c in missing]

    def test_weekend_is_not_a_workday(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 7, None)
        saturday = next(c for c in view.cells if c.day == date(2026, 7, 25))
        assert saturday.is_weekend
        assert not saturday.is_workday

    def test_week_summaries_carry_kw_and_total(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 7, demo_timesheet())
        summaries = view.week_summaries()
        # Eine Summe je Rasterzeile.
        assert len(summaries) == len(view.cells) // 7
        by_kw = dict(summaries)
        # KW 30 (20.-24.07.): 8,0 + 8,0 + 8,0 + 6,5 + 7,0 = 37,5
        assert by_kw[30] == pytest.approx(37.5)
        # KW 31 (27.-31.07.): 5,5 + 5,0 + 6,0 = 16,5
        assert by_kw[31] == pytest.approx(16.5)

    def test_day_hours_color_reflects_target(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.theme import palette_for

        view = CalendarView()
        view.set_month(2026, 7, demo_timesheet(), "SN", 8.0)
        p = palette_for(view._mode)
        full = next(c for c in view.cells if c.day == date(2026, 7, 20))  # 8,0 h -> Soll erfuellt
        partial = next(c for c in view.cells if c.day == date(2026, 7, 23))  # 6,5 h -> unter Soll
        assert view._hours_color(full, p).name() == QColor(p.green).name()
        assert view._hours_color(partial, p).name() == QColor(p.orange).name()


class TestYearView:
    def test_twelve_months(self, qapp: QApplication) -> None:
        view = YearView()
        view.set_year(2026, {}, {})
        assert len(view.cells) == 12

    def test_hours_and_ratio(self, qapp: QApplication) -> None:
        view = YearView()
        view.set_year(2026, {7: 54.0}, {7: 15}, hours_per_day=8.0)
        july = view.cells[6]
        assert july.hours == pytest.approx(54.0)
        assert july.has_data
        assert 0 < july.ratio < 1

    def test_month_without_data(self, qapp: QApplication) -> None:
        view = YearView()
        view.set_year(2026, {7: 54.0}, {7: 15})
        assert not view.cells[0].has_data
        assert view.cells[0].ratio == 0.0

    def test_ratio_is_capped(self, qapp: QApplication) -> None:
        """Mehr als das Soll gebucht heisst voller Balken, nicht mehr."""
        view = YearView()
        view.set_year(2026, {1: 9999.0}, {1: 5})
        assert view.cells[0].ratio == 1.0

    def test_total(self, qapp: QApplication) -> None:
        view = YearView()
        view.set_year(2026, {1: 10.0, 2: 20.0}, {1: 1, 2: 2})
        assert view.total_hours == pytest.approx(30.0)


class TestExport:
    def test_excel_is_written(self, qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
        service = ExportService(Settings())
        target = tmp_path / "Stundenzettel.xlsx"
        monkeypatch.setattr(service, "_ask_target", lambda *a, **k: str(target))
        result = service.export_excel(demo_timesheet(), None)  # type: ignore[arg-type]
        assert not result.cancelled
        assert Path(result.path).is_file()
        assert Path(result.path).stat().st_size > 0

    def test_pdf_is_written(self, qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
        service = ExportService(Settings())
        target = tmp_path / "Stundenzettel.pdf"
        monkeypatch.setattr(service, "_ask_target", lambda *a, **k: str(target))
        result = service.export_pdf(demo_timesheet(), None)  # type: ignore[arg-type]
        assert not result.cancelled
        assert Path(result.path).is_file()
        assert Path(result.path).read_bytes()[:4] == b"%PDF"

    def test_cancelling_writes_nothing(self, qapp: QApplication, monkeypatch) -> None:
        service = ExportService(Settings())
        monkeypatch.setattr(service, "_ask_target", lambda *a, **k: "")
        assert service.export_excel(demo_timesheet(), None).cancelled  # type: ignore[arg-type]

    def test_print_html_contains_the_entries(self, qapp: QApplication) -> None:
        html = ExportService(Settings()).build_print_html(demo_timesheet())
        assert "PROJ-0" in html
        assert "54,00" in html  # Gesamtsumme mit deutschem Komma
        assert "20.07.2026" in html

    def test_print_html_escapes_markup(self, qapp: QApplication) -> None:
        """Ein Beschreibungstext kann spitze Klammern enthalten."""
        entry = WorklogEntry(
            date=date(2026, 7, 1),
            ticket="X-1",
            summary="<b>Umbau</b> & Test",
            author="A",
            budget="",
            hours=1.0,
        )
        sheet = Timesheet(
            developer="A",
            email="a@b.de",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
            days=[TimesheetDay(date=date(2026, 7, 1), entries=[entry])],
        )
        html = ExportService(Settings()).build_print_html(sheet)
        assert "&lt;b&gt;Umbau&lt;/b&gt;" in html

    def test_export_without_data_is_refused(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(None)
        window.export_excel()
        assert window._status.property("state") == "error"


class TestCrashGuard:
    def test_report_names_version_and_cause(self) -> None:
        try:
            raise ValueError("etwas ging schief")
        except ValueError as exc:
            report = format_report(type(exc), exc, exc.__traceback__)
        assert "jira-timesheet-qt" in report
        assert "ValueError" in report
        assert "etwas ging schief" in report

    def test_dialog_shows_the_report(self, qapp: QApplication) -> None:
        dialog = ErrorDialog("Zeile eins\nZeile zwei")
        assert "Zeile zwei" in dialog._view.toPlainText()


class TestViewsInWindow:
    def test_all_three_views_are_reachable(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        assert window._stack.count() == 3
        for index in range(3):
            window._sidebar.view_changed.emit(index)
            assert window._stack.currentIndex() == index

    def test_data_reaches_calendar_and_year(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._year, window._month = 2026, 7
        window.set_timesheet(demo_timesheet())
        assert any(c.hours > 0 for c in window._calendar.cells)
        assert window._year_view.cells[6].hours == pytest.approx(54.0)

    def test_month_click_switches_to_the_list(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._sidebar.view_changed.emit(2)
        window._on_month_selected(3)
        assert window._month == 3
        assert window._stack.currentIndex() == 0
