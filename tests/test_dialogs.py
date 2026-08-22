"""Tests fuer Einstellungen, Haftungshinweis und Leerzustand."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import WorklogEntry
from jira_timesheet_qt.ui.detail_dialog import TicketDetailDialog
from jira_timesheet_qt.ui.disclaimer_dialog import (
    DISCLAIMER_VERSION,
    DUTIES,
    INTRO,
    DisclaimerDialog,
    DisclaimerStore,
)
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.theme import Mode


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Verlegt alle Nutzerdateien, damit die echten unberuehrt bleiben."""
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


def _configured() -> Settings:
    """Einstellungen mit vollstaendigem Zugang."""
    return Settings(
        jira_host="https://beispiel.atlassian.net",
        email="person@beispiel.de",
        jira_token="geheim",
    )


class TestDisclaimerStore:
    def test_no_consent_initially(self, _isolated_settings: Path) -> None:
        store = DisclaimerStore(_isolated_settings / "disclaimer.json")
        assert store.accepted_version is None

    def test_records_the_current_version(self, _isolated_settings: Path) -> None:
        path = _isolated_settings / "disclaimer.json"
        store = DisclaimerStore(path)
        store.record()
        assert store.accepted_version == DISCLAIMER_VERSION
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "accepted_at" in data

    def test_older_version_counts_as_missing(self, _isolated_settings: Path) -> None:
        """Aendert sich der Wortlaut, wird erneut gefragt."""
        path = _isolated_settings / "disclaimer.json"
        path.write_text(json.dumps({"accepted_version": "2020-01-01"}), encoding="utf-8")
        assert DisclaimerStore(path).accepted_version != DISCLAIMER_VERSION

    def test_broken_file_counts_as_missing(self, _isolated_settings: Path) -> None:
        path = _isolated_settings / "disclaimer.json"
        path.write_text("kein json", encoding="utf-8")
        assert DisclaimerStore(path).accepted_version is None


class TestDisclaimerDialog:
    def test_confirm_is_disabled_until_the_box_is_ticked(self, qapp: QApplication) -> None:
        """Ohne Haken darf sich der Hinweis nicht bestaetigen lassen."""
        # Ueber die Objektnamen statt ueber private Felder: die Namen sind
        # der Vertrag der Bibliothek, die Feldnamen dahinter nicht.
        dialog = DisclaimerDialog("Test 1.0", intro=INTRO, duties=DUTIES)
        haken = dialog.findChild(QCheckBox, "disclaimer-agree")
        annehmen = dialog.findChild(QPushButton, "disclaimer-accept")
        assert haken is not None and annehmen is not None
        assert not annehmen.isEnabled()
        haken.setChecked(True)
        assert annehmen.isEnabled()

    def test_text_names_the_foreign_data(self, qapp: QApplication) -> None:
        """Der Kern der Begruendung muss im Text stehen."""
        joined = " ".join(DUTIES)
        assert "Berechtigung des Betreibers" in joined
        assert "Buchungen anderer Personen" in joined


