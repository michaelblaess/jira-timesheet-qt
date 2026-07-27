"""Tests fuer die neu ergaenzten Bausteine der manuellen Zeiten in Qt:
Aufwand-Parser, Legacy-Import der TUI-Datenbank und der Erfassungsdialog.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from jira_timesheet_qt.i18n import load_locale
from jira_timesheet_qt.services.hours_parser import parse_hours
from jira_timesheet_qt.services.manual_entry_service import ManualEntry, ManualEntryService


@pytest.fixture(autouse=True)
def _german() -> None:
    load_locale("de")


class TestParseHours:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("3,5", 3.5),
            ("3.5", 3.5),
            ("3", 3.0),
            ("3:30", 3.5),
            ("0:15", 0.25),
            ("3h 30m", 3.5),
            ("3h30m", 3.5),
            ("2h", 2.0),
            ("90m", 1.5),
            ("  4  ", 4.0),
        ],
    )
    def test_valid(self, text: str, expected: float) -> None:
        result = parse_hours(text)
        assert result is not None
        assert abs(result - expected) < 1e-9

    @pytest.mark.parametrize("text", ["", "   ", "abc", "0", "-2", "0:00", "x:30"])
    def test_invalid(self, text: str) -> None:
        assert parse_hours(text) is None


class TestLegacyImport:
    def _make_legacy_db(self, path: Path, rows: int) -> None:
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE manual_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                ticket TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                customer TEXT NOT NULL DEFAULT '',
                hours REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        for i in range(rows):
            conn.execute(
                "INSERT INTO manual_entries (entry_date, ticket, summary, customer, hours) VALUES (?,?,?,?,?)",
                (f"2026-07-{i + 1:02d}", f"PROJ-{i}", "Arbeit", "Corporate", 1.5),
            )
        conn.commit()
        conn.close()

    def test_import_when_empty(self, tmp_path: Path) -> None:
        legacy = tmp_path / "legacy.db"
        self._make_legacy_db(legacy, 3)
        with ManualEntryService(db_path=tmp_path / "own.db") as service:
            assert service.import_from_legacy(legacy) == 3
            assert service.count() == 3

    def test_no_import_when_own_has_entries(self, tmp_path: Path) -> None:
        legacy = tmp_path / "legacy.db"
        self._make_legacy_db(legacy, 3)
        with ManualEntryService(db_path=tmp_path / "own.db") as service:
            service.add(ManualEntry(entry_date=date(2026, 7, 1), hours=2.0, customer="Vertrieb"))
            assert service.import_from_legacy(legacy) == 0
            assert service.count() == 1

    def test_no_import_when_legacy_missing(self, tmp_path: Path) -> None:
        with ManualEntryService(db_path=tmp_path / "own.db") as service:
            assert service.import_from_legacy(tmp_path / "nope.db") == 0
            assert service.count() == 0


class TestManualEntryDialog:
    def test_new_entry_reads_fields(self, qapp: object) -> None:
        from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog

        dialog = ManualEntryDialog(
            customers=["Vertrieb", "Corporate"],
            default_customer="Vertrieb",
            default_date=date(2026, 7, 15),
        )
        dialog.ticket.setText("PROJ-0")
        dialog.summary.setText("Doku")
        dialog.customer.setCurrentText("Corporate")
        dialog.hours.setText("3h 30m")
        dialog._on_save()

        entry = dialog.result_entry()
        assert entry is not None
        assert entry.entry_date == date(2026, 7, 15)
        assert entry.ticket == "PROJ-0"
        assert entry.customer == "Corporate"
        assert abs(entry.hours - 3.5) < 1e-9

    def test_invalid_hours_blocks_result(self, qapp: object) -> None:
        from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog

        dialog = ManualEntryDialog(customers=["Vertrieb"], default_customer="Vertrieb")
        dialog.hours.setText("keine zahl")
        # _build_entry() validiert ohne modalen Dialog (der wuerde den Test blockieren).
        assert dialog._build_entry() is None

    def test_edit_prefills_and_keeps_id(self, qapp: object) -> None:
        from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog

        existing = ManualEntry(
            entry_date=date(2026, 6, 10), ticket="PROJ-0", summary="x", customer="Corporate", hours=2.0, entry_id=7
        )
        dialog = ManualEntryDialog(customers=["Vertrieb", "Corporate"], default_customer="Vertrieb", entry=existing)
        assert dialog.ticket.text() == "PROJ-0"
        dialog.hours.setText("4,25")
        dialog._on_save()

        entry = dialog.result_entry()
        assert entry is not None
        assert entry.entry_id == 7
        assert abs(entry.hours - 4.25) < 1e-9
