"""Tests der Oberflaeche des Teamflows - Stern, Schalter, Ticketliste, Verdrahtung.

Alle Namen sind erfunden. Der Stern rechnet mit einem festen "heute", das
Fenster mit dem echten - dort wird der Zeitraum deshalb aus flow_since
abgeleitet statt als Datum hingeschrieben.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.team import Roster, TeamMember, to_storage
from jira_timesheet_qt.services.ticket_flow import (
    EDGE_ACCEPTANCE,
    EDGE_HANDOVER,
    EDGE_ORDER,
    FLOW_12M,
    FLOW_ALL,
    FlowLoad,
    extract_flow,
    flow_since,
)
from jira_timesheet_qt.ui import main_window
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.ticket_flow_view import GUEST, TicketFlowView, _Arrow, _Node, initials
from tests.test_ticket_flow import ANNA, BERT, CARL, DORA, handover, issue

TODAY = dt.date(2026, 10, 26)


def at(day: int, month: int) -> str:
    """Zeitstempel im Jira-Format, 2026."""
    return dt.datetime(2026, month, day, 9, tzinfo=dt.UTC).isoformat()


def _abruf(since: dt.date | None = None) -> FlowLoad:
    """Anna in der Mitte: gibt Bert im Oktober, bekommt von Dora im Maerz und von Carl im Oktober."""
    issues = [
        issue("X-1", ANNA, BERT, at(1, 10)),
        issue("X-2", DORA, ANNA, at(1, 3)),
        issue("X-3", CARL, CARL, at(5, 10)),
        issue("X-9", ANNA, BERT, at(2, 10)),
    ]
    issues[0]["fields"]["summary"] = "Kaffeemaschine entkalken"
    issues[0]["fields"]["assignee"]["avatarUrls"] = {"48x48": "https://bilder.example/bert"}
    histories: dict[str, list[dict[str, Any]]] = {
        "X-1": [],
        "X-2": [],
        "X-3": [handover(at(10, 10), CARL, ANNA)],
    }
    return FlowLoad((ANNA,), since, extract_flow(issues, histories), cached=0, fetched=3)


def _view() -> TicketFlowView:
    view = TicketFlowView(Mode.DARK, today=TODAY)
    view.resize(900, 600)
    view.set_flow(_abruf())
    return view


def _namen(view: TicketFlowView) -> list[str]:
    star = view.star()
    assert star is not None
    return [s.person.name for s in star.spokes if s.person is not None]


def _items(view: TicketFlowView, kind: type) -> list[Any]:
    return [item for item in view._scene.items() if isinstance(item, kind)]


class TestStern:
    def test_alle_wege_im_vorgabezeitraum(self, qapp: QApplication) -> None:
        assert _namen(_view()) == ["Bert Beispiel", "Carl Mustermann", "Dora Probe"]

    def test_zeitraum_schneidet_ohne_neuen_abruf(self, qapp: QApplication) -> None:
        view = _view()
        gemeldet: list[str] = []
        view.period_changed.connect(gemeldet.append)
        view._period_buttons["1M"].click()
        # Doras Auftrag stammt aus dem Maerz.
        assert _namen(view) == ["Bert Beispiel", "Carl Mustermann"]
        assert gemeldet == ["1M"]

    def test_pfeilart_abschaltbar(self, qapp: QApplication) -> None:
        view = _view()
        view._kind_buttons[EDGE_ACCEPTANCE].click()
        view._kind_buttons[EDGE_HANDOVER].click()
        assert _namen(view) == ["Bert Beispiel", "Dora Probe"]
        assert view.current_kinds() == (EDGE_ORDER,)

    def test_die_letzte_pfeilart_bleibt_an(self, qapp: QApplication) -> None:
        view = _view()
        view._kind_buttons[EDGE_ACCEPTANCE].click()
        view._kind_buttons[EDGE_HANDOVER].click()
        view._kind_buttons[EDGE_ORDER].click()
        assert view.current_kinds() == (EDGE_ORDER,)
        assert view._kind_buttons[EDGE_ORDER].isChecked()

    def test_ein_pfeil_je_richtung_mit_wegen(self, qapp: QApplication) -> None:
        # Bert bekommt, Carl und Dora geben - drei Pfeile, keiner fuer leere Richtungen.
        assert len(_items(_view(), _Arrow)) == 3

    def test_pfeilklick_zeigt_tickets_mit_titel(self, qapp: QApplication) -> None:
        view = _view()
        bert = next(s for s in view.star().spokes if s.person and s.person.account_id == BERT)  # type: ignore[union-attr]
        view.show_tickets(bert, "out")
        assert view.listed_keys() == ["X-1"]
        assert view._list.topLevelItem(0).text(1) == "Kaffeemaschine entkalken"  # type: ignore[union-attr]
        assert view._list_title.text() == "Anna Muster an Bert Beispiel: 1 Ticket"

    def test_jeder_pfeil_ist_klickbar(self, qapp: QApplication) -> None:
        view = _view()
        for arrow in _items(view, _Arrow):
            arrow._on_click()
            assert view.listed_keys()

    def test_klick_auf_person_meldet_kennung_und_namen(self, qapp: QApplication) -> None:
        view = _view()
        gemeldet: list[tuple[str, str]] = []
        view.person_clicked.connect(lambda account, name: gemeldet.append((account, name)))
        for node in _items(view, _Node):
            if node._on_click is not None:
                node._on_click()
        assert sorted(gemeldet) == [(BERT, "Bert Beispiel"), (CARL, "Carl Mustermann"), (DORA, "Dora Probe")]

    def test_keine_fusszeile_mehr(self, qapp: QApplication) -> None:
        assert not hasattr(_view(), "_footer")

    def test_legende_sagt_ausgehend_und_eingehend(self, qapp: QApplication) -> None:
        text = _view()._legend.text()
        assert "ausgehend" in text and "eingehend" in text

    def test_trenner_unter_der_kopfzeile(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QFrame

        rule = _view().findChild(QFrame, "FlowRule")
        assert rule is not None and rule.frameShape() == QFrame.Shape.HLine

    def test_zoom_sind_echte_knoepfe_mit_reset(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QPushButton

        view = _view()
        assert all(isinstance(b, QPushButton) for b in view._zoom_buttons.values())
        assert view._zoom_buttons["fit"].text() == "Reset"
        assert not view._zoom_buttons["in"].icon().isNull()

    def test_hinweis_raeumt_den_alten_stern_weg(self, qapp: QApplication) -> None:
        view = _view()
        view.show_message("Teamflow wird geladen ...")
        assert view.star() is None and view.flow() is None
        assert view._scene.items() == []

    def test_themewechsel_zeichnet_neu(self, qapp: QApplication) -> None:
        view = _view()
        vorher = len(view._scene.items())
        view.apply_mode(Mode.LIGHT)
        assert len(view._scene.items()) == vorher


def _png() -> bytes:
    """Ein kleines Bild, wie es aus der Bildablage kaeme."""
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor("#336699"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(data.data())


class TestMehrfachkonten:
    def test_konten_aus_der_merkliste_sind_eine_speiche(self, qapp: QApplication) -> None:
        view = _view()
        view.set_account_groups([(BERT, CARL), (DORA,)])
        assert _namen(view) == ["Bert Beispiel", "Dora Probe"]
        star = view.star()
        assert star is not None
        assert (star.spokes[0].outgoing, star.spokes[0].incoming) == (("X-1",), ("X-3",))

    def test_neuer_abruf_behaelt_die_gruppen(self, qapp: QApplication) -> None:
        view = _view()
        view.set_account_groups([(BERT, CARL)])
        view.set_flow(_abruf())
        assert _namen(view) == ["Bert Beispiel", "Dora Probe"]

    def test_hauptfenster_reicht_die_merkliste_durch(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster([TeamMember(display_name="Bert", account_ids=(BERT, CARL))])
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        assert _namen(fenster._ticket_flow) == ["Bert Beispiel", "Dora Probe"]


class TestZoomUndHover:
    def test_knoepfe_zoomen_und_einpassen(self, qapp: QApplication) -> None:
        view = _view()
        view._zoom_buttons["in"].click()
        assert view.zoom_level() == pytest.approx(1.15)
        view._zoom_buttons["out"].click()
        view._zoom_buttons["out"].click()
        assert view.zoom_level() == pytest.approx(1 / 1.15)
        view._zoom_buttons["fit"].click()
        assert view.zoom_level() == pytest.approx(1.0)

    def test_zoom_hat_grenzen(self, qapp: QApplication) -> None:
        view = _view()
        for _ in range(40):
            view._zoom_buttons["in"].click()
        assert view.zoom_level() == pytest.approx(5.0)

    def test_hover_auf_person_blendet_den_rest_aus(self, qapp: QApplication) -> None:
        view = _view()
        bert = next(n for n in _items(view, _Node) if "Bert" in n.toolTip())
        bert._on_hover(True)
        hell = [i for i in view._dimmable if i.opacity() == 1.0]
        # Bert: Kreis, Initialen, Name, ein Pfeil und seine Zahl.
        assert len(hell) == 5
        assert all(i.opacity() < 1.0 for i in view._dimmable if i not in hell)
        bert._on_hover(False)
        assert all(i.opacity() == 1.0 for i in view._dimmable)

    def test_hover_auf_pfeil_hebt_seine_speiche(self, qapp: QApplication) -> None:
        view = _view()
        arrow = _items(view, _Arrow)[0]
        arrow._on_hover(True)
        assert arrow.opacity() == 1.0
        assert any(i.opacity() < 1.0 for i in view._dimmable)


class TestKontakte:
    def test_drei_kontakte_bei_gleichstand_nach_namen(self, qapp: QApplication) -> None:
        assert _view().contact_names() == ["Bert Beispiel", "Carl Mustermann", "Dora Probe"]

    def test_klick_zeigt_gemeinsame_tickets(self, qapp: QApplication) -> None:
        view = _view()
        view._on_contact_clicked(view._contacts.topLevelItem(0))  # type: ignore[arg-type]
        assert view.listed_keys() == ["X-1"]
        assert view._list_title.text() == "Anna Muster und Bert Beispiel: 1 Ticket"

    def test_doppelklick_setzt_in_die_mitte(self, qapp: QApplication) -> None:
        view = _view()
        gemeldet: list[tuple[str, str]] = []
        view.person_clicked.connect(lambda account, name: gemeldet.append((account, name)))
        view._on_contact_activated(view._contacts.topLevelItem(2))  # type: ignore[arg-type]
        assert gemeldet == [(DORA, "Dora Probe")]

    def test_zeitraum_wirkt_auch_auf_die_kontakte(self, qapp: QApplication) -> None:
        view = _view()
        view._period_buttons["1M"].click()
        assert view.contact_names() == ["Bert Beispiel", "Carl Mustermann"]


class TestProfilbilder:
    @pytest.mark.parametrize(
        ("name", "kurz"),
        [("Michael Blaess", "MB"), ("Blaess, Michael", "MB"), ("Anna-Lena Muster", "AM"), ("Cher", "CH"), ("", "?")],
    )
    def test_initialen(self, name: str, kurz: str) -> None:
        assert initials(name) == kurz

    def test_fehlende_bilder_werden_einmal_erfragt(self, qapp: QApplication) -> None:
        view = TicketFlowView(Mode.DARK, today=TODAY)
        gefragt: list[list[str]] = []
        view.avatars_needed.connect(gefragt.append)
        view.set_flow(_abruf())
        view._period_buttons["1M"].click()
        assert gefragt == [[ANNA, BERT, CARL, DORA]]

    def test_bild_ersetzt_die_initialen(self, qapp: QApplication) -> None:
        view = _view()
        assert _items(view, QGraphicsPixmapItem) == []
        view.set_avatars({BERT: _png()})
        assert len(_items(view, QGraphicsPixmapItem)) == 1

    def test_kaputte_bilddaten_fallen_auf_initialen_zurueck(self, qapp: QApplication) -> None:
        view = _view()
        view.set_avatars({BERT: b"kein Bild"})
        assert _items(view, QGraphicsPixmapItem) == []

    def test_screenshot_modus_ohne_bilder(self, qapp: QApplication) -> None:
        view = TicketFlowView(Mode.DARK, today=TODAY)
        gefragt: list[list[str]] = []
        view.avatars_needed.connect(gefragt.append)
        view.set_anonymized(True)
        view.set_flow(_abruf())
        view.set_avatars({BERT: _png()})
        assert gefragt == []
        assert _items(view, QGraphicsPixmapItem) == []


class TestGast:
    def test_gast_steht_hinten_und_bleibt_beim_neufuellen(self, qapp: QApplication) -> None:
        view = _view()
        view.set_members(["Bert Beispiel"])
        view.set_guest("Dora Probe")
        assert view.current_member() == GUEST
        view.set_members(["Bert Beispiel", "Carl Mustermann"])
        assert view.current_member() == GUEST
        assert view._member_box.itemText(view._member_box.count() - 1) == "Dora Probe"


class FakeFlowWorker(QObject):
    """Ersetzt den echten Faden. Merkt sich Person und Untergrenze."""

    progress = Signal(str)
    log = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    finished = Signal()

    erzeugt: list[FakeFlowWorker] = []

    def __init__(
        self,
        settings: Settings,
        member: TeamMember | None,
        since: dt.date | None,
        cache_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.member = member
        self.since = since
        self.cache_dir = cache_dir
        FakeFlowWorker.erzeugt.append(self)

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


class FakeAvatarWorker(QObject):
    """Ersetzt den Bilder-Faden. Merkt sich, was gewuenscht war."""

    finished_ok = Signal(object)
    log = Signal(str)
    finished = Signal()

    erzeugt: list[FakeAvatarWorker] = []

    def __init__(
        self, settings: Settings, wanted: dict[str, str], cache_dir: Path, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.wanted = dict(wanted)
        self.cache_dir = cache_dir
        FakeAvatarWorker.erzeugt.append(self)

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> list[FakeFlowWorker]:
    FakeFlowWorker.erzeugt = []
    FakeAvatarWorker.erzeugt = []
    monkeypatch.setattr(main_window, "TicketFlowWorker", FakeFlowWorker)
    monkeypatch.setattr(main_window, "AvatarWorker", FakeAvatarWorker)
    return FakeFlowWorker.erzeugt


def _fenster(team: list[TeamMember] | None = None) -> Any:
    einstellungen = Settings(jira_host="https://jira.example.com", email="max@example.com", jira_token="geheim")
    einstellungen.team_members = to_storage(Roster(members=list(team or [])))
    return main_window.MainWindow(einstellungen, Mode.DARK)


def _besuch(fenster: Any) -> None:
    fenster._tabs.setCurrentIndex(main_window._FLOW_VIEW)


class TestHauptfenster:
    def test_reiter_steht_ganz_rechts_hinter_dem_booster(self, qapp: QApplication) -> None:
        # Hinter den Booster, weil "Neue Tickets" direkt davor bleiben soll
        # (Michael, 24.09.2026, siehe test_new_tickets).
        fenster = _fenster()
        assert main_window._VIEWS[-1] == "Teamflow"
        assert main_window._FLOW_VIEW == main_window._PERF_VIEW + 1
        assert fenster._stack.widget(main_window._FLOW_VIEW) is fenster._ticket_flow
        assert fenster._tabs.tabText(main_window._FLOW_VIEW) == "Teamflow"

    def test_erster_besuch_laedt_die_eigenen_wege(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        assert len(fake) == 1
        assert fake[0].member is None
        assert fake[0].since == flow_since(FLOW_12M, dt.date.today())
        # Eigene Ablage, nicht die des Boosters.
        assert fake[0].cache_dir.name == "ticket_flow"

    def test_engerer_zeitraum_laedt_nicht_neu_weiterer_schon(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        fenster._ticket_flow._period_buttons["3M"].click()
        assert len(fake) == 1
        fenster._ticket_flow._period_buttons[FLOW_ALL].click()
        assert len(fake) == 2 and fake[1].since is None

    def test_ueberholter_abruf_wird_verworfen(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fenster._ticket_flow._period_buttons[FLOW_ALL].click()
        fake[0].finished_ok.emit(_abruf())
        assert fenster._ticket_flow.flow() is None
        fake[1].finished_ok.emit(_abruf())
        assert fenster._ticket_flow.flow() is not None

    def test_klick_auf_mitglied_der_merkliste(self, qapp: QApplication, fake: list[Any]) -> None:
        bert = TeamMember(display_name="Bert", account_ids=(BERT, "id-bert-alt"))
        fenster = _fenster([bert])
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        fenster._ticket_flow.person_clicked.emit(BERT, "Bert Beispiel")
        assert fake[-1].member == bert
        fake[-1].finished_ok.emit(_abruf())
        # Der Name aus der Merkliste geht vor dem Jira-Namen.
        assert fenster._ticket_flow.star().center.name == "Bert"

    def test_klick_auf_fremde_person_wird_gast(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        fenster._ticket_flow.person_clicked.emit(DORA, "Dora Probe")
        assert fenster._ticket_flow.current_member() == GUEST
        assert fake[-1].member == TeamMember(display_name="Dora Probe", account_ids=(DORA,))

    def test_klick_auf_sich_selbst_fuehrt_zurueck(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        fenster._ticket_flow.person_clicked.emit(DORA, "Dora Probe")
        fenster._ticket_flow.person_clicked.emit(ANNA, "Anna Muster")
        assert fenster._ticket_flow.current_member() == ""
        assert fake[-1].member is None

    def test_screenshot_modus_zeigt_erfundene_namen(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        fenster._toggle_anonymize()
        star = fenster._ticket_flow.star()
        names = {s.person.name for s in star.spokes if s.person is not None}
        assert names.isdisjoint({"Bert Beispiel", "Carl Mustermann", "Dora Probe"})
        assert star.center.name not in {"Anna Muster", ""}
        # Ein Klick ruft im Screenshot-Modus niemanden ab.
        fenster._ticket_flow.person_clicked.emit(DORA, "erfunden")
        assert len(fake) == 1

    def test_profilbilder_mit_adresse_aus_der_suche(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        assert len(FakeAvatarWorker.erzeugt) == 1
        wunsch = FakeAvatarWorker.erzeugt[0].wanted
        # Bert kam mit Adresse aus der Suche, die anderen schlaegt der Faden nach.
        assert wunsch == {ANNA: "", BERT: "https://bilder.example/bert", CARL: "", DORA: ""}
        assert FakeAvatarWorker.erzeugt[0].cache_dir.name == "avatars"
        FakeAvatarWorker.erzeugt[0].finished_ok.emit({BERT: _png()})
        assert len(_items(fenster._ticket_flow, QGraphicsPixmapItem)) == 1

    def test_screenshot_modus_laedt_keine_bilder(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._toggle_anonymize()
        _besuch(fenster)
        fake[0].finished_ok.emit(_abruf(fake[0].since))
        assert FakeAvatarWorker.erzeugt == []

    def test_kein_eigener_aktualisieren_knopf(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QPushButton

        fenster = _fenster()
        for view in (fenster._ticket_flow, fenster._new_tickets, fenster._performance):
            texte = [b.text() for b in view.findChildren(QPushButton)]
            assert "Aktualisieren" not in texte, type(view).__name__


def _viele() -> FlowLoad:
    """Anna gibt an zehn erfundene Personen ab - zwei landen unter Sonstige."""
    issues: list[dict[str, Any]] = []
    for n in range(1, 11):
        for k in range(n):
            issues.append(
                {
                    "key": f"V-{n * 10 + k}",
                    "fields": {
                        "created": at(1, 10),
                        "summary": f"Aufgabe {n}.{k}",
                        "reporter": {"accountId": ANNA, "displayName": "Muster, Anna"},
                        "assignee": {"accountId": f"id-p{n}", "displayName": f"Platzhalter{n:02d}, Pia"},
                    },
                }
            )
    return FlowLoad((ANNA,), None, extract_flow(issues, {i["key"]: [] for i in issues}), cached=0, fetched=0)


class TestTicketliste:
    def test_sonstige_zeigen_die_person(self, qapp: QApplication) -> None:
        view = TicketFlowView(Mode.DARK, today=TODAY)
        view.set_flow(_viele())
        star = view.star()
        assert star is not None and star.others is not None
        view.show_tickets(star.others, "out")
        assert view.list_headers() == ["Ticket", "Person", "Titel"]
        # Mit den wenigsten Wegen: Person 1 (ein Ticket) und Person 2 (zwei).
        assert {row[1] for row in view.list_rows()} == {"Pia Platzhalter01", "Pia Platzhalter02"}

    def test_einzelne_person_ohne_personenspalte(self, qapp: QApplication) -> None:
        view = _view()
        bert = next(s for s in view.star().spokes if s.person and s.person.account_id == BERT)  # type: ignore[union-attr]
        view.show_tickets(bert, "out")
        assert view.list_headers() == ["Ticket", "Titel"]

    def test_sortiert_nummern_als_zahl(self, qapp: QApplication) -> None:
        from PySide6.QtCore import Qt

        issues = [issue(key, ANNA, BERT, at(1, 10)) for key in ("X-10", "X-9", "X-100")]
        view = TicketFlowView(Mode.DARK, today=TODAY)
        view.set_flow(FlowLoad((ANNA,), None, extract_flow(issues, {i["key"]: [] for i in issues}), 0, 0))
        bert = view.star().spokes[0]  # type: ignore[union-attr]
        view.show_tickets(bert, "out")
        # Als Text stuende X-100 vor X-9.
        assert [row[0] for row in view.list_rows()] == ["X-9", "X-10", "X-100"]
        view._list.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        assert [row[0] for row in view.list_rows()] == ["X-100", "X-10", "X-9"]

    def test_kontakte_lassen_sich_sortieren(self, qapp: QApplication) -> None:
        from PySide6.QtCore import Qt

        view = TicketFlowView(Mode.DARK, today=TODAY)
        view.set_flow(_viele())
        assert view.contact_names()[0] == "Pia Platzhalter10"
        view._contacts.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        assert view.contact_names()[0] == "Pia Platzhalter08"


def _texte(menu: Any) -> dict[str, bool]:
    return {a.text(): a.isEnabled() for a in menu.actions() if a.text()}


class TestKontextmenues:
    def test_ticket_menue(self, qapp: QApplication) -> None:
        view = _view()
        bert = next(s for s in view.star().spokes if s.person and s.person.account_id == BERT)  # type: ignore[union-attr]
        view.show_tickets(bert, "out")
        menu = view.build_ticket_menu(view._list.topLevelItem(0))
        assert _texte(menu) == {
            "Ticket im Browser öffnen": True,
            "Ticket-Analyse erstellen": True,
            "Ticketnummer kopieren": True,
        }
        analyse: list[str] = []
        view.report_requested.connect(analyse.append)
        next(a for a in menu.actions() if a.text() == "Ticket-Analyse erstellen").trigger()
        assert analyse == ["X-1"]

    def test_ticket_menue_unter_sonstige_bietet_die_mitte_an(self, qapp: QApplication) -> None:
        view = TicketFlowView(Mode.DARK, today=TODAY)
        view.set_flow(_viele())
        view.show_tickets(view.star().others, "out")  # type: ignore[union-attr, arg-type]
        texte = _texte(view.build_ticket_menu(view._list.topLevelItem(0)))
        assert any(t.endswith("in die Mitte setzen") for t in texte)

    def test_analyse_ohne_zugang_grau(self, qapp: QApplication) -> None:
        view = _view()
        view.set_report_available(False)
        assert _texte(view.build_ticket_menu(None))["Ticket-Analyse erstellen"] is False

    def test_person_menue_mit_mein_team(self, qapp: QApplication) -> None:
        view = _view()
        dora = next(s for s in view.star().spokes if s.person and s.person.account_id == DORA)  # type: ignore[union-attr]
        texte = _texte(view.build_person_menu(dora))
        assert texte["Dora Probe zu meinem Team hinzufügen"] is True
        assert texte["Dora Probe in die Mitte setzen"] is True
        assert texte["Tickets von Dora Probe anzeigen"] is True
        gemeldet: list[tuple[str, str]] = []
        view.team_add_requested.connect(lambda a, n: gemeldet.append((a, n)))
        menu = view.build_person_menu(dora)
        next(a for a in menu.actions() if a.text().endswith("hinzufügen")).trigger()
        assert gemeldet == [(DORA, "Dora Probe")]

    def test_schon_im_team_ist_grau(self, qapp: QApplication) -> None:
        view = _view()
        view.set_team_ids(frozenset({DORA}))
        dora = next(s for s in view.star().spokes if s.person and s.person.account_id == DORA)  # type: ignore[union-attr]
        assert _texte(view.build_person_menu(dora))["Dora Probe ist schon in Mein Team"] is False

    def test_screenshot_modus_nimmt_niemanden_auf(self, qapp: QApplication) -> None:
        view = _view()
        view.set_anonymized(True)
        dora = next(s for s in view.star().spokes if s.person and s.person.account_id == DORA)  # type: ignore[union-attr]
        texte = _texte(view.build_person_menu(dora))
        assert texte["Dora Probe zu meinem Team hinzufügen"] is False
        assert texte["Tickets von Dora Probe anzeigen"] is False

    def test_rechtsklick_auf_den_kreis_oeffnet_das_menue(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _view()
        geoeffnet: list[str] = []
        monkeypatch.setattr(
            TicketFlowView, "_open_person_menu", lambda self, spoke, pos: geoeffnet.append(spoke.person.name)
        )
        view._render()
        node = next(n for n in _items(view, _Node) if "Dora" in n.toolTip())
        from PySide6.QtCore import QPoint

        node._on_menu(QPoint(0, 0))
        assert geoeffnet == ["Dora Probe"]

    def test_fenster_verdrahtet_die_menues(self, qapp: QApplication) -> None:
        fenster = _fenster()
        view = fenster._ticket_flow
        for signal in (
            "2report_requested(QString)",
            "2person_requested(QString,QString)",
            "2team_add_requested(QString,QString)",
        ):
            assert view.receivers(signal) == 1, signal


class TestVorschauUndKnoepfe:
    def test_knoepfe_gleich_hoch_plus_minus_quadratisch(self, qapp: QApplication) -> None:
        view = _view()
        # Feste Hoehe, und zwar dieselbe - ungezeigt waeren sie sonst nur zufaellig gleich.
        hoehen = {(b.minimumHeight(), b.maximumHeight()) for b in view._zoom_buttons.values()}
        assert len(hoehen) == 1
        (unten, oben) = hoehen.pop()
        # Das Maximum der natuerlichen Hoehen - der Knopf mit Symbol ist hoeher als der mit Text.
        assert unten == oben == max(b.sizeHint().height() for b in view._zoom_buttons.values())
        assert view._zoom_buttons["in"].width() == view._zoom_buttons["out"].width()
        assert view._zoom_buttons["in"].text() == "" and not view._zoom_buttons["in"].icon().isNull()

    def test_auswahl_in_der_liste_meldet_das_ticket(self, qapp: QApplication) -> None:
        view = _view()
        gemeldet: list[object] = []
        view.ticket_selected.connect(gemeldet.append)
        bert = next(s for s in view.star().spokes if s.person and s.person.account_id == BERT)  # type: ignore[union-attr]
        view.show_tickets(bert, "out")
        erste = view._list.topLevelItem(0)
        assert erste is not None
        view._list.setCurrentItem(erste)
        assert view.current_key() == "X-1"
        assert gemeldet[-1] == "X-1"

    def test_vorschau_zieht_in_den_teamflow(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._settings.show_ticket_preview = True
        fenster._stack.setCurrentIndex(main_window._FLOW_VIEW)
        assert fenster._ticket_flow.preview_host().indexOf(fenster._preview) >= 0


def test_demodaten_zeigen_stern_mit_sonstigen() -> None:
    from jira_timesheet_qt.services.ticket_flow import EDGE_KINDS, build_star
    from jira_timesheet_qt.ui.demo_flow import demo_flow

    load = demo_flow()
    star = build_star(load.data, load.center, EDGE_KINDS, None)
    # Das Motiv der README-Bilder: volle acht Speichen, ein Rest, beide Kantenarten.
    assert len(star.spokes) == 8 and star.others is not None
    assert {e.kind for e in load.data.edges} == set(EDGE_KINDS)
    assert star.center.name == "Max Mustermann"
    assert demo_flow().data.edges == load.data.edges
