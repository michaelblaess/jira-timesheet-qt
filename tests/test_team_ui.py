"""Tests der Oberflaeche zu "Mein Team" - Einstellungsseite und Reiter.

Getrennt von test_team.py, weil dort der Kern steht: der ist mit der
Textual-Fassung wortgleich, diese Datei teilt mit ihr keine Zeile.

Die geprueften Faelle stammen aus Fehlern, die in der Textual-Fassung im
Betrieb aufgefallen sind - vor allem der wichtigste: die Merkliste wurde
uebernommen, war nach dem erneuten Oeffnen aber wieder leer.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QApplication

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
        assert dialog._nav.count() == dialog._pages.count()

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
        assert dialog.team_hits.item(0, 2).text() == ""
        # Gegenprobe: mit Zahl steht sie auch da.
        dialog._team_hits_ready([_hit(ID_B, "Mit Zahlen", offen=7)])
        assert dialog.team_hits.item(0, 2).text() == "7"


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
        from jira_timesheet_qt.ui.main_window import MODE_TEAM, MainWindow
        from jira_timesheet_qt.ui.theme import Mode

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
