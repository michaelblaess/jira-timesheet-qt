"""Tests fuer den Zeitraumwechsel waehrend eines laufenden Abrufs.

Frueher kehrte load_month() bei laufendem Faden wortlos zurueck. Zwei Folgen:
der Zeitraumwechsel wurde stillschweigend verschluckt (die Kopfzeile zeigte den
neuen Monat, geladen wurde er nie), und das spaeter eintreffende Ergebnis des
alten Abrufs landete ungeprueft in einer Ansicht, die laengst einen anderen
Monat zeigte.

Ein QThread laesst sich nicht abbrechen - der ueberholte Faden laeuft also zu
Ende. Verworfen wird sein Ergebnis anhand einer laufenden Abruf-Nummer.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui import main_window as mw
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode


class FakeWorker(QObject):
    """Ersetzt den echten Faden: meldet sich als laufend, tut aber nichts."""

    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    finished = Signal()

    erzeugt: list[tuple[date, date]] = []

    def __init__(self, settings: Settings, first: date, last: date, parent: QObject | None = None) -> None:
        super().__init__(parent)
        FakeWorker.erzeugt.append((first, last))

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeWorker.erzeugt = []


def _settings() -> Settings:
    """Vollstaendiger Zugang - sonst bricht der Lader vorher ab."""
    s = Settings()
    s.jira_host = "https://beispiel.atlassian.net"
    s.email = "test@example.com"
    s.jira_token = "geheim"
    return s


class TestZeitraumwechsel:
    def test_wechsel_waehrend_des_abrufs_startet_neuen_abruf(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Kernfall: der zweite Abruf darf nicht verschluckt werden."""
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        assert len(FakeWorker.erzeugt) == 1, "erster Abruf startet nicht"

        # Zeitraumwechsel, waehrend der erste Faden noch laeuft.
        window._month = 7 if window._month != 7 else 6
        window.load_month()

        assert len(FakeWorker.erzeugt) == 2, (
            "der Zeitraumwechsel wurde verschluckt - die Kopfzeile zeigt den "
            "neuen Monat, geladen wird er nie"
        )
        assert FakeWorker.erzeugt[0] != FakeWorker.erzeugt[1]

    def test_jahresabruf_wird_ebenfalls_nicht_verschluckt(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mw, "WorklogWorker", FakeWorker)
        window = MainWindow(_settings(), Mode.DARK)

        window.load_month()
        window.load_year()

        assert len(FakeWorker.erzeugt) == 2


class TestVeralteteErgebnisse:
    def test_ergebnis_eines_ueberholten_abrufs_wird_verworfen(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein spaet eintreffender Abruf darf die Ansicht nicht ueberschreiben."""
        window = MainWindow(_settings(), Mode.DARK)
        angezeigt: list[object] = []
        monkeypatch.setattr(
            MainWindow, "set_timesheet", lambda self, ts: angezeigt.append(ts)
        )

        window._load_generation = 7
        window._on_loaded(demo_timesheet(), 3)
        assert angezeigt == [], "veraltetes Ergebnis landete in der Ansicht"

        window._on_loaded(demo_timesheet(), 7)
        assert len(angezeigt) == 1, "das aktuelle Ergebnis fehlt"

    def test_fehler_eines_ueberholten_abrufs_wird_verworfen(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sonst leert ein alter Fehlschlag die frisch geladene Ansicht."""
        window = MainWindow(_settings(), Mode.DARK)
        geleert: list[object] = []
        monkeypatch.setattr(
            MainWindow, "set_timesheet", lambda self, ts: geleert.append(ts)
        )

        window._load_generation = 4
        window._on_failed("Netzwerkfehler", 2)
        assert geleert == []

    def test_fortschritt_eines_ueberholten_abrufs_wird_verworfen(
        self, qapp: QApplication
    ) -> None:
        """Sonst ueberschreibt der alte Faden die Statusmeldung des neuen."""
        window = MainWindow(_settings(), Mode.DARK)
        window._load_generation = 5
        window._set_status("Lade August 2026 ...", "busy")
        vorher = window._status.text()

        window._on_progress("Lade Juli 2026 ...", 2)
        assert window._status.text() == vorher

    def test_direkter_aufruf_ohne_nummer_bleibt_erlaubt(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne Nummer (Tests, Direktaufrufe) wird nichts verworfen."""
        window = MainWindow(_settings(), Mode.DARK)
        angezeigt: list[object] = []
        monkeypatch.setattr(
            MainWindow, "set_timesheet", lambda self, ts: angezeigt.append(ts)
        )

        window._load_generation = 9
        window._on_loaded(demo_timesheet())
        assert len(angezeigt) == 1
