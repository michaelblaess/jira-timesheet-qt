"""Tests der Ticket-Ansichten in der Oberflaeche.

Ohne Netz: die Boards werden von Hand gebaut und in die Ansicht gegeben.
Geprueft wird die Verdrahtung - Baum, Filter, Suche, Kontextmenue - nicht der
Kern, der seine eigenen Tests hat.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.ticket_board import (
    Board,
    BoardConfig,
    Group,
    Marker,
    Role,
    Ticket,
)
from jira_timesheet_qt.ui.main_window import _VIEWS, MainWindow
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.ticket_board_model import TICKET_ROLE, TicketBoardModel
from jira_timesheet_qt.ui.ticket_board_view import TicketBoardView
from jira_timesheet_qt.ui.ticket_board_worker import (
    MODE_ASSIGNED,
    MODE_RELEVANT,
    config_from,
)

NOW = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.UTC)


def ticket(
    key: str,
    *,
    status: str = "In Arbeit",
    summary: str = "Irgendein Titel",
    markers: tuple[Marker, ...] = (),
    idle: float = 1.0,
    is_bug: bool = False,
) -> Ticket:
    """Baut ein Ticket fuer die Anzeige."""
    return Ticket(
        key=key,
        summary=summary,
        status=status,
        markers=markers,
        idle_workdays=idle,
        idle_days=int(idle),
        is_bug=is_bug,
        url=f"https://example.invalid/browse/{key}",
    )


def board(*groups: Group) -> Board:
    """Baut ein Board aus fertigen Gruppen."""
    tickets = [t for g in groups for t in g.tickets]
    return Board(groups=list(groups), tickets=tickets)


class TestModell:
    """Der Baum bildet Gruppen und Tickets ab."""

    def test_gruppen_werden_zu_elternzeilen(self, qapp: QApplication) -> None:
        model = TicketBoardModel()
        model.set_board(
            board(
                Group(role=Role.ACTIVE, tickets=[ticket("A-1"), ticket("A-2")]),
                Group(role=Role.BACKLOG, tickets=[ticket("A-3")]),
            )
        )
        assert model.rowCount() == 2
        # Qt-Konvention: Kinder haengen ausschliesslich an Spalte 0.
        assert model.rowCount(model.index(0, 0)) == 2
        assert model.rowCount(model.index(1, 0)) == 1

    def test_kinder_haengen_nur_an_spalte_null(self, qapp: QApplication) -> None:
        model = TicketBoardModel()
        model.set_board(board(Group(role=Role.ACTIVE, tickets=[ticket("A-1")])))
        assert model.rowCount(model.index(0, 2)) == 0

    def test_ticket_ist_ueber_die_rolle_erreichbar(self, qapp: QApplication) -> None:
        model = TicketBoardModel()
        model.set_board(board(Group(role=Role.ACTIVE, tickets=[ticket("A-1")])))
        child = model.index(0, 0, model.index(0, 0))
        assert model.ticket_at(child) is not None
        assert child.data(TICKET_ROLE).key == "A-1"
        # Eine Gruppenzeile traegt kein Ticket.
        assert model.ticket_at(model.index(0, 0)) is None

    def test_liegezeit_sortiert_nach_dem_rohwert(self, qapp: QApplication) -> None:
        # "10 At" vor "9 At" waere die Reihenfolge einer Zeichenkette und
        # damit falsch.
        model = TicketBoardModel()
        model.set_board(
            board(Group(role=Role.ACTIVE, tickets=[ticket("A-1", idle=9), ticket("A-2", idle=10)]))
        )
        parent = model.index(0, 0)
        from jira_timesheet_qt.ui.ticket_board_model import SORT_ROLE

        assert model.index(0, 4, parent).data(SORT_ROLE) == 9
        assert model.index(1, 4, parent).data(SORT_ROLE) == 10


class TestAnsicht:
    """Kopfleiste, Filter und Suche."""

    def _view(self) -> TicketBoardView:
        view = TicketBoardView("Test")
        view.set_board(
            board(
                Group(
                    role=Role.ACTIVE,
                    tickets=[
                        ticket("A-1", summary="Erster Eintrag", markers=(Marker.PILE_OF_SHAME,)),
                        ticket("A-2", status="Im Review", summary="Zweiter Eintrag"),
                    ],
                ),
                Group(role=Role.BACKLOG, tickets=[ticket("B-9", summary="Dritter Eintrag")]),
            )
        )
        return view

    def _sichtbare_schluessel(self, view: TicketBoardView) -> list[str]:
        """Liest die Ticketnummern der aktuell angezeigten Zeilen."""
        proxy = view._proxy
        keys: list[str] = []
        for group_row in range(proxy.rowCount()):
            parent = proxy.index(group_row, 0)
            for row in range(proxy.rowCount(parent)):
                data = proxy.index(row, 0, parent).data(TICKET_ROLE)
                if data is not None:
                    keys.append(data.key)
        return keys

    def test_ohne_daten_steht_ein_hinweis(self, qapp: QApplication) -> None:
        view = TicketBoardView("Test")
        assert "Noch nichts geladen" in view._status_line.text()
        assert view._reload.text() == "Laden"

    def test_nach_dem_laden_heisst_der_knopf_aktualisieren(self, qapp: QApplication) -> None:
        view = self._view()
        assert view._reload.text() == "Aktualisieren"

    def test_alle_tickets_sind_sichtbar(self, qapp: QApplication) -> None:
        assert self._sichtbare_schluessel(self._view()) == ["A-1", "A-2", "B-9"]

    def test_suche_trifft_nummer_und_titel(self, qapp: QApplication) -> None:
        view = self._view()
        view._search.setText("B-9")
        assert self._sichtbare_schluessel(view) == ["B-9"]
        view._search.setText("Zweiter")
        assert self._sichtbare_schluessel(view) == ["A-2"]

    def test_suche_ignoriert_gross_und_kleinschreibung(self, qapp: QApplication) -> None:
        view = self._view()
        view._search.setText("erster")
        assert self._sichtbare_schluessel(view) == ["A-1"]

    def test_leere_gruppen_verschwinden_beim_filtern(self, qapp: QApplication) -> None:
        # Eine Gruppe ueberlebt nur, wenn ein Kind passt - sonst stuenden
        # leere Ueberschriften in der gefilterten Liste.
        view = self._view()
        view._search.setText("B-9")
        assert view._proxy.rowCount() == 1

    def test_statusfilter_kommt_aus_den_vorkommenden_werten(self, qapp: QApplication) -> None:
        view = self._view()
        eintraege = [view._status_box.itemData(i) for i in range(view._status_box.count())]
        assert eintraege == ["", "Im Review", "In Arbeit"]

    def test_statusfilter_wirkt(self, qapp: QApplication) -> None:
        view = self._view()
        view._status_box.setCurrentIndex(view._status_box.findData("Im Review"))
        assert self._sichtbare_schluessel(view) == ["A-2"]

    def test_handlungsbedarf_blendet_den_rest_aus(self, qapp: QApplication) -> None:
        view = self._view()
        view._actionable.setChecked(True)
        assert self._sichtbare_schluessel(view) == ["A-1"]

    def test_fusszeile_nennt_den_pile_of_shame(self, qapp: QApplication) -> None:
        view = self._view()
        text = view._status_line.text()
        assert "3 Tickets" in text
        assert "1 im Pile of Shame" in text

    def test_nicht_zugeordnete_status_stehen_in_der_fusszeile(self, qapp: QApplication) -> None:
        view = TicketBoardView("Test")
        view.set_board(
            Board(
                groups=[Group(role=Role.UNKNOWN, tickets=[ticket("A-1")])],
                tickets=[ticket("A-1")],
                unknown_status=["Seltsam"],
            )
        )
        assert "Seltsam" in view._status_line.text()


class TestEinstellungsbruecke:
    """Aus den Benutzereinstellungen wird die Kern-Konfiguration."""

    def test_leere_einstellungen_ergeben_den_rueckfall(self, qapp: QApplication) -> None:
        config = config_from(Settings())
        assert config.active_status == ()
        # Ohne Zuordnung entscheidet die Jira-Statuskategorie.
        assert config.role_of("Irgendwas", "indeterminate") is Role.ACTIVE

    def test_status_und_schwellen_werden_uebernommen(self, qapp: QApplication) -> None:
        settings = Settings()
        settings.board_active_status = ["Läuft"]
        settings.board_threshold_active = 15.0
        settings.board_threshold_closing = 0.0
        config = config_from(settings)
        assert config.role_of("Läuft", "new") is Role.ACTIVE
        assert config.threshold_of(Role.ACTIVE) == 15.0
        # Schwelle 0 heisst: diese Rolle erzeugt keinen Pile of Shame.
        assert config.threshold_of(Role.CLOSING) is None

    def test_eigene_prioritaetsrangfolge_schlaegt_die_vorgabe(self, qapp: QApplication) -> None:
        settings = Settings()
        settings.board_priorities = ["Sofort", "Irgendwann"]
        config = config_from(settings)
        assert config.priority_rank("Sofort") < config.priority_rank("Irgendwann")


class TestImFenster:
    """Die Ansichten haengen als eigene Reiter im Hauptfenster."""

    def test_beide_reiter_sind_da(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        assert "Meine Tickets" in _VIEWS
        assert "Relevante Tickets" in _VIEWS
        assert isinstance(window._assigned_board, TicketBoardView)
        assert isinstance(window._relevant_board, TicketBoardView)

    def test_reiter_zeigen_auf_die_richtige_ansicht(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._tabs.setCurrentIndex(_VIEWS.index("Meine Tickets"))
        assert window._stack.currentWidget() is window._assigned_board
        window._tabs.setCurrentIndex(_VIEWS.index("Relevante Tickets"))
        assert window._stack.currentWidget() is window._relevant_board

    def test_ohne_zugangsdaten_wird_nicht_abgerufen(self, qapp: QApplication) -> None:
        # Ein Abruf ohne Zugang wuerde nur in einer Fehlermeldung enden -
        # besser gleich sagen, was fehlt.
        window = MainWindow(Settings(), Mode.DARK)
        window._load_board(MODE_ASSIGNED)
        assert "Zugangsdaten" in window._assigned_board._status_line.text()
        assert window._board_generation[MODE_ASSIGNED] == 0

    def test_ueberholtes_ergebnis_wird_verworfen(self, qapp: QApplication) -> None:
        # Ein QThread laesst sich nicht abbrechen. Der ueberholte Faden laeuft
        # zu Ende - sein Ergebnis darf die Ansicht aber nicht mehr fuellen.
        window = MainWindow(Settings(), Mode.DARK)
        window._board_generation[MODE_ASSIGNED] = 7
        alt = board(Group(role=Role.ACTIVE, tickets=[ticket("VERALTET-1")]))
        window._on_board_loaded(alt, MODE_ASSIGNED, 6)
        assert window._assigned_board._board is None

    def test_aktuelles_ergebnis_kommt_an(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._board_generation[MODE_RELEVANT] = 3
        neu = board(Group(role=Role.ACTIVE, tickets=[ticket("AKTUELL-1")]))
        window._on_board_loaded(neu, MODE_RELEVANT, 3)
        assert window._relevant_board._board is neu

    def test_beide_ansichten_zaehlen_getrennt(self, qapp: QApplication) -> None:
        # Sonst entwertet ein Abruf der einen Ansicht das Ergebnis der anderen.
        window = MainWindow(Settings(), Mode.DARK)
        window._board_generation[MODE_ASSIGNED] = 4
        window._board_generation[MODE_RELEVANT] = 1
        eigenes = board(Group(role=Role.ACTIVE, tickets=[ticket("R-1")]))
        window._on_board_loaded(eigenes, MODE_RELEVANT, 1)
        assert window._relevant_board._board is eigenes
        assert window._assigned_board._board is None


class TestKonfigurationImKern:
    """Der Kern arbeitet auch ohne jede Konfiguration."""

    def test_ohne_konfiguration_gibt_es_gruppen(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.services.ticket_board import build_board

        issue = {
            "key": "A-1",
            "fields": {
                "summary": "Titel",
                "status": {"name": "Egal", "statusCategory": {"key": "indeterminate"}},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Story"},
                "reporter": {"accountId": "x", "displayName": "Wer"},
                "updated": "2026-08-04T10:00:00.000+0200",
                "created": "2026-01-01T10:00:00.000+0200",
            },
        }
        result = build_board([issue], BoardConfig(), NOW)
        assert result.count == 1
        assert result.groups[0].role is Role.ACTIVE


class TestEinstellungsseite:
    """Die Felder der Ticket-Seite muessen den Dialog ueberleben.

    Erfahrungsgemaess die verlustreichste Stelle: ein Feld, das im Modell
    steht und im Dialog gesetzt wird, aber beim Auslesen vergessen wurde,
    springt nach dem Speichern wortlos auf den alten Wert zurueck.
    """

    def test_alle_felder_kommen_zurueck(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.board_active.setText("Läuft, Rennt")
        dialog.board_backlog.setText("Wartet")
        dialog.board_acceptance.setText("Prüfung")
        dialog.board_handback.setText("Bewertung")
        dialog.board_closing.setText("Übergabe")
        dialog.board_priorities.setText("Sofort, Später")
        dialog.board_window.setValue(45)
        dialog.board_stale.setValue(120)
        dialog.board_threshold_active.setValue(12)
        dialog.board_threshold_acceptance.setValue(7)
        dialog.board_threshold_closing.setValue(30)

        result = dialog.result_settings()
        assert result.board_active_status == ["Läuft", "Rennt"]
        assert result.board_backlog_status == ["Wartet"]
        assert result.board_acceptance_status == ["Prüfung"]
        assert result.board_handback_status == ["Bewertung"]
        assert result.board_closing_status == ["Übergabe"]
        assert result.board_priorities == ["Sofort", "Später"]
        assert result.board_window_days == 45
        assert result.board_stale_days == 120
        assert result.board_threshold_active == 12
        assert result.board_threshold_acceptance == 7
        assert result.board_threshold_closing == 30

    def test_gespeicherte_werte_stehen_beim_oeffnen_wieder_da(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        settings = Settings()
        settings.board_active_status = ["Läuft"]
        settings.board_threshold_active = 25.0
        dialog = SettingsDialog(settings)
        assert dialog.board_active.text() == "Läuft"
        assert dialog.board_threshold_active.value() == 25.0

    def test_der_weg_bis_zur_kernkonfiguration_haelt(self, qapp: QApplication) -> None:
        # Dialog -> Einstellungen -> Kern-Konfiguration, in einem Zug.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.board_active.setText("Läuft")
        dialog.board_threshold_active.setValue(9)
        config = config_from(dialog.result_settings())
        assert config.role_of("Läuft", "new") is Role.ACTIVE
        assert config.threshold_of(Role.ACTIVE) == 9.0
