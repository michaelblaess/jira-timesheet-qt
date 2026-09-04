"""Tests der Oberflaeche zu "Mein Team" - Einstellungsseite und Reiter.

Getrennt von test_team.py, weil dort der Kern steht: der ist mit der
Textual-Fassung wortgleich, diese Datei teilt mit ihr keine Zeile.

Die geprueften Faelle stammen aus Fehlern, die in der Textual-Fassung im
Betrieb aufgefallen sind - vor allem der wichtigste: die Merkliste wurde
uebernommen, war nach dem erneuten Oeffnen aber wieder leer.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QWidget

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.team import AccountCandidate

# Kennungen im Format der vermessenen Instanz: 24 Zeichen alt, 43 Zeichen neu.
ID_A = "5cf79d64eba18b0ea85a7b53"
ID_B = "712020:e1153ec2-3116-4efb-bb7e-f94d2617a14a"
ID_C = "630f1a2b3c4d5e6f70819200"


def _hit(account_id: str, name: str, offen: int | None = 3) -> AccountCandidate:
    """Baut einen Suchtreffer, wie ihn der Faden liefert."""
    return AccountCandidate(
        account_id=account_id,
        display_name=name,
        email=f"{account_id[:6]}@example.invalid",
        open_count=offen,
        last_touch=dt.datetime(2026, 8, 5, 9, 0, tzinfo=dt.UTC),
    )


if TYPE_CHECKING:
    from jira_timesheet_qt.services.ticket_board import Board


class TestEinstellungsseite:
    """Suchen, uebernehmen, speichern."""

    def test_seite_ist_ueber_die_navigation_erreichbar(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        eintraege = [
            dialog._nav.item(row).text() for row in range(dialog._nav.count())
        ]
        assert "Mein Team" in eintraege
        # Jeder Navigationseintrag braucht seine Seite - sonst zeigt der
        # Klick die Seite des Nachbarn an.
        assert dialog._nav.count() == dialog._stapel.count()

    def test_uebernehmen_landet_in_der_merkliste(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        assert [m.display_name for m in dialog._roster.members] == ["Reiner Beispiel"]

    def test_merkliste_ueberlebt_das_speichern(self, qapp: QApplication) -> None:
        # DER Fehler aus der Textual-Fassung: uebernommen, gespeichert, und
        # nach dem erneuten Oeffnen war die Liste wieder leer. Geprueft wird
        # deshalb der ganze Weg, nicht nur der erste Schritt.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        gespeichert = dialog.result_settings()
        assert gespeichert.team_members, "Die Merkliste kam nicht in den Einstellungen an"

        # Zweiter Dialog auf demselben Stand - genau das Oeffnen, bei dem die
        # Liste leer blieb.
        wieder = SettingsDialog(gespeichert)
        assert [m.display_name for m in wieder._roster.members] == ["Reiner Beispiel"]
        assert wieder.team_roster_list.count() == 1

    def test_mehrere_konten_werden_eine_person(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready(
            [_hit(ID_A, "Reinhold Beispiel"), _hit(ID_B, "Beispiel, Reinhold")]
        )
        dialog.team_hits.selectAll()
        dialog.team_name.setText("Reiner Beispiel")
        dialog._team_add()

        mitglied = dialog._roster.members[0]
        assert mitglied.display_name == "Reiner Beispiel"
        assert set(mitglied.account_ids) == {ID_A, ID_B}

    def test_zweite_uebernahme_erweitert_statt_zu_ersetzen(self, qapp: QApplication) -> None:
        # Wer spaeter ein drittes Konto derselben Person findet, soll es
        # dazulegen koennen, ohne die schon gefundenen zu verlieren.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog.team_name.setText("Reiner Beispiel")
        dialog._team_add()

        dialog._team_hits_ready([_hit(ID_C, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog.team_name.setText("Reiner Beispiel")
        dialog._team_add()

        assert len(dialog._roster.members) == 1
        assert set(dialog._roster.members[0].account_ids) == {ID_A, ID_C}

    def test_konto_einer_anderen_person_wird_abgelehnt(self, qapp: QApplication) -> None:
        # Sonst erscheinen dieselben Tickets unter zwei Namen.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Erste Person")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        dialog._team_hits_ready([_hit(ID_A, "Zweite Person")])
        dialog.team_hits.selectRow(0)
        dialog.team_name.setText("Zweite Person")
        dialog._team_add()

        assert [m.display_name for m in dialog._roster.members] == ["Erste Person"]
        assert "Merkliste" in dialog.team_status.text()

    def test_entfernen_nimmt_die_person_heraus(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        dialog.team_roster_list.setCurrentRow(0)
        dialog._team_remove()
        assert dialog._roster.members == []
        assert dialog.team_roster_list.count() == 0

    def test_ohne_zugang_keine_suche(self, qapp: QApplication) -> None:
        # Ohne Zugang liefe die Suche in einen Netzwerkfehler. Der Hinweis
        # sagt, wo der Zugang steht, statt nur "gescheitert" zu melden.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.team_query.setText("Beispiel")
        dialog._team_search()
        assert "Zugang" in dialog.team_status.text()
        assert dialog._team_worker is None, "Ohne Zugang darf kein Faden starten"

    def test_gescheiterte_suche_gibt_die_seite_wieder_frei(self, qapp: QApplication) -> None:
        # Bleibt der Knopf gesperrt, ist die Seite nach einem Netzwerkfehler
        # tot und nur ueber Schliessen und Neuoeffnen zu retten.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.team_search_button.setEnabled(False)
        dialog._team_search_failed("Verbindung abgelehnt")
        assert dialog.team_search_button.isEnabled()
        assert "Verbindung abgelehnt" in dialog.team_status.text()

    def test_konto_ohne_zahlen_zeigt_leere_spalten(self, qapp: QApplication) -> None:
        # Eine Null waere eine Behauptung, die niemand geprueft hat - und
        # gerade das Konto mit der meisten Arbeit gibt oft am wenigsten preis.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Ohne Zahlen", offen=None)])
        zelle = dialog.team_hits.item(0, 2)
        assert zelle is not None and zelle.text() == ""
        # Gegenprobe: mit Zahl steht sie auch da.
        dialog._team_hits_ready([_hit(ID_B, "Mit Zahlen", offen=7)])
        zelle = dialog.team_hits.item(0, 2)
        assert zelle is not None and zelle.text() == "7"


class TestReiter:
    """Der Reiter "Mein Team" im Hauptfenster."""

    def _settings(self, *namen: str) -> Settings:
        """Einstellungen mit gefuellter Merkliste und vollstaendigem Zugang."""
        return Settings(
            jira_host="https://beispiel.invalid",
            email="ich@example.invalid",
            jira_token="geheim",
            team_members=[
                {"display_name": name, "account_ids": [f"{ID_A[:-1]}{i}"]}
                for i, name in enumerate(namen)
            ],
        )

    def test_reiter_ist_vorhanden(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.main_window import _VIEWS

        assert "Mein Team" in _VIEWS
        # Die Umbenennungen mit: der alte Name darf nicht daneben stehen
        # bleiben, sonst gibt es zwei Reiter fuer dieselbe Sache.
        assert "Relevante Tickets" not in _VIEWS
        assert "Liste" not in _VIEWS
        assert "Meine Aktivitäten" in _VIEWS
        assert "Stundenzettel" in _VIEWS

    def test_reiter_zeigt_auf_die_eigene_ansicht(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.main_window import _VIEWS, MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(Settings(), Mode.DARK)
        window._tabs.setCurrentIndex(_VIEWS.index("Mein Team"))
        assert window._stack.currentWidget() is window._team_board

    def test_auswahlfeld_entsteht_auch_ohne_merkliste(self, qapp: QApplication) -> None:
        # DER Fehler aus der Textual-Fassung: das Feld entstand nur bei
        # gefuellter Merkliste. Wer danach jemanden eintrug, sah trotzdem
        # kein Feld - und hielt die Uebernahme fuer gescheitert.
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(Settings(), Mode.DARK)
        assert window._team_board._with_members
        assert window._team_board._member_box is not None

    def test_merkliste_erreicht_das_auswahlfeld(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(self._settings("Anna Muster", "Reiner Beispiel"), Mode.DARK)
        box = window._team_board._member_box
        assert [box.itemText(i) for i in range(box.count())] == [
            "Anna Muster",
            "Reiner Beispiel",
        ]

    def test_gewaehlte_person_landet_im_abruf(self, qapp: QApplication) -> None:
        # Ohne diesen Weg faellt die Abfrage auf currentUser() zurueck, und
        # die Ansicht zeigt die eigenen Tickets unter fremdem Namen.
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(self._settings("Reiner Beispiel"), Mode.DARK)
        member = window._current_member()
        assert member is not None
        assert member.display_name == "Reiner Beispiel"
        assert member.account_ids

    def test_ohne_merkliste_kein_abruf_sondern_ein_hinweis(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode
        from jira_timesheet_qt.ui.ticket_board_worker import MODE_TEAM

        window = MainWindow(
            Settings(
                jira_host="https://beispiel.invalid",
                email="ich@example.invalid",
                jira_token="geheim",
            ),
            Mode.DARK,
        )
        vorher = len(window._running_workers)
        window._load_board(MODE_TEAM)
        assert len(window._running_workers) == vorher, "Ohne Person darf kein Abruf starten"
        assert "Merkliste" in window._team_board._placeholder.text()

    def test_fremdsicht_zeigt_keine_auswertung(self, qapp: QApplication) -> None:
        # Durchsatz je Monat waere ueber eine andere Person eine
        # Leistungskennzahl. Die Gegenprobe zeigt, dass die eigene Ansicht
        # sie sehr wohl hat - sonst belegte der Test nur, dass die Diagramme
        # ueberall fehlen.
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(self._settings("Reiner Beispiel"), Mode.DARK)
        assert not window._team_board._with_charts
        assert window._assigned_board._with_charts


class TestGruppen:
    """Titel, Hinweise und der Startzustand der Gruppen."""

    def _board(self) -> Board:
        """Eine Ansicht mit je einem Ticket in Übergabe und Abgeschlossen."""
        from jira_timesheet_qt.services.ticket_board import BoardConfig, build_board

        alt = (dt.datetime.now(dt.UTC) - dt.timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.000+0000"
        )
        issues = [
            {
                "key": f"BSP-{i}",
                "fields": {
                    "summary": "Beispiel",
                    "status": {"name": status, "statusCategory": {"key": "done"}},
                    "priority": {"name": "Medium"},
                    "issuetype": {"name": "Task"},
                    "reporter": {"accountId": ID_A, "displayName": "Autor"},
                    "created": alt,
                    "updated": alt,
                },
            }
            for i, status in enumerate(("Zur Übergabe", "Erledigt"))
        ]
        return build_board(
            issues,
            BoardConfig(closing_status=("Zur Übergabe",), done_status=("Erledigt",)),
            account_id=ID_A,
        )

    def test_titel_treffen_die_statusbedeutung(self, qapp: QApplication) -> None:
        # "Rückläufer" war falsch: ein Rückläufer geht aus dem Review zurück
        # in die Arbeit. Der gemeinte Status heißt dagegen: produktiv gesetzt,
        # muss auf PROD noch getestet werden.
        from jira_timesheet_qt.services.ticket_board import Role
        from jira_timesheet_qt.ui.ticket_board_model import GROUP_TITLES

        assert GROUP_TITLES[Role.HANDBACK] == "Live, wartet auf Test"
        assert GROUP_TITLES[Role.CLOSING] == "Übergabe"
        assert GROUP_TITLES[Role.DONE] == "Abgeschlossen"

    def test_jede_rolle_hat_titel_und_hinweis(self, qapp: QApplication) -> None:
        # Eine neue Rolle ohne Eintrag faellt sonst auf ihren technischen
        # Namen zurueck ("done") und steht so in der Oberflaeche.
        from jira_timesheet_qt.services.ticket_board import Role
        from jira_timesheet_qt.ui.ticket_board_model import GROUP_HINTS, GROUP_TITLES

        for role in Role:
            assert role in GROUP_TITLES, f"Titel fehlt: {role}"
            assert role in GROUP_HINTS, f"Hinweis fehlt: {role}"

    def test_erklaerung_steht_im_hinweis_nicht_im_titel(self, qapp: QApplication) -> None:
        # Im Titel las sie sich wie ein Teil des Statusnamens.
        from PySide6.QtCore import Qt

        from jira_timesheet_qt.ui.ticket_board_model import TicketBoardModel

        model = TicketBoardModel()
        model.set_board(self._board())
        index = model.index(0, 0)
        titel = model.data(index, Qt.ItemDataRole.DisplayRole)
        hinweis = model.data(index, Qt.ItemDataRole.ToolTipRole)
        assert " - " not in str(titel).split("(")[0].strip()
        assert hinweis, "Die Gruppenzeile hat keinen Hinweis"

    def test_abgeschlossen_startet_zugeklappt(self, qapp: QApplication) -> None:
        # Dort ist nichts mehr zu tun. Aufgeklappt schiebt die Gruppe alles
        # darüber aus dem Bild.
        from PySide6.QtCore import QModelIndex

        from jira_timesheet_qt.services.ticket_board import Role
        from jira_timesheet_qt.ui.ticket_board_view import TicketBoardView

        view = TicketBoardView("Test")
        board = self._board()
        view.set_board(board)

        zustand = {}
        for row, group in enumerate(board.groups):
            index = view._proxy.index(row, 0, QModelIndex())
            zustand[group.role] = view._tree.isExpanded(index)

        assert zustand[Role.DONE] is False
        # Gegenprobe: die übrigen Gruppen stehen offen - sonst belegte der
        # Test nur, dass gar nichts aufgeklappt wird.
        assert zustand[Role.CLOSING] is True


class TestLadenUndAktualisieren:
    """Wann von selbst geladen wird und was "Aktualisieren" trifft."""

    def _zugang(self) -> Settings:
        return Settings(
            jira_host="https://beispiel.invalid",
            email="ich@example.invalid",
            jira_token="geheim",
        )

    def test_ohne_zugang_laedt_der_start_nichts(self, qapp: QApplication) -> None:
        # Ein Abruf ohne Token endet in einer Fehlermeldung, und die als
        # Begrüßung ist schlechter als ein Hinweis, was zu tun ist.
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(Settings(), Mode.DARK)
        gerufen: list[str] = []
        window.load_month = lambda: gerufen.append("monat")  # type: ignore[method-assign]
        window.start_initial_load()
        assert gerufen == []

    def test_mit_zugang_laedt_der_start_von_selbst(self, qapp: QApplication) -> None:
        # Gegenprobe zum Test darüber - ohne sie belegte er nur, dass beim
        # Start nie geladen wird.
        from jira_timesheet_qt.ui.main_window import MainWindow
        from jira_timesheet_qt.ui.theme import Mode

        window = MainWindow(self._zugang(), Mode.DARK)
        gerufen: list[str] = []
        window.load_month = lambda: gerufen.append("monat")  # type: ignore[method-assign]
        window.start_initial_load()
        assert gerufen == ["monat"]

    def test_aktualisieren_trifft_die_sichtbare_ansicht(self, qapp: QApplication) -> None:
        # Die sichtbare Ansicht wird geladen - und seit dem 04.09.2026 immer
        # auch der Stundenzettel. Er ist der Zweck der Anwendung und darf
        # nicht alt sein, nur weil eine Ticketliste im Vordergrund stand.
        from jira_timesheet_qt.ui.main_window import _VIEWS, MainWindow
        from jira_timesheet_qt.ui.theme import Mode
        from jira_timesheet_qt.ui.ticket_board_worker import MODE_TEAM

        window = MainWindow(self._zugang(), Mode.DARK)
        geladen: list[str] = []
        window.load_month = lambda: geladen.append("monat")  # type: ignore[method-assign]
        window._load_board = lambda mode: geladen.append(mode)  # type: ignore[method-assign]

        window._stack.setCurrentIndex(_VIEWS.index("Stundenzettel"))
        window.reload_current()
        window._stack.setCurrentIndex(_VIEWS.index("Mein Team"))
        window.reload_current()

        assert geladen == ["monat", MODE_TEAM, "monat"]


class TestBeschriftungen:
    """Einstellungsfelder und Gruppentitel muessen zusammenpassen.

    Am 11.08.2026 aufgefallen: die Gruppentitel im Board waren umbenannt, die
    Feldbeschriftungen im Einstellungsdialog nicht. Wer die Gruppe "Live,
    wartet auf Test" befuellen wollte, suchte ein Feld namens "Rueckgabe" -
    und in der Textual-Fassung hiess dasselbe Feld schon "Live, Test offen".
    Drei Namen fuer eine Sache.
    """

    # Beschriftung im Dialog je Rolle. Bewusst kuerzer als der Gruppentitel,
    # aber erkennbar dieselbe Sache. Wortgleich mit der Textual-Fassung.
    ERWARTET = {
        "board_active": "Ich bin dran",
        "board_backlog": "Backlog",
        "board_acceptance": "Andere sind dran",
        "board_handback": "Live, Test offen",
        "board_closing": "Übergabe",
        "board_done": "Abgeschlossen",
    }

    def _labels(self, dialog: QWidget) -> dict[str, str]:
        """Liest zu jedem Board-Feld die Beschriftung aus dem Formular."""
        from PySide6.QtWidgets import QFormLayout, QLabel

        # Ueber ALLE Formulare des Dialogs, nicht ueber das Elternwidget: die
        # Felder sitzen in verschachtelten Seiten, deren layout() nicht das
        # QFormLayout ist.
        formulare = dialog.findChildren(QFormLayout)
        gefunden: dict[str, str] = {}
        for name in self.ERWARTET:
            feld = getattr(dialog, name)
            for form in formulare:
                beschriftung = form.labelForField(feld)
                if isinstance(beschriftung, QLabel):
                    gefunden[name] = beschriftung.text()
                    break
        return gefunden

    def test_jedes_feld_traegt_die_erwartete_beschriftung(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        gefunden = self._labels(dialog)
        assert gefunden, "Keine Beschriftung gefunden - der Test misst nichts"
        for name, erwartet in self.ERWARTET.items():
            assert gefunden.get(name) == erwartet, (
                f"{name}: erwartet {erwartet!r}, gefunden {gefunden.get(name)!r}"
            )

    def test_alte_bezeichnungen_sind_verschwunden(self, qapp: QApplication) -> None:
        # Die Gegenprobe zum Test darüber: er würde auch bestehen, wenn eine
        # alte Bezeichnung an anderer Stelle stehen bliebe.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        texte = " ".join(
            kind.text() for kind in dialog.findChildren(type(dialog.team_status))
        )
        for veraltet in ("Rückgabe", "Abschluss offen", "Rückläufer", "Relevante Tickets"):
            assert veraltet not in texte, f"Alte Bezeichnung noch da: {veraltet}"


class TestSuchfeldNachUebernahme:
    """Was nach dem Übernehmen im Dialog stehen bleibt und was nicht."""

    def test_suchbegriff_wird_geleert(self, qapp: QApplication) -> None:
        # Der Begriff ist verbraucht. Bleibt er stehen, muss man ihn vor
        # jedem weiteren Namen erst von Hand löschen.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.team_query.setText("beispiel")
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        assert dialog.team_query.text() == ""
        assert dialog.team_name.text() == ""

    def test_trefferliste_bleibt_stehen(self, qapp: QApplication) -> None:
        # Bewusst NICHT geleert: fällt hinterher auf, dass ein weiteres Konto
        # zu derselben Person gehört, ist es noch da.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog._team_hits_ready([_hit(ID_A, "Erstes"), _hit(ID_B, "Zweites")])
        dialog.team_hits.selectRow(0)
        dialog._team_add()

        assert dialog.team_hits.rowCount() == 2

    def test_gescheiterte_uebernahme_behaelt_den_begriff(self, qapp: QApplication) -> None:
        # Ohne Auswahl passiert nichts - dann darf auch nichts weggeräumt
        # werden, sonst ist die Eingabe weg und der Grund unklar.
        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(Settings())
        dialog.team_query.setText("beispiel")
        dialog._team_hits_ready([_hit(ID_A, "Reiner Beispiel")])
        dialog.team_hits.clearSelection()
        dialog._team_add()

        assert dialog.team_query.text() == "beispiel"
        assert dialog._roster.members == []
