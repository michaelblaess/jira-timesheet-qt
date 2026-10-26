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
        view._kind_buttons[EDGE_HANDOVER].click()
        assert _namen(view) == ["Bert Beispiel", "Dora Probe"]
        assert view.current_kinds() == (EDGE_ORDER,)

    def test_die_letzte_pfeilart_bleibt_an(self, qapp: QApplication) -> None:
        view = _view()
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

    def test_fusszeile_nennt_tickets_ohne_verlauf(self, qapp: QApplication) -> None:
        text = _view()._footer.text()
        assert "1 Ticket ohne Änderungsverlauf" in text
        assert "ab 27.10.2025" in text

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
