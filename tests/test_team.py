"""Tests der Ansicht "Mein Team" - Abfragen, Kontoauswahl, Merkliste.

Die Zahlen und Faelle stammen aus Messungen gegen eine echte Jira-Instanz am
10.08.2026, nicht aus der Dokumentation. Wo ein Test eine Gegenprobe hat, ist
sie mitgetestet: eine Pruefung, die nicht scheitern kann, belegt nichts.

Der Kern ist mit der Textual-Fassung deckungsgleich, deshalb sind diese Tests
dort wortgleich vorhanden. Die Tests der Oberflaeche stehen getrennt - Qt und
Textual teilen dort keine Zeile.
"""

from __future__ import annotations

import datetime as dt
import unittest
from typing import Any

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.team import (
    Roster,
    TeamMember,
    from_storage,
    merge_accounts,
    parse_people,
    parse_search,
    sort_candidates,
    to_storage,
    with_last_touch,
)
from jira_timesheet_qt.services.ticket_board import (
    AccountIdError,
    BoardConfig,
    Marker,
    Role,
    Ticket,
    WorklogInfo,
    assigned_jql,
    assignee_clause,
    build_board,
    closing_jql,
    history_jql,
    last_touch_jql,
)
from jira_timesheet_qt.ui.ticket_board_worker import (
    MODE_ASSIGNED,
    MODE_TEAM,
    TicketBoardWorker,
    config_from,
)

# Kennungen im Format der vermessenen Instanz: 24 Zeichen alt, 43 Zeichen neu.
ID_A = "5cf79d64eba18b0ea85a7b53"
ID_B = "712020:e1153ec2-3116-4efb-bb7e-f94d2617a14a"
ID_C = "630f1a2b3c4d5e6f70819200"


def _user(
    account_id: str,
    name: str,
    mail: str = "",
    active: bool = True,
    kind: str = "atlassian",
) -> dict[str, object]:
    """Baut einen Treffer, wie ihn /user/search liefert."""
    entry: dict[str, object] = {
        "accountId": account_id,
        "displayName": name,
        "active": active,
        "accountType": kind,
        "avatarUrls": {"48x48": f"https://example.invalid/{account_id}.png"},
    }
    if mail:
        entry["emailAddress"] = mail
    return entry


class AbfragenTest(unittest.TestCase):
    """Die JQL-Bauer mit und ohne fremde Kennung."""

    def test_ohne_kennung_bleibt_es_bei_currentuser(self) -> None:
        self.assertEqual("assignee = currentUser()", assignee_clause())
        self.assertIn("assignee = currentUser()", assigned_jql())
        self.assertIn("assignee = currentUser()", closing_jql(("Schliessen",)))

    def test_eine_kennung_nutzt_trotzdem_die_mengenform(self) -> None:
        # Bewusst IN statt "=", damit die Abfrage unveraendert bleibt, wenn
        # spaeter ein zweites Konto derselben Person dazukommt.
        self.assertEqual(f'assignee IN ("{ID_A}")', assignee_clause([ID_A]))

    def test_mehrere_kennungen_landen_alle_im_ausdruck(self) -> None:
        klausel = assignee_clause([ID_A, ID_B, ID_C])
        for kennung in (ID_A, ID_B, ID_C):
            self.assertIn(f'"{kennung}"', klausel)
        self.assertTrue(klausel.startswith("assignee IN ("))

    def test_unbrauchbare_kennung_bricht_ab_statt_sie_zu_uebergehen(self) -> None:
        # Eine uebersprungene Kennung liefert ein unvollstaendiges Ergebnis,
        # das wie ein vollstaendiges aussieht. Deshalb Abbruch.
        with self.assertRaises(AccountIdError):
            assignee_clause([ID_A, 'boese" OR key = "PROJ-1'])

    def test_kennung_wandert_in_beide_ansichten(self) -> None:
        self.assertIn(f'"{ID_A}"', assigned_jql([ID_A]))
        self.assertIn(f'"{ID_A}"', closing_jql(("Schliessen",), [ID_A]))

    def test_auswertung_kennt_keine_fremde_kennung(self) -> None:
        # Durchsatz je Monat ueber eine andere Person waere eine
        # Leistungskennzahl. history_jql darf deshalb gar keinen Parameter
        # haben - dieser Test scheitert, sobald jemand einen einbaut.
        self.assertIn("currentUser()", history_jql())
        with self.assertRaises(TypeError):
            history_jql(ID_A)  # type: ignore[call-arg]

    def test_letzter_kontakt_sortiert_absteigend(self) -> None:
        ausdruck = last_touch_jql(ID_A)
        self.assertIn(f'assignee = "{ID_A}"', ausdruck)
        self.assertIn("ORDER BY updated DESC", ausdruck)

    def test_letzter_kontakt_prueft_die_kennung(self) -> None:
        with self.assertRaises(AccountIdError):
            last_touch_jql('" OR key = "PROJ-1')


