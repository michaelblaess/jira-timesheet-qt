"""Zu meinem Team hinzufuegen - Kern (gleich in beiden Fassungen) und Qt-Oberflaeche."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.team import Roster, TeamMember, add_person, from_storage, member_of, to_storage
from jira_timesheet_qt.services.ticket_board import AccountIdError, Ticket
from jira_timesheet_qt.ui import main_window
from jira_timesheet_qt.ui.new_tickets_view import NewTicketsView
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.ticket_board_view import TicketBoardView

ID_A = "712020:aaaaaaaa-0000-0000-0000-00000000000a"
ID_B = "712020:bbbbbbbb-0000-0000-0000-00000000000b"
ID_C = "712020:cccccccc-0000-0000-0000-00000000000c"
ANNA = TeamMember(display_name="Beispiel, Anna", account_ids=(ID_A,))


class TestKern:
    def test_neue_person_kommt_sortiert_dazu(self) -> None:
        alt = Roster(members=[ANNA])
        neu, name, added = add_person(alt, ID_B, "Adler, Bea")
        assert added and name == "Adler, Bea"
        assert [m.display_name for m in neu.members] == ["Adler, Bea", "Beispiel, Anna"]
        assert member_of(neu, ID_B) is not None
        # Die alte Liste bleibt unberuehrt.
        assert [m.display_name for m in alt.members] == ["Beispiel, Anna"]

    def test_bekannte_kennung_aendert_nichts(self) -> None:
        alt = Roster(members=[ANNA])
        neu, name, added = add_person(alt, ID_A, "Anders geschrieben")
        assert not added and name == "Beispiel, Anna" and neu is alt

    def test_gleicher_name_andere_person_bekommt_nummer(self) -> None:
        neu, name, added = add_person(Roster(members=[ANNA]), ID_C, "Beispiel, Anna")
        assert added and name == "Beispiel, Anna (2)"
        assert len(neu.members) == 2

    def test_kaputte_kennung_bricht_ab(self) -> None:
        with pytest.raises(AccountIdError):
            add_person(Roster(), 'a" OR 1=1', "X")


def _ticket() -> Ticket:
    return Ticket(
        key="ABC-1",
        assignee="Beispiel, Anna",
        assignee_id=ID_A,
        reporter="Adler, Bea",
        reporter_id=ID_B,
        url="https://jira.example.com/browse/ABC-1",
    )


def _texte(menu: Any) -> list[str]:
    return [action.text() for action in menu.actions() if action.text()]


class TestMenue:
    def test_ticketliste_bietet_fehlende_personen_an(self, qapp: QApplication) -> None:
        view = TicketBoardView("Meine Aktivitäten")
        view.set_team_ids(frozenset({ID_A}))
        texte = _texte(view.build_menu(_ticket()))
        assert "Adler, Bea zu meinem Team hinzufügen" in texte
        # Wer schon im Team steht, bekommt keinen Eintrag.
        assert "Beispiel, Anna zu meinem Team hinzufügen" not in texte
        assert "Tickets von Beispiel, Anna anzeigen" in texte

    def test_eintrag_meldet_kennung_und_name(self, qapp: QApplication) -> None:
        view = TicketBoardView("Meine Aktivitäten")
        gemeldet: list[tuple[str, str]] = []
        view.team_add_requested.connect(lambda a, n: gemeldet.append((a, n)))
        menu = view.build_menu(_ticket())
        next(a for a in menu.actions() if a.text() == "Adler, Bea zu meinem Team hinzufügen").trigger()
        assert gemeldet == [(ID_B, "Adler, Bea")]

    def test_screenshot_modus_bietet_niemanden_an(self, qapp: QApplication) -> None:
        view = TicketBoardView("Meine Aktivitäten")
        view.set_anonymized(True)
        assert not any("hinzufügen" in text for text in _texte(view.build_menu(_ticket())))

    def test_neue_tickets_haben_dieselben_eintraege(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        texte = _texte(view.build_menu(_ticket()))
        assert "Tickets von Adler, Bea anzeigen" in texte
        assert "Adler, Bea zu meinem Team hinzufügen" in texte


class TestHauptfenster:
    def test_hinzufuegen_speichert_und_zieht_alles_nach(self, qapp: QApplication) -> None:
        einstellungen = Settings(jira_host="https://jira.example.com", email="max@example.com", jira_token="geheim")
        einstellungen.team_members = to_storage(Roster(members=[ANNA]))
        fenster = main_window.MainWindow(einstellungen, Mode.DARK)
        fenster.add_person_to_team(ID_B, "Adler, Bea")
        assert [m.display_name for m in from_storage(Settings.load().team_members).members] == [
            "Adler, Bea",
            "Beispiel, Anna",
        ]
        assert fenster._new_tickets._member_box.findData("Adler, Bea") >= 0
        # Jetzt steht sie im Team - das Menue bietet sie nicht mehr an.
        texte = _texte(fenster._relevant_board.build_menu(_ticket()))
        assert "Adler, Bea zu meinem Team hinzufügen" not in texte
        # Ein zweites Mal legt keinen Doppeleintrag an.
        fenster.add_person_to_team(ID_B, "Adler, Bea")
        assert len(from_storage(Settings.load().team_members).members) == 2
