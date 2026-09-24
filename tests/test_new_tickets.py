"""Tests fuer den Reiter "Neue Tickets" - Kern, Ansicht und Verdrahtung."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.new_tickets import (
    ALL_MEMBERS,
    build_new_tickets,
    created_label,
    new_tickets_jql,
    visible_tickets,
    window_start,
)
from jira_timesheet_qt.services.team import Roster, TeamMember, to_storage
from jira_timesheet_qt.services.ticket_board import AccountIdError, BoardConfig
from jira_timesheet_qt.ui import main_window
from jira_timesheet_qt.ui.new_tickets_view import ALL_LABEL, COL, NewTicketsView
from jira_timesheet_qt.ui.theme import Mode

ANNA_ID = "712020:aaaaaaaa-0000-0000-0000-000000000001"
ANNA_ALT = "712020:aaaaaaaa-0000-0000-0000-000000000002"
BERT_ID = "712020:bbbbbbbb-0000-0000-0000-000000000003"
ANNA = TeamMember(display_name="Anna", account_ids=(ANNA_ID, ANNA_ALT))
BERT = TeamMember(display_name="Bert", account_ids=(BERT_ID,))

# Dienstag, 22.09.2026 - der Vortag ist ein Montag.
TUESDAY = dt.date(2026, 9, 22)
MONDAY = dt.date(2026, 9, 21)


def issue(key: str, created: str, reporter_id: str, reporter_name: str = "Jira-Name") -> dict[str, Any]:
    """Ein Suchtreffer, wie Jira ihn liefert."""
    return {
        "key": key,
        "fields": {
            "summary": f"Titel {key}",
            "status": {"name": "Offen", "statusCategory": {"key": "new"}},
            "priority": {"name": "Mittel"},
            "issuetype": {"name": "Aufgabe"},
            "reporter": {"accountId": reporter_id, "displayName": reporter_name},
            "assignee": None,
            "created": created,
            "updated": created,
        },
    }


ISSUES = [
    issue("ABC-10", "2026-09-22T08:14:00.000+0200", ANNA_ID),
    issue("ABC-11", "2026-09-21T16:02:00.000+0200", ANNA_ALT),
    issue("ABC-12", "2026-09-18T10:30:00.000+0200", BERT_ID),
    issue("ABC-13", "2026-09-14T09:00:00.000+0200", BERT_ID),
]


def _tickets() -> list[Any]:
    return build_new_tickets(
        ISSUES, [ANNA, BERT], BoardConfig(), dt.datetime(2026, 9, 22, 9, tzinfo=dt.UTC), "https://jira.example.com"
    )


class TestZeitraum:
    def test_dienstag_zeigt_ab_montag(self) -> None:
        assert window_start(TUESDAY, 1) == MONDAY

    def test_montag_zeigt_ab_freitag(self) -> None:
        # Der eigentliche Grund fuer Arbeitstage: rollende 24 h zeigten nur den Sonntag.
        assert window_start(MONDAY, 1) == dt.date(2026, 9, 18)
        assert window_start(MONDAY, 2) == dt.date(2026, 9, 17)

    def test_wochenende_zaehlt_ab_freitag(self) -> None:
        assert window_start(dt.date(2026, 9, 26), 1) == dt.date(2026, 9, 25)

    def test_sieben_arbeitstage(self) -> None:
        assert window_start(TUESDAY, 7) == dt.date(2026, 9, 11)

    def test_feiertage_zaehlen_nicht(self) -> None:
        # Dienstag nach Ostern 2026: Ostermontag und Karfreitag fallen weg.
        feiertage = {dt.date(2026, 4, 3), dt.date(2026, 4, 6)}

        def arbeitstag(day: dt.date) -> bool:
            return day.weekday() < 5 and day not in feiertage

        assert window_start(dt.date(2026, 4, 7), 1, arbeitstag) == dt.date(2026, 4, 2)

    def test_kaputter_kalender_haengt_nicht(self) -> None:
        assert window_start(TUESDAY, 1, lambda _day: False) == MONDAY


class TestAbfrage:
    def test_alle_kennungen_aller_mitglieder(self) -> None:
        jql = new_tickets_jql([ANNA, BERT, ANNA], dt.date(2026, 9, 11))
        assert jql == (
            f'reporter IN ("{ANNA_ID}", "{ANNA_ALT}", "{BERT_ID}") AND created >= "2026-09-11" ORDER BY created DESC'
        )

    def test_ohne_kennungen_keine_abfrage(self) -> None:
        assert new_tickets_jql([TeamMember(display_name="Leer")], TUESDAY) == ""

    def test_kaputte_kennung_bricht_ab(self) -> None:
        with pytest.raises(AccountIdError):
            new_tickets_jql([TeamMember(display_name="X", account_ids=('a" OR 1=1',))], TUESDAY)


class TestAufbereitung:
    def test_neueste_zuerst_mit_namen_aus_der_merkliste(self) -> None:
        tickets = _tickets()
        assert [t.key for t in tickets] == ["ABC-10", "ABC-11", "ABC-12", "ABC-13"]
        # Auch das Zweitkonto fuehrt zum Namen der Merkliste.
        assert [t.reporter for t in tickets] == ["Anna", "Anna", "Bert", "Bert"]
        assert tickets[0].url == "https://jira.example.com/browse/ABC-10"

    def test_doppelte_treffer_einmal(self) -> None:
        tickets = build_new_tickets([*ISSUES, ISSUES[0]], [ANNA, BERT], BoardConfig(), dt.datetime.now(dt.UTC))
        assert len(tickets) == 4

    def test_filter_nach_person_und_zeitraum(self) -> None:
        tickets = _tickets()
        assert [t.key for t in visible_tickets(tickets, ALL_MEMBERS, MONDAY)] == ["ABC-10", "ABC-11"]
        assert [t.key for t in visible_tickets(tickets, "Bert", dt.date(2026, 9, 11))] == ["ABC-12", "ABC-13"]
        assert visible_tickets(tickets, "Bert", MONDAY) == []

    def test_beschriftung_der_anlage(self) -> None:
        tz = dt.timezone(dt.timedelta(hours=2))
        assert created_label(dt.datetime(2026, 9, 22, 8, 14, tzinfo=tz), TUESDAY) == "heute 08:14"
        assert created_label(dt.datetime(2026, 9, 21, 16, 2, tzinfo=tz), TUESDAY) == "gestern 16:02"
        assert created_label(dt.datetime(2026, 9, 18, 10, 30, tzinfo=tz), TUESDAY) == "Fr 18.09. 10:30"
        assert created_label(None, TUESDAY) == ""


def _texte(view: NewTicketsView, spalte: str = "Ticket") -> list[str]:
    tabelle = view._table
    zellen = [tabelle.item(r, COL[spalte]) for r in range(tabelle.rowCount())]
    return [zelle.text() if zelle is not None else "" for zelle in zellen]


class TestAnsicht:
    def test_alle_steht_vorn_und_ist_vorgewaehlt(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        view.set_members(["Anna", "Bert"])
        assert view._member_box.itemText(0) == ALL_LABEL
        assert view.current_member() == ALL_MEMBERS
        assert view.current_window() == "1T"

    def test_filter_wirkt_ohne_neuen_abruf(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        view.set_clock(lambda: TUESDAY)
        view.set_members(["Anna", "Bert"])
        view.set_tickets(_tickets())
        assert _texte(view) == ["ABC-10", "ABC-11"]
        assert _texte(view, "Erstellt") == ["heute 08:14", "gestern 16:02"]
        assert view._count.text() == "2 neue Tickets"
        view._window_buttons["7T"].click()
        assert _texte(view) == ["ABC-10", "ABC-11", "ABC-12", "ABC-13"]
        view.select_member("Bert")
        assert _texte(view) == ["ABC-12", "ABC-13"]
        assert _texte(view, "Erstellt von") == ["Bert", "Bert"]

    def test_leerer_zeitraum_sagt_es(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        view.set_clock(lambda: TUESDAY)
        view.set_members(["Anna", "Bert"])
        view.set_tickets(_tickets())
        view.select_member("Bert")
        assert view._count.text() == "keine neuen Tickets"
        assert view._pages.currentWidget() is view._placeholder

    def test_zeitraum_steht_in_der_kopfzeile(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        view.set_clock(lambda: MONDAY)
        assert view._range.text() == "seit Freitag, 18.09.2026"

    def test_auswahl_bleibt_beim_filterwechsel(self, qapp: QApplication) -> None:
        view = NewTicketsView()
        view.set_clock(lambda: TUESDAY)
        view.set_tickets(_tickets())
        assert view.select_ticket("ABC-11")
        view._window_buttons["3T"].click()
        assert view.current_key() == "ABC-11"


class FakeNewWorker(QObject):
    """Ersetzt den Abruf - haelt fest, womit er gestartet wurde."""

    log = Signal(str)
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    finished = Signal()

    erzeugt: list[FakeNewWorker] = []

    def __init__(
        self,
        settings: Settings,
        config: Any,
        members: list[TeamMember],
        since: dt.date,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.members = members
        self.since = since
        FakeNewWorker.erzeugt.append(self)

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> list[FakeNewWorker]:
    FakeNewWorker.erzeugt = []
    monkeypatch.setattr(main_window, "NewTicketsWorker", FakeNewWorker)
    return FakeNewWorker.erzeugt


def _fenster(team: list[TeamMember] | None = None, **extra: Any) -> Any:
    einstellungen = Settings(jira_host="https://jira.example.com", email="max@example.com", jira_token="geheim")
    einstellungen.team_members = to_storage(Roster(members=list(team or [])))
    for name, value in extra.items():
        setattr(einstellungen, name, value)
    return main_window.MainWindow(einstellungen, Mode.DARK)


class TestHauptfenster:
    def test_reiter_steht_zwischen_team_und_booster(self, qapp: QApplication) -> None:
        # Michael, 24.09.2026: vor den Performance-Booster.
        fenster = _fenster()
        views = main_window._VIEWS
        assert views.index("Neue Tickets") == views.index("Mein Team") + 1
        assert views.index("Performance-Booster") == views.index("Neue Tickets") + 1
        assert fenster._tabs.tabText(main_window._NEW_VIEW).startswith("Neue Tickets")
        assert fenster._stack.widget(main_window._NEW_VIEW) is fenster._new_tickets

    def test_erster_besuch_laedt_einmal_den_laengsten_zeitraum(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA, BERT])
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        assert len(fake) == 1
        assert [m.display_name for m in fake[0].members] == ["Anna", "Bert"]
        assert fake[0].since == fenster._new_tickets.since_longest()
        # Person und Zeitraum filtern lokal, der zweite Besuch laedt nicht.
        fenster._new_tickets._window_buttons["3T"].click()
        fenster._new_tickets.select_member("Bert")
        fenster._tabs.setCurrentIndex(0)
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        assert len(fake) == 1

    def test_leere_merkliste_sagt_wo_man_sie_fuellt(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        assert fake == []
        assert "Mein Team" in fenster._new_tickets._placeholder.text()

    def test_anzahl_steht_im_reiter(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA, BERT])
        fenster._new_tickets.set_clock(lambda: TUESDAY)
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        fake[0].finished_ok.emit(_tickets())
        assert fenster._tabs.tabText(main_window._NEW_VIEW) == "Neue Tickets (2)"

    def test_ueberholter_abruf_wird_verworfen(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA, BERT])
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        fenster._new_tickets.refresh_requested.emit()
        fake[0].finished_ok.emit(_tickets())
        assert fenster._new_tickets.tickets() is None
        fake[1].finished_ok.emit(_tickets()[:1])
        assert [t.key for t in fenster._new_tickets.tickets() or []] == ["ABC-10"]

    def test_fehler_laesst_den_naechsten_besuch_neu_laden(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA])
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        fake[0].failed.emit("HTTP 500")
        assert fenster._new_tickets._placeholder.text() == "HTTP 500"
        fenster._tabs.setCurrentIndex(0)
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        assert len(fake) == 2

    def test_zeitraum_wird_gemerkt(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._new_tickets._window_buttons["7T"].click()
        assert _fenster()._new_tickets.current_window() == "7T"

    def test_screenshot_modus_zeigt_keine_echten_nummern(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA, BERT])
        fenster._new_tickets.set_clock(lambda: TUESDAY)
        fenster._tabs.setCurrentIndex(main_window._NEW_VIEW)
        fake[0].finished_ok.emit(_tickets())
        fenster._toggle_anonymize()
        view = fenster._new_tickets
        sichtbar = " ".join(_texte(view) + _texte(view, "Titel") + _texte(view, "Erstellt von"))
        assert "ABC-" not in sichtbar and "Anna" not in sichtbar
        # Gefiltert wird weiter auf den echten Namen.
        view._window_buttons["7T"].click()
        view.select_member("Bert")
        assert len(_texte(view)) == 2
        fenster._toggle_anonymize()
        assert _texte(view) == ["ABC-12", "ABC-13"]

    def test_vorschau_zieht_mit(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._settings.show_ticket_preview = True
        fenster._stack.setCurrentIndex(main_window._NEW_VIEW)
        assert fenster._new_tickets.preview_host().indexOf(fenster._preview) >= 0

    def test_startet_auf_wunsch_mit_den_neuen_tickets(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([ANNA], start_with_new_tickets=True)
        qapp.processEvents()
        assert fenster._stack.currentIndex() == main_window._NEW_VIEW
        assert len(fake) == 1
        ohne = _fenster([ANNA])
        qapp.processEvents()
        assert ohne._stack.currentIndex() == 0


def test_einstellung_ueberlebt_speichern_und_laden(tmp_path: Path) -> None:
    # conftest verlegt SETTINGS_DIR - hier wird nichts Echtes angefasst.
    Settings(start_with_new_tickets=True).save()
    assert Settings.load().start_with_new_tickets is True