class KontoauswahlTest(unittest.TestCase):
    """Mehrere Konten je Person - der am 10.08.2026 gemessene Fall."""

    def _kandidaten(self) -> list[object]:
        """Die drei Konten eines Kollegen, wie am 10.08.2026 vermessen."""
        treffer = parse_search(
            [
                _user(ID_A, "Reinhold Beispiel"),
                _user(ID_B, "Beispiel, Reinhold", "vorname.nachname@example.invalid"),
                _user(ID_C, "Reiner Beispiel"),
            ]
        )
        stempel = {
            ID_A: "2026-04-16T09:00:00.000+0200",
            ID_B: "2026-08-05T09:00:00.000+0200",
            ID_C: "2026-07-30T09:00:00.000+0200",
        }
        return [
            with_last_touch(k, [{"fields": {"updated": stempel[k.account_id]}}])
            for k in treffer
        ]

    def test_juengstes_konto_gewinnt_nicht_das_groesste(self) -> None:
        # Der Kern des gemessenen Falls: das aktuelle Konto trug zwei Tickets,
        # ein stillgelegtes achtzehn. Wer nach Menge sortiert, liegt falsch.
        sortiert = sort_candidates(self._kandidaten())  # type: ignore[arg-type]
        self.assertEqual(ID_B, sortiert[0].account_id)
        self.assertEqual(ID_C, sortiert[1].account_id)
        self.assertEqual(ID_A, sortiert[2].account_id)

    def test_konto_ohne_jedes_ticket_landet_hinten(self) -> None:
        treffer = parse_search([_user(ID_A, "Ohne Ticket"), _user(ID_B, "Mit Ticket")])
        mit = with_last_touch(
            treffer[1], [{"fields": {"updated": "2026-08-05T09:00:00.000+0200"}}]
        )
        ohne = with_last_touch(treffer[0], [])
        self.assertIsNone(ohne.last_touch)
        self.assertEqual(ID_B, sort_candidates([ohne, mit])[0].account_id)

    def test_zusammenfassen_haelt_alle_kennungen(self) -> None:
        mitglied = merge_accounts(self._kandidaten(), name="Reiner Beispiel")  # type: ignore[arg-type]
        self.assertEqual("Reiner Beispiel", mitglied.display_name)
        self.assertEqual((ID_B, ID_C, ID_A), mitglied.account_ids)

    def test_eigener_name_schlaegt_den_aus_jira(self) -> None:
        # Jira fuehrt denselben Menschen unter drei Schreibweisen. Wie jemand
        # genannt werden moechte, entscheidet nicht das Verzeichnis.
        ohne = merge_accounts(self._kandidaten())  # type: ignore[arg-type]
        self.assertEqual("Beispiel, Reinhold", ohne.display_name)

    def test_mitglied_ohne_konto_wird_abgelehnt(self) -> None:
        with self.assertRaises(ValueError):
            merge_accounts([])

    def test_mailadresse_wird_uebernommen_wenn_irgendein_konto_sie_zeigt(self) -> None:
        mitglied = merge_accounts(self._kandidaten())  # type: ignore[arg-type]
        self.assertEqual("vorname.nachname@example.invalid", mitglied.email)