class TestSettingsDialog:
    def test_fields_are_prefilled(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(_configured())
        assert dialog.host.text() == "https://beispiel.atlassian.net"
        assert dialog.email.text() == "person@beispiel.de"

    def test_token_is_masked(self, qapp: QApplication) -> None:
        """Der Token darf nicht im Klartext auf dem Bildschirm stehen."""
        dialog = SettingsDialog(_configured())
        assert dialog.token.echoMode() == dialog.token.EchoMode.Password

    def test_result_takes_over_the_values(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        dialog.host.setText("https://neu.atlassian.net/")
        dialog.email.setText("  neu@beispiel.de  ")
        dialog.token.setText("token")
        result = dialog.result_settings()
        # Abschliessender Schraegstrich und Leerzeichen werden entfernt.
        assert result.jira_host == "https://neu.atlassian.net"
        assert result.email == "neu@beispiel.de"

    def test_empty_budget_field_stays_empty(self, qapp: QApplication) -> None:
        # Kein hartkodierter Default mehr - leer bleibt leer, das Budget-Feld wird
        # dann einfach nicht angefordert (oder per Auto-Erkennung gesetzt).
        dialog = SettingsDialog(Settings())
        dialog.budget_field.setText("")
        assert dialog.result_settings().budget_field == ""

    def test_manual_color_round_trips(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings(manual_entry_color="00FF00"))
        # Vorbelegter Wert steht auf dem Farbknopf.
        assert dialog.farbe_von(dialog.manual_color) == "00FF00"
        assert dialog.result_settings().manual_entry_color == "00FF00"

    def test_color_button_disabled_when_marking_off(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings(mark_manual_entries=False))
        assert dialog.manual_color.isEnabled() is False
        dialog.mark_manual.setChecked(True)
        assert dialog.manual_color.isEnabled() is True

    def test_accent_round_trips(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings(accent="gruen"))
        assert dialog._feld_akzent.currentData() == "gruen"
        assert dialog.result_settings().accent == "gruen"

    def test_all_pages_are_reachable(self, qapp: QApplication) -> None:
        # Die Zahl bewusst NICHT fest verdrahten - sie waechst mit den Seiten
        # mit. Der Fehler, den dieser Test finden soll, ist ein
        # Navigationseintrag ohne Seite (oder umgekehrt).
        dialog = SettingsDialog(Settings())
        assert dialog._nav.count() == dialog._stapel.count()
        assert dialog._nav.count() >= 6
        for row in range(dialog._nav.count()):
            dialog._nav.setCurrentRow(row)
            assert dialog._stapel.currentIndex() == row

    def test_detect_button_disabled_in_legacy_mode(self, qapp: QApplication) -> None:
        """Die Autoerkennung nutzt die Cloud-API - im Data-Center-Modus aus."""
        dialog = SettingsDialog(Settings(use_legacy_api=True))
        assert dialog.detect_budget.isEnabled() is False
        dialog.legacy.setChecked(False)
        assert dialog.detect_budget.isEnabled() is True

    def test_detect_warns_without_credentials(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        calls: list[object] = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
        dialog = SettingsDialog(Settings())  # blank -> kein Zugang
        dialog._detect_budget_field()
        assert calls  # eine Warnung erschien
        assert dialog._detect_worker is None  # kein Faden gestartet

    def test_detect_fills_field_on_single_match(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        dialog = SettingsDialog(_configured())
        dialog._on_budget_found([("customfield_99", "Budget")])
        assert dialog.budget_field.text() == "customfield_99"

    def test_detect_takes_first_of_multiple(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
        dialog = SettingsDialog(_configured())
        dialog._on_budget_found([("cf_1", "Budget A"), ("cf_2", "Budget B")])
        assert dialog.budget_field.text() == "cf_1"

    def test_detect_none_keeps_field(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
        dialog = SettingsDialog(_configured())
        before = dialog.budget_field.text()
        dialog._on_budget_found([])
        assert dialog.budget_field.text() == before


class TestEmptyState:
    def test_asks_for_credentials_when_missing(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(None)
        assert window._empty_button.text() == "Einstellungen öffnen"
        assert "Jira-Zugang" in window._empty_text.text()

    def test_offers_loading_when_configured(self, qapp: QApplication) -> None:
        window = MainWindow(_configured(), Mode.DARK)
        window.set_timesheet(None)
        assert window._empty_button.text() == "Aus Jira laden"

    def test_table_replaces_the_empty_state_once_data_arrives(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.demo import demo_timesheet

        window = MainWindow(_configured(), Mode.DARK)
        window.set_timesheet(None)
        assert window._list_stack.currentIndex() == 0
        window.set_timesheet(demo_timesheet())
        assert window._list_stack.currentIndex() == 1


class TestMonthNavigation:
    def test_stepping_back_from_january_lands_in_december(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._year, window._month = 2026, 1
        window._shift_month(-1)
        assert (window._year, window._month) == (2025, 12)

    def test_stepping_forward_from_december_lands_in_january(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._year, window._month = 2026, 12
        window._shift_month(1)
        assert (window._year, window._month) == (2027, 1)

    def test_header_follows_the_month(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._year, window._month = 2026, 3
        window._update_period_labels()
        assert window._month_label.text() == "März 2026"


class TestStatusBar:
    def test_state_is_kept_for_the_stylesheet(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._set_status("Fehlgeschlagen", "error")
        assert window._status.text() == "Fehlgeschlagen"
        assert window._status.property("state") == "error"

    def test_loading_without_credentials_reports_an_error(self, qapp: QApplication, monkeypatch) -> None:
        """Ohne Zugang darf kein Arbeitsfaden starten."""
        window = MainWindow(Settings(), Mode.DARK)
        monkeypatch.setattr(window, "open_settings", lambda: None)
        window.load_month()
        assert window._status.property("state") == "error"
        assert window._worker is None


def _jira_entry() -> WorklogEntry:
    return WorklogEntry(
        date=date(2026, 7, 23), ticket="PROJ-42", summary="Deployment anpassen",
        author="Mustermann, Max", budget="", hours=4.5, status="IN ARBEIT",
        issuetype="Story", priority="High", assignee="Mustermann, Max",
    )


class TestTicketDetailDialog:
    def test_banner_carries_ticket_and_summary(self, qapp: QApplication) -> None:
        """Der Kopf-Banner traegt das Ticket prominent und die Beschreibung darunter."""
        dialog = TicketDetailDialog(_jira_entry())
        ticket = dialog.findChild(QLabel, "DetailBannerTicket")
        summary = dialog.findChild(QLabel, "DetailBannerSummary")
        assert ticket is not None
        assert "PROJ-42" in ticket.text()
        assert summary is not None
        assert "Deployment anpassen" in summary.text()

    def test_values_include_hours_and_status(self, qapp: QApplication) -> None:
        dialog = TicketDetailDialog(_jira_entry())
        values = " | ".join(
            label.text() for label in dialog.findChildren(QLabel, "DetailDialogValue")
        )
        assert "4,50 h" in values
        assert "IN ARBEIT" in values
        assert "Aus Jira" in values

    def test_link_shown_for_jira_entry(self, qapp: QApplication) -> None:
        dialog = TicketDetailDialog(_jira_entry(), "https://beispiel.atlassian.net")
        link = dialog.findChild(QLabel, "DetailDialogLink")
        assert link is not None
        assert "beispiel.atlassian.net/browse/PROJ-42" in link.text()

    def test_logo_browse_sets_the_path(self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
        """Der Datei-Dialog uebernimmt die gewaehlte Grafik in das Logo-Feld."""
        from PySide6.QtWidgets import QFileDialog

        from jira_timesheet_qt.models.settings import Settings
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("C:/logos/firma.png", ""))
        dialog = SettingsDialog(Settings())
        dialog._browse_logo()
        assert dialog.logo_path.text() == "C:/logos/firma.png"

    def test_no_link_for_manual_entry(self, qapp: QApplication) -> None:
        manual = WorklogEntry(
            date=date(2026, 7, 1), ticket="", summary="Besprechung", author="Ich",
            budget="", hours=1.0, manual=True, manual_id=3,
        )
        dialog = TicketDetailDialog(manual, "https://beispiel.atlassian.net")
        assert dialog.findChild(QLabel, "DetailDialogLink") is None
