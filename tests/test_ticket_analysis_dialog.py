"""Tests fuer den Dialog "Ticket-Analyse".

Kein Netzwerk: der Abruf wird durch eine Attrappe ersetzt. Geprueft wird die
Verdrahtung - Keyerkennung, Freigabe des Knopfes, Schreiben der Datei und der
gemerkte Zielordner.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.i18n import current_language, load_locale
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.ticket_lifecycle import TicketLifecycleData
from jira_timesheet_qt.ui import ticket_analysis_dialog as modul
from jira_timesheet_qt.ui.ticket_analysis_dialog import TicketAnalysisDialog, ticket_key


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Verlegt die Nutzerdateien, damit die echten unberuehrt bleiben."""
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


@pytest.fixture(autouse=True)
def _sprache() -> Iterator[None]:
    """Laedt die deutsche Sprachdatei und stellt sie danach zurueck.

    Ohne geladene Sprache liefert ``t()`` den Schluessel statt des Textes -
    ein Test auf den angezeigten Text wuerde dann nichts pruefen. Die Sprache
    ist globaler Zustand, deshalb wird sie am Ende zurueckgesetzt.
    """
    vorher = current_language()
    load_locale("de")
    yield
    load_locale(vorher)


def _configured() -> Settings:
    """Einstellungen mit vollstaendigem Zugang."""
    return Settings(
        jira_host="https://example.atlassian.net",
        email="person@beispiel.de",
        jira_token="geheim",
    )


def _daten() -> TicketLifecycleData:
    """Rohdaten eines kleinen Tickets."""
    return TicketLifecycleData(
        issue={
            "key": "ABC-1",
            "fields": {
                "summary": "Testticket",
                "created": "2026-07-01T09:00:00.000+0200",
                "updated": "2026-07-02T09:00:00.000+0200",
                "issuetype": {"name": "Story"},
                "priority": {"name": "Medium"},
                "status": {"name": "IN ARBEIT"},
                "reporter": {"displayName": "Muster, Erika"},
                "assignee": {"displayName": "Beispiel, Max"},
            },
        },
        changelog=[
            {
                "created": "2026-07-01T10:00:00.000+0200",
                "author": {"displayName": "Beispiel, Max"},
                "items": [
                    {"field": "status", "fromString": "Offen", "toString": "IN ARBEIT"},
                ],
            }
        ],
        comments=[],
    )


class TestTicketKey:
    """Der Key muss aus jeder Schreibweise fallen."""

    @pytest.mark.parametrize(
        "eingabe",
        [
            "ABC-123",
            "abc-123",
            "  ABC-123  ",
            "https://jira.example.com/browse/ABC-123",
            "https://example.atlassian.net/browse/ABC-123?focusedId=1",
        ],
    )
    def test_erkennt_key(self, eingabe: str) -> None:
        assert ticket_key(eingabe) == "ABC-123"

    @pytest.mark.parametrize("eingabe", ["", "kein Ticket", "1234", "https://example.com/"])
    def test_ohne_key_bleibt_leer(self, eingabe: str) -> None:
        assert ticket_key(eingabe) == ""


