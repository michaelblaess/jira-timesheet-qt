"""Tests fuer den Anonymisierungs-Modus (Screenshots).

Deckt drei Ebenen ab: die reine Anonymisierung eines Stundenzettels, die
Zensur-Zuordnung fuer das Meldungsfenster und die Verdrahtung im Hauptfenster
(Umschalten ersetzt Daten und Host, Zurueckschalten stellt sie wieder her).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.anonymizer import (
    FAKE_EMAIL,
    FAKE_HOST,
    anonymize_timesheet,
    log_censor_map,
)
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.log_dock import LogDock
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode

REAL_HOST = "https://jira.intern.example/"
REAL_EMAIL = "vorname.nachname@example.com"


class TestAnonymizeTimesheet:
    def test_structure_and_hours_are_preserved(self) -> None:
        real = demo_timesheet()
        anon = anonymize_timesheet(real)
        assert len(anon.days) == len(real.days)
        assert anon.total_hours == pytest.approx(real.total_hours)
        for real_day, anon_day in zip(real.days, anon.days, strict=True):
            assert anon_day.date == real_day.date
            assert len(anon_day.entries) == len(real_day.entries)
            assert anon_day.total_hours == pytest.approx(real_day.total_hours)

    def test_identifying_fields_are_replaced(self) -> None:
        anon = anonymize_timesheet(demo_timesheet())
        assert anon.email == FAKE_EMAIL
        # Alle vergebenen Ticketnummern liegen im Dummy-Bereich (>= 1001),
        # klar getrennt von den Demo-Nummern (101..113).
        for entry in anon.all_entries:
            number = int(entry.ticket.rsplit("-", 1)[1])
            assert number >= 1001

    def test_same_ticket_maps_consistently(self) -> None:
        # Beide manuellen Demo-Eintraege tragen dasselbe Ticket ("MANUELL") -
        # sie muessen auf dieselbe Dummy-Nummer abgebildet werden.
        real = demo_timesheet()
        manual = [e for e in real.all_entries if e.ticket == "MANUELL"]
        assert len(manual) >= 2
        anon = anonymize_timesheet(real)
        anon_manual = [
            a.ticket
            for r, a in zip(real.all_entries, anon.all_entries, strict=True)
            if r.ticket == "MANUELL"
        ]
        assert len(set(anon_manual)) == 1

    def test_is_deterministic(self) -> None:
        first = anonymize_timesheet(demo_timesheet())
        second = anonymize_timesheet(demo_timesheet())
        assert [e.ticket for e in first.all_entries] == [e.ticket for e in second.all_entries]
        assert [e.summary for e in first.all_entries] == [e.summary for e in second.all_entries]

    def test_original_is_untouched(self) -> None:
        real = demo_timesheet()
        tickets_before = [e.ticket for e in real.all_entries]
        anonymize_timesheet(real)
        assert [e.ticket for e in real.all_entries] == tickets_before


class TestLogCensorMap:
    def test_maps_host_and_email(self) -> None:
        mapping = log_censor_map(REAL_EMAIL, REAL_HOST)
        assert mapping["https://jira.intern.example"] == FAKE_HOST
        assert mapping["jira.intern.example"] == "jira.example.com"
        assert mapping[REAL_EMAIL] == FAKE_EMAIL

    def test_longest_key_first(self) -> None:
        # Der Host mit Schema muss vor dem blossen Hostnamen ersetzt werden.
        keys = list(log_censor_map(REAL_EMAIL, REAL_HOST))
        lengths = [len(k) for k in keys]
        assert lengths == sorted(lengths, reverse=True)

    def test_empty_inputs_yield_empty_map(self) -> None:
        assert log_censor_map("", "") == {}


class TestLogDockCensor:
    def test_existing_and_new_lines_are_censored(self, qapp: QApplication) -> None:
        dock = LogDock()
        dock.write(f"Verbunden mit {REAL_HOST}")
        dock.set_censor(log_censor_map(REAL_EMAIL, REAL_HOST))
        assert "jira.intern.example" not in dock.plain_text()
        assert "jira.example.com" in dock.plain_text()
        # Auch spaeter geschriebene Zeilen werden zensiert.
        dock.write(f"Anfrage von {REAL_EMAIL}")
        assert REAL_EMAIL not in dock.plain_text()
        assert FAKE_EMAIL in dock.plain_text()

    def test_clearing_censor_restores_plaintext(self, qapp: QApplication) -> None:
        dock = LogDock()
        dock.write(f"Verbunden mit {REAL_HOST}")
        dock.set_censor(log_censor_map(REAL_EMAIL, REAL_HOST))
        dock.set_censor({})
        assert "jira.intern.example" in dock.plain_text()


@pytest.fixture
def window(qapp: QApplication) -> MainWindow:
    """Hauptfenster mit echtem Zugang und Demodaten."""
    settings = Settings()
    settings.jira_host = REAL_HOST
    settings.email = REAL_EMAIL
    win = MainWindow(settings, Mode.DARK)
    win.set_timesheet(demo_timesheet())
    return win


class TestMainWindowAnonymize:
    def test_toggle_replaces_data_and_host(self, window: MainWindow) -> None:
        real_ticket = window._model.entry_at(0).ticket
        window._toggle_anonymize()
        # Ansicht zeigt jetzt Dummy-Daten.
        assert window._anonymize is True
        # isVisible() ist headless immer False (Fenster nie gezeigt) - isHidden()
        # spiegelt den explizit gesetzten Zustand.
        assert window._anon_badge.isHidden() is False
        assert window._model.entry_at(0).ticket != real_ticket
        assert window._timesheet.email == FAKE_EMAIL
        # Host in Status und Detail-Dialog ist verschleiert.
        assert window._display_host() == FAKE_HOST
        assert window._host_label() == "jira.example.com"
        # Die echten Rohdaten bleiben erhalten.
        assert window._real_ts.all_entries[0].ticket == real_ticket

    def test_toggle_off_restores_real_data(self, window: MainWindow) -> None:
        real_ticket = window._model.entry_at(0).ticket
        window._toggle_anonymize()
        window._toggle_anonymize()
        assert window._anonymize is False
        assert window._anon_badge.isHidden() is True
        assert window._model.entry_at(0).ticket == real_ticket
        assert window._display_host() == REAL_HOST

    def test_command_reflects_state(self, window: MainWindow) -> None:
        command = window._commands.get("view.anonymize")
        assert command.is_checked is not None
        assert command.is_checked() is False
        window._toggle_anonymize()
        assert command.is_checked() is True