class PersonensucheTest(unittest.TestCase):
    """Was aus den Antworten gelesen wird und was nicht."""

    def test_stillgelegte_und_maschinenkonten_fallen_raus(self) -> None:
        treffer = parse_search(
            [
                _user(ID_A, "Aktiver Mensch"),
                _user(ID_B, "Stillgelegt", active=False),
                _user(ID_C, "Automat", kind="app"),
            ]
        )
        self.assertEqual([ID_A], [k.account_id for k in treffer])

    def test_konto_ohne_sichtbare_mail_bleibt_brauchbar(self) -> None:
        # Nicht sichtbar heisst nicht: nicht vorhanden. Das Konto mit der
        # meisten Arbeit gab in der Messung keine Adresse heraus - es
        # auszusortieren waere der teuerste denkbare Fehler.
        treffer = parse_search([_user(ID_A, "Ohne Mail")])
        self.assertEqual(1, len(treffer))
        self.assertEqual("", treffer[0].email)
        self.assertTrue(treffer[0].account_id)

    def test_unbrauchbare_kennung_wird_uebergangen(self) -> None:
        self.assertEqual([], parse_search([_user('" OR "', "Boese")]))

    def test_personen_aus_dem_ticketbestand(self) -> None:
        # Der Weg ohne Benutzer-Schnittstelle: die Kennung steht im
        # assignee-Objekt jeder Suchantwort.
        issues = [
            {"fields": {"assignee": _user(ID_B, "Zweite Person", "z@example.invalid")}},
            {"fields": {"assignee": _user(ID_A, "Erste Person")}},
            {"fields": {"assignee": _user(ID_A, "Erste Person")}},
            {"fields": {"assignee": None}},
            {"fields": {}},
        ]
        leute = parse_people(issues)
        self.assertEqual(["Erste Person", "Zweite Person"], [p.display_name for p in leute])
        self.assertEqual("z@example.invalid", leute[1].email)

    def test_avatar_wird_in_groesster_groesse_gelesen(self) -> None:
        treffer = parse_search([_user(ID_A, "Mit Bild")])
        self.assertTrue(treffer[0].avatar_url.endswith(f"{ID_A}.png"))


class MerklisteTest(unittest.TestCase):
    """Speichern und Laden, auch bei verdorbenem Bestand."""

    def test_hin_und_zurueck(self) -> None:
        roster = Roster(
            members=[
                TeamMember(display_name="Reiner Beispiel", account_ids=(ID_A, ID_B)),
                TeamMember(display_name="Anna Muster", account_ids=(ID_C,)),
            ]
        )
        zurueck = from_storage(to_storage(roster))
        # Alphabetisch beim Laden, nicht in Eingabereihenfolge.
        self.assertEqual(
            ["Anna Muster", "Reiner Beispiel"], [m.display_name for m in zurueck.members]
        )
        self.assertEqual((ID_A, ID_B), zurueck.find("Reiner Beispiel").account_ids)  # type: ignore[union-attr]

    def test_verdorbener_bestand_verhindert_den_start_nicht(self) -> None:
        roh = [
            {"display_name": "Gut", "account_ids": [ID_A]},
            {"display_name": "Ohne Konto", "account_ids": []},
            {"display_name": "", "account_ids": [ID_B]},
            {"account_ids": [ID_C]},
            {"display_name": "Boese Kennung", "account_ids": ['" OR "']},
            "kein Eintrag",
        ]
        geladen = from_storage(roh)
        self.assertEqual(["Gut"], [m.display_name for m in geladen.members])

    def test_kein_bestand_ergibt_leere_liste(self) -> None:
        werte: tuple[object, ...] = (None, "", 42, {})
        for wert in werte:
            self.assertEqual([], from_storage(wert).members)

    def test_suche_ist_unabhaengig_von_gross_und_kleinschreibung(self) -> None:
        roster = Roster(members=[TeamMember(display_name="Reiner Beispiel", account_ids=(ID_A,))])
        self.assertIsNotNone(roster.find("reiner beispiel"))
        self.assertIsNone(roster.find("Niemand"))


