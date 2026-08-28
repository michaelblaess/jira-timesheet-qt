"""Tests fuer die Karte im Leerzustand waehrend eines laufenden Abrufs.

Seit der Monatsabruf beim Start von selbst anlaeuft, steht die Karte schon da,
waehrend die Buchungen noch unterwegs sind. Sie behauptete dabei "Keine
Eintraege in diesem Zeitraum" - eine Aussage ueber einen Stand, den zu dem
Zeitpunkt noch niemand kennt - und bot einen Knopf an, der ein zweites Mal
laedt, was ohnehin schon laeuft.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.ui import main_window as mw
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode


class FakeWorker(QObject):
    """Ersetzt den echten Faden: meldet sich als laufend, tut aber nichts."""

    progress = Signal(str)
    log = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, settings: Settings, first: date, last: date, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


def _settings() -> Settings:
    """Vollstaendiger Zugang - sonst bricht der Lader vor dem Abruf ab."""
    s = Settings()
    s.jira_host = "https://beispiel.atlassian.net"
    s.email = "test@example.com"
    s.jira_token = "geheim"
    return s


def _leerer_monat() -> Timesheet:
    """Ein Ergebnis ohne Buchungen - genau der Fall, in dem die Karte stehen bleibt."""
    return Timesheet(
        developer="Testperson",
        email="test@example.com",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        days=[],
    )


class TestLadezustand:
    def test_waehrend_des_abrufs_bittet_die_karte_um_geduld(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()

        assert "geladen" in window._empty_title.text(), (
            f"die Karte behauptet waehrend des Abrufs einen Stand: {window._empty_title.text()!r}"
        )
        assert "Keine Einträge" not in window._empty_title.text()

    def test_der_alte_hinweis_bleibt_beim_naechsten_abruf_nicht_stehen(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Fall aus dem Screenshot: erst ein leerer Monat, dann der naechste.

        Die Karte trug danach weiter "Keine Eintraege in diesem Zeitraum" -
        diesmal aber ueber einen Monat, dessen Buchungen noch unterwegs waren.
        """
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        window._on_loaded(_leerer_monat(), window._load_generation)
        assert "Keine Einträge" in window._empty_title.text(), "Ausgangslage stimmt nicht"

        # Anwender blaettert weiter - der naechste Abruf laeuft an.
        window._month = 7 if window._month != 7 else 6
        window.load_month()

        assert "Keine Einträge" not in window._empty_title.text(), (
            "der Hinweis des vorigen Monats steht noch da, waehrend der naechste laedt"
        )
        assert "geladen" in window._empty_title.text()

    def test_der_knopf_startet_waehrend_des_abrufs_keinen_zweiten(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein Knopf, der anbietet was gerade laeuft, ist eine Einladung zum Doppelklick."""
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()

        assert window._empty_button.isEnabled() is False

    def test_nach_einem_leeren_ergebnis_steht_wieder_der_normale_hinweis(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Ladehinweis darf nicht haengenbleiben - sonst wartet man ewig."""
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        window._on_loaded(_leerer_monat(), window._load_generation)

        assert "Keine Einträge" in window._empty_title.text()
        assert window._empty_button.isEnabled() is True

    def test_nach_einem_fehlschlag_ist_der_knopf_wieder_bedienbar(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        window._on_failed("Verbindung fehlgeschlagen", window._load_generation)

        assert "Keine Einträge" in window._empty_title.text()
        assert window._empty_button.isEnabled() is True

    def test_ein_faden_ohne_ergebnis_laesst_die_karte_nicht_haengen(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Netz: meldet der Faden weder Ergebnis noch Fehler, endet er trotzdem."""
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        window._on_worker_done(window._load_generation)

        assert window._empty_button.isEnabled() is True
        assert "geladen" not in window._empty_title.text()

    def test_ohne_zugang_bleibt_es_beim_hinweis_auf_die_einstellungen(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Ladezustand darf den Zugangs-Hinweis nicht verdraengen."""
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(Settings(), Mode.DARK)

        window._update_empty_state()

        assert "Noch keine Daten" in window._empty_title.text()
        assert window._empty_button.isEnabled() is True