class TestDialog:
    """Verdrahtung des Dialogs."""

    def test_knopf_ist_erst_mit_erkanntem_key_frei(self, qapp: QApplication) -> None:
        dialog = TicketAnalysisDialog(_configured())
        assert not dialog._start_button.isEnabled()

        dialog._input.setText("noch nichts")
        assert not dialog._start_button.isEnabled()

        dialog._input.setText("https://jira.example.com/browse/ABC-123")
        assert dialog._start_button.isEnabled()
        assert "ABC-123" in dialog._status.text()

    def test_fehlender_zugang_startet_keinen_abruf(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gestartet: list[str] = []
        monkeypatch.setattr(modul.QMessageBox, "warning", lambda *a, **k: None)
        monkeypatch.setattr(
            modul, "TicketReportWorker", lambda *a, **k: gestartet.append("start")
        )

        dialog = TicketAnalysisDialog(Settings())
        dialog._input.setText("ABC-123")
        dialog._on_start()
        assert gestartet == []

    def test_schreibt_die_datei_und_merkt_den_ordner(
        self, qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ziel = tmp_path / "berichte" / "ABC-1.html"
        ziel.parent.mkdir()
        monkeypatch.setattr(
            modul.QFileDialog, "getSaveFileName", lambda *a, **k: (str(ziel), "")
        )
        monkeypatch.setattr(modul.QMessageBox, "information", lambda *a, **k: None)

        einstellungen = _configured()
        dialog = TicketAnalysisDialog(einstellungen)
        dialog._input.setText("ABC-1")
        dialog._on_data(_daten())

        assert ziel.is_file()
        inhalt = ziel.read_text(encoding="utf-8")
        assert inhalt.startswith("<!doctype html>")
        assert "Testticket" in inhalt
        # Der naechste Bericht soll im selben Ordner vorgeschlagen werden.
        assert einstellungen.last_export_dir == str(ziel.parent)

    def test_abbruch_im_speichern_dialog_schreibt_nichts(
        self, qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(modul.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))

        dialog = TicketAnalysisDialog(_configured())
        dialog._input.setText("ABC-1")
        dialog._on_data(_daten())

        assert list(tmp_path.glob("*.html")) == []


class TestVerdrahtung:
    """Der Aufruf muss in Menue UND Werkzeugleiste stehen."""

    def _fenster(self) -> Any:
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        return MainWindow(Settings(), Mode.DARK)

    def test_steht_im_extras_menue(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QMenu

        fenster = self._fenster()
        treffer = [
            (menu.title(), aktion.text())
            for menu in fenster.menuBar().findChildren(QMenu)
            for aktion in menu.actions()
            if "Ticket-Analyse" in aktion.text()
        ]
        assert treffer, "Ticket-Analyse fehlt im Menue"
        assert treffer[0][0] == "Extras"

    def test_steht_in_der_werkzeugleiste(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QToolBar

        fenster = self._fenster()
        knoepfe = [
            aktion
            for leiste in fenster.findChildren(QToolBar)
            for aktion in leiste.actions()
            if "Ticket-Analyse" in aktion.text()
        ]
        assert knoepfe, "Ticket-Analyse fehlt in der Werkzeugleiste"
        # Ohne Symbol waere der Knopf in der Leiste leer.
        assert not knoepfe[0].icon().isNull()

    def test_kuerzel_ist_eindeutig(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QMenu

        fenster = self._fenster()
        belegt: dict[str, list[str]] = {}
        for menu in fenster.menuBar().findChildren(QMenu):
            for aktion in menu.actions():
                kuerzel = aktion.shortcut().toString()
                if kuerzel:
                    belegt.setdefault(kuerzel, []).append(aktion.text())
        doppelt = {k: v for k, v in belegt.items() if len(v) > 1}
        assert not doppelt, f"doppelt belegte Kuerzel: {doppelt}"
        assert "Ctrl+T" in belegt


class TestClientAufruf:
    """Der Client muss die drei Antworten zusammenfuehren."""

    def test_holt_issue_changelog_und_kommentare(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # asyncio.run statt eines async-Tests: das Projekt bringt kein
        # pytest-asyncio mit, und fuer einen einzelnen Aufruf braucht es das
        # auch nicht.
        from jira_timesheet_qt.services.jira_client import JiraClient

        gerufen: list[str] = []

        class FakeResponse:
            def __init__(self, payload: dict[str, Any]) -> None:
                self._payload = payload
                self.status_code = 200

            def json(self) -> dict[str, Any]:
                return self._payload

        class FakeClient:
            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def get(self, url: str, **kwargs: Any) -> FakeResponse:
                gerufen.append(url)
                if url.endswith("/changelog"):
                    return FakeResponse({"values": [{"created": "x"}], "isLast": True})
                if url.endswith("/comment"):
                    return FakeResponse({"comments": [{"created": "y"}]})
                return FakeResponse({"key": "ABC-1", "fields": {}})

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: FakeClient())
        monkeypatch.setattr(JiraClient, "_check_response", lambda self, r, u: None)

        client = JiraClient(host="https://example.atlassian.net", email="a@b.de", token="x")
        daten = asyncio.run(client.get_ticket_lifecycle("ABC-1"))

        assert daten.key == "ABC-1"
        assert len(daten.changelog) == 1
        assert len(daten.comments) == 1
        assert any(u.endswith("/changelog") for u in gerufen)
        assert any(u.endswith("/comment") for u in gerufen)


def test_zeitzone_bleibt_erhalten() -> None:
    """Der Bericht rechnet in der von Jira gelieferten Ortszeit."""
    from jira_timesheet_qt.services.ticket_report.lifecycle import parse_ts

    moment = parse_ts("2026-07-01T09:00:00.000+0200")
    assert moment is not None
    assert moment.utcoffset() == dt.timedelta(hours=2)


class TestVorbelegung:
    """Aus dem Kontextmenue kommt das Ticket schon mit."""

    def test_dialog_mit_vorbelegtem_ticket(self, qapp: QApplication) -> None:
        # Regression: die Vorbelegung loest textChanged aus. Wurde sie vor dem
        # Aufbau der Knoepfe gesetzt, lief der Handler in ein noch nicht
        # existierendes Attribut (AttributeError beim Oeffnen aus dem
        # Kontextmenue).
        dialog = TicketAnalysisDialog(_configured(), ticket="ABC-123")
        assert dialog._input.text() == "ABC-123"
        assert dialog._start_button.isEnabled()
        assert "ABC-123" in dialog._status.text()

    def test_dialog_ohne_vorbelegung_bleibt_leer(self, qapp: QApplication) -> None:
        dialog = TicketAnalysisDialog(_configured())
        assert dialog._input.text() == ""
        assert not dialog._start_button.isEnabled()