class FremdsichtGrenzeTest(unittest.TestCase):
    """Was in der Fremdsicht NICHT entstehen darf."""

    def _issue(self, key: str, reporter: str) -> dict[str, Any]:
        """Ein Ticket in einem Rueckgabe-Status mit gegebenem Autor."""
        alt = (dt.datetime.now(dt.UTC) - dt.timedelta(days=90)).strftime(
            "%Y-%m-%dT%H:%M:%S.000+0000"
        )
        return {
            "key": key,
            "fields": {
                "summary": "Beispiel",
                "status": {"name": "In Arbeit", "statusCategory": {"key": "indeterminate"}},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
                "reporter": {"accountId": reporter, "displayName": "Autor"},
                "assignee": {"accountId": ID_A, "displayName": "Person"},
                "created": alt,
                "updated": alt,
            },
        }

    def test_ohne_buchungsdaten_kein_pile_of_shame(self) -> None:
        # Fuer fremde Personen werden Worklogs gar nicht erst geholt. Ohne sie
        # darf der Marker nicht gesetzt werden - geraten wird nicht.
        config = BoardConfig(active_status=("In Arbeit",))
        board = build_board(
            [self._issue("PROJ-1", ID_B)], config, account_id=ID_A, account_ids=[ID_A]
        )
        alle = [t for gruppe in board.groups for t in gruppe.tickets]
        self.assertEqual(1, len(alle))
        self.assertNotIn(Marker.PILE_OF_SHAME, alle[0].markers)

    def test_zweites_konto_macht_den_eigenen_vorgang_nicht_fremd(self) -> None:
        # Wer unter Konto A meldet und unter Konto B bearbeitet, meldet nicht
        # sich selbst fremd. Ohne die vollstaendige Kennungsliste passiert
        # genau das.
        config = BoardConfig(active_status=("In Arbeit",))
        board = build_board(
            [self._issue("PROJ-2", ID_B)],
            config,
            account_id=ID_A,
            account_ids=[ID_A, ID_B],
        )
        ticket = [t for gruppe in board.groups for t in gruppe.tickets][0]
        self.assertFalse(ticket.foreign_reporter)

    def test_gegenprobe_fremder_autor_wird_weiterhin_erkannt(self) -> None:
        # Ohne diese Gegenprobe wuerde der Test oben auch dann bestehen, wenn
        # foreign_reporter grundsaetzlich False waere.
        config = BoardConfig(active_status=("In Arbeit",))
        board = build_board(
            [self._issue("PROJ-3", ID_C)],
            config,
            account_id=ID_A,
            account_ids=[ID_A, ID_B],
        )
        ticket = [t for gruppe in board.groups for t in gruppe.tickets][0]
        self.assertTrue(ticket.foreign_reporter)


class AbgeschlossenTest(unittest.TestCase):
    """Die Rolle "Abgeschlossen" - fertig, aber weiterhin sichtbar.

    Michael hat am 11.08.2026 belegt, dass die frühere Gruppe "Abschluss
    offen" zwei verschiedene Dinge zusammenwarf: Status, die auf die
    Live-Setzung warten, und solche, die wirklich fertig sind. Ein Name kann
    beides nicht tragen.
    """

    def _config(self) -> BoardConfig:
        return BoardConfig(
            active_status=("In Arbeit",),
            closing_status=("Zur Übergabe",),
            done_status=("Erledigt",),
        )

    def _issue(self, key: str, status: str) -> dict[str, Any]:
        alt = (dt.datetime.now(dt.UTC) - dt.timedelta(days=200)).strftime(
            "%Y-%m-%dT%H:%M:%S.000+0000"
        )
        return {
            "key": key,
            "fields": {
                "summary": "Beispiel",
                "status": {"name": status, "statusCategory": {"key": "done"}},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
                "reporter": {"accountId": ID_B, "displayName": "Autor"},
                "created": alt,
                "updated": alt,
            },
        }

    def test_beide_status_landen_in_verschiedenen_gruppen(self) -> None:
        board = build_board(
            [self._issue("PROJ-1", "Zur Übergabe"), self._issue("PROJ-2", "Erledigt")],
            self._config(),
            account_id=ID_A,
        )
        rollen = {
            gruppe.role: [ticket.key for ticket in gruppe.tickets]
            for gruppe in board.groups
        }
        self.assertEqual(["PROJ-1"], rollen[Role.CLOSING])
        self.assertEqual(["PROJ-2"], rollen[Role.DONE])

    def test_abgeschlossen_steht_hinter_uebergabe(self) -> None:
        # Was fertig ist, gehoert ans Ende. Sonst schiebt sich der reine
        # Kontrollblick vor die Gruppen mit Handlungsbedarf.
        board = build_board(
            [self._issue("PROJ-1", "Erledigt"), self._issue("PROJ-2", "Zur Übergabe")],
            self._config(),
            account_id=ID_A,
        )
        reihenfolge = [gruppe.role for gruppe in board.groups]
        self.assertLess(
            reihenfolge.index(Role.CLOSING), reihenfolge.index(Role.DONE)
        )

    def test_abgeschlossen_erzeugt_keinen_pile_of_shame(self) -> None:
        # Eine Schwelle wuerde Tickets anmahnen, an denen nichts mehr zu tun
        # ist. Die Gegenprobe unten zeigt, dass die Schwelle sonst greift.
        config = BoardConfig(
            closing_status=("Zur Übergabe",),
            done_status=("Erledigt",),
            thresholds={Role.CLOSING: 1.0, Role.DONE: 1.0},
        )
        board = build_board(
            [self._issue("PROJ-1", "Erledigt"), self._issue("PROJ-2", "Zur Übergabe")],
            config,
            account_id=ID_A,
            worklogs={
                "PROJ-1": WorklogInfo(count=0),
                "PROJ-2": WorklogInfo(count=0),
            },
        )
        marker = {
            ticket.key: ticket.markers
            for gruppe in board.groups
            for ticket in gruppe.tickets
        }
        self.assertNotIn(Marker.PILE_OF_SHAME, marker["PROJ-1"])
        # Gegenprobe: in der Uebergabe-Gruppe greift dieselbe Schwelle sehr wohl.
        self.assertIn(Marker.PILE_OF_SHAME, marker["PROJ-2"])

    def test_abgeschlossen_traegt_ueberhaupt_keine_merkmale(self) -> None:
        # Michael am 11.08.2026: "Tickets im Status Abgeschlossen sind final,
        # die koennen nicht mehr verwaisen." Das gilt fuer JEDES Merkmal -
        # ein fertiges Ticket ist nicht blockiert, und seine Prioritaet
        # fordert zu nichts mehr auf. Jedes Merkmal hier waere eine
        # Aufforderung ohne Adressat, und die rote Einfaerbung stiehlt die
        # Aufmerksamkeit den Gruppen, in denen wirklich etwas zu tun ist.
        config = BoardConfig(
            active_status=("In Arbeit",),
            done_status=("Erledigt",),
            priorities=("Blocker", "Medium"),
            high_priority_ranks=1,
            stale_days=30,
        )
        alt = self._issue("PROJ-1", "Erledigt")
        alt["fields"]["priority"] = {"name": "Blocker"}
        alt["fields"]["issuelinks"] = [
            {
                "type": {"inward": "is blocked by"},
                "inwardIssue": {
                    "fields": {"status": {"statusCategory": {"key": "indeterminate"}}}
                },
            }
        ]
        board = build_board([alt], config, account_id=ID_A)
        ticket = [t for gruppe in board.groups for t in gruppe.tickets][0]
        self.assertEqual((), ticket.markers)

        # Gegenprobe: dasselbe Ticket in einer offenen Rolle traegt sehr wohl
        # Merkmale - ohne sie belegte der Test oben nur, dass die Testdaten
        # keine ausloesen.
        offen = BoardConfig(
            active_status=("Erledigt",),
            priorities=("Blocker", "Medium"),
            high_priority_ranks=1,
            stale_days=30,
        )
        vergleich = build_board([alt], offen, account_id=ID_A)
        andere = [t for gruppe in vergleich.groups for t in gruppe.tickets][0]
        self.assertIn(Marker.STALE, andere.markers)
        self.assertIn(Marker.BLOCKED, andere.markers)
        self.assertIn(Marker.HIGH_PRIORITY, andere.markers)


class VerdrahtungTest(unittest.TestCase):
    """Was der Faden aus einer Ansicht macht.

    Der Faden wird nur gebaut, nicht gestartet - geprueft wird die Abfrage,
    die er stellen wuerde. Ein laufender Faden braeuchte eine echte Instanz.
    """

    def _worker(self, mode: str, member: TeamMember | None = None) -> TicketBoardWorker:
        config = BoardConfig(closing_status=("Schliessen",))
        return TicketBoardWorker(Settings(), config, mode, member=member)

    def test_team_ansicht_fragt_die_kennungen_ab(self) -> None:
        mitglied = TeamMember(display_name="Reiner Beispiel", account_ids=(ID_A, ID_B))
        ausdruecke = self._worker(MODE_TEAM, mitglied)._jqls("eigene-kennung")
        self.assertEqual(2, len(ausdruecke))
        for ausdruck in ausdruecke:
            self.assertIn(f'"{ID_A}"', ausdruck)
            self.assertIn(f'"{ID_B}"', ausdruck)
            self.assertNotIn("currentUser()", ausdruck)

    def test_team_ansicht_ohne_person_bricht_ab(self) -> None:
        # Ohne Kennung faellt die Abfrage auf currentUser() zurueck. Dann
        # staenden die eigenen Tickets unter fremdem Namen in der Ansicht -
        # ein stiller Fehler, der wie ein Ergebnis aussieht.
        with self.assertRaises(ValueError):
            self._worker(MODE_TEAM, None)
        with self.assertRaises(ValueError):
            self._worker(MODE_TEAM, TeamMember(display_name="Ohne Konto"))

    def test_eigene_ansicht_bleibt_unveraendert(self) -> None:
        for ausdruck in self._worker(MODE_ASSIGNED)._jqls("eigene-kennung"):
            self.assertIn("currentUser()", ausdruck)

    def test_die_abfrage_deckt_beide_listen_ab(self) -> None:
        # Jira zaehlt beide als "Done" - sie fallen also gemeinsam durch
        # statusCategory != Done und muessen zusammen abgefragt werden.
        config = BoardConfig(closing_status=("Zur Übergabe",), done_status=("Erledigt",))
        worker = TicketBoardWorker(Settings(), config, MODE_ASSIGNED)
        zusammen = " ".join(worker._jqls("eigene-kennung"))
        self.assertIn("Zur Übergabe", zusammen)
        self.assertIn("Erledigt", zusammen)

    def test_fremdsicht_kennt_alle_konten_der_person(self) -> None:
        # Der Abruf gibt dem Kern die eigene Kennung des angemeldeten
        # Benutzers zurueck - in der Fremdsicht also die falsche. Der Faden
        # muss beides ersetzen: die Sicht auf die gemeinte Person UND deren
        # vollstaendige Kennungsliste.
        #
        # Der Fall ist bewusst so gewaehlt, dass nur die Liste ihn traegt: die
        # Person meldet unter ihrem ZWEITEN Konto. Mit nur einer Kennung sind
        # beide Wege austauschbar, und eine Mutation an einem von ihnen bliebe
        # unbemerkt - gemessen am 11.08.2026, beide Mutationen blieben gruen.
        eigenes_zweitkonto = self._fremd_board(reporter=ID_C)
        self.assertFalse(eigenes_zweitkonto.foreign_reporter)

        # Gegenprobe: ein wirklich fremder Autor wird weiterhin erkannt. Ohne
        # sie bestuende der Test auch dann, wenn foreign_reporter immer False
        # waere.
        gemeldet_von_dritten = self._fremd_board(reporter="9999abcd9999abcd9999abcd")
        self.assertTrue(gemeldet_von_dritten.foreign_reporter)

    def _fremd_board(self, reporter: str) -> Ticket:
        """Laesst den Faden mit eingesetztem Client laufen und gibt das Ticket.

        Die gemeinte Person fuehrt zwei Konten (ID_B und ID_C), der
        angemeldete Benutzer ist ein dritter (ID_A).

        Args:
            reporter:
                Kennung des Autors des einen Tickets.

        Returns:
            Das einzige Ticket der aufgebauten Ansicht.
        """
        import asyncio

        from jira_timesheet_qt.ui import ticket_board_worker as modul

        alt = (dt.datetime.now(dt.UTC) - dt.timedelta(days=90)).strftime(
            "%Y-%m-%dT%H:%M:%S.000+0000"
        )
        issue: dict[str, Any] = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Beispiel",
                "status": {"name": "In Arbeit", "statusCategory": {"key": "indeterminate"}},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
                "reporter": {"accountId": reporter, "displayName": "Autor"},
                "assignee": {"accountId": ID_B, "displayName": "Person"},
                "created": alt,
                "updated": alt,
            },
        }

        class FakeClient:
            """Liefert eine feste Antwort und die EIGENE Kennung dazu."""

            def __init__(self, **_kwargs: object) -> None:
                pass

            async def fetch_issues(
                self, _builder: object, _fields: object
            ) -> tuple[str, list[dict[str, object]]]:
                # Jira meldet hier immer die Kennung des angemeldeten
                # Benutzers - in der Fremdsicht also die falsche.
                return ID_A, [issue]

        original = modul.JiraClient  # type: ignore[attr-defined]
        modul.JiraClient = FakeClient  # type: ignore[attr-defined, assignment]
        try:
            mitglied = TeamMember(display_name="Fremde Person", account_ids=(ID_B, ID_C))
            worker = TicketBoardWorker(
                Settings(), BoardConfig(active_status=("In Arbeit",)), MODE_TEAM, member=mitglied
            )
            board = asyncio.run(worker._fetch())
        finally:
            modul.JiraClient = original  # type: ignore[attr-defined]
        return [t for gruppe in board.groups for t in gruppe.tickets][0]

    def test_einstellung_erreicht_den_kern(self) -> None:
        # Die Uebersetzung Einstellungen -> Kern ist die Stelle, an der ein
        # neues Feld am leichtesten haengen bleibt: gespeichert, aber nie
        # ausgewertet. Die Gegenprobe unten zeigt, dass der Weg wirklich
        # ueber die Einstellung fuehrt und nicht ueber einen Vorgabewert.
        settings = Settings(board_done_status=["Erledigt"])
        self.assertEqual(("Erledigt",), config_from(settings).done_status)
        self.assertEqual((), config_from(Settings()).done_status)


if __name__ == "__main__":
    unittest.main()
