"""Tests fuer den Kern der Ticket-Ansichten.

Alle Zeitpunkte sind fest verdrahtet. Ein Test, der am heutigen Datum haengt,
ist gruen bis zum naechsten Monatswechsel und danach ohne Code-Aenderung rot.
"""

from __future__ import annotations

import datetime as dt

import pytest

from jira_timesheet_qt.services.ticket_board import (
    AccountIdError,
    BoardConfig,
    Marker,
    Role,
    WorklogInfo,
    assigned_jql,
    build_board,
    build_statistics,
    check_account_id,
    closing_jql,
    pending_worklog_keys,
    relevant_jql,
    workdays_between,
)

TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 8, 5, 12, 0, tzinfo=TZ)
ACCOUNT = "712020:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER = "712020:11111111-2222-3333-4444-555555555555"

# Eine Konfiguration, wie sie ein Anwender pflegen wuerde. Bewusst mit
# gemischter Schreibweise, um den case-insensitiven Vergleich zu pruefen.
CONFIG = BoardConfig(
    active_status=("In Arbeit", "In Umsetzung"),
    backlog_status=("Bereit",),
    handback_status=("Bewertung",),
    acceptance_status=("Abnahme",),
    closing_status=("Abschluss",),
)


def stamp(moment: dt.datetime) -> str:
    """Formatiert einen Zeitpunkt so, wie Jira ihn liefert."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000%z")


def issue(
    key: str,
    status: str,
    *,
    category: str = "indeterminate",
    updated: dt.datetime | None = None,
    created: dt.datetime | None = None,
    priority: str = "Medium",
    issue_type: str = "Story",
    reporter: str = ACCOUNT,
    links: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Baut eine Suchantwort-Zeile, wie Jira sie liefert."""
    return {
        "key": key,
        "fields": {
            "summary": f"Titel zu {key}",
            "status": {"name": status, "statusCategory": {"key": category}},
            "priority": {"name": priority},
            "issuetype": {"name": issue_type},
            "reporter": {"accountId": reporter, "displayName": "Wer Auch Immer"},
            "assignee": {"accountId": ACCOUNT, "displayName": "Ich Selbst"},
            "created": stamp(created or (NOW - dt.timedelta(days=400))),
            "updated": stamp(updated or NOW),
            "issuelinks": links or [],
        },
    }


class TestArbeitszeit:
    """Liegezeit muss in Arbeitstagen rechnen, nicht in Kalendertagen."""

    def test_wochenende_zaehlt_nicht_als_arbeitszeit(self) -> None:
        # Freitag 12 Uhr bis Montag 12 Uhr sind drei Kalendertage.
        freitag = dt.datetime(2026, 7, 31, 12, 0, tzinfo=TZ)
        montag = dt.datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
        assert (montag - freitag).days == 3
        # Aber nur ein Arbeitstag: Freitagnachmittag plus Montagvormittag.
        assert workdays_between(freitag, montag) == pytest.approx(1.0, abs=0.01)

    def test_ohne_startzeitpunkt_null(self) -> None:
        assert workdays_between(None, NOW) == 0.0


class TestAbfragen:
    """Die JQL-Ausdruecke muessen die gemessenen Eigenheiten einhalten."""

    def test_zugewiesene_schliessen_erledigte_aus(self) -> None:
        assert "statusCategory != Done" in assigned_jql()

    def test_relevante_nutzen_updatedby_mit_kennung_statt_currentuser(self) -> None:
        # currentUser() laesst sich NICHT als Argument verschachteln - das
        # ist ein Syntaxfehler in Jira, kein Stilfrage.
        jql = relevant_jql(ACCOUNT, window_days=90)
        assert f'issue in updatedBy("{ACCOUNT}")' in jql
        assert "updatedBy(currentUser())" not in jql

    def test_relevante_suchen_erwaehnungen_ueber_die_kennung(self) -> None:
        assert f'comment ~ "{ACCOUNT}"' in relevant_jql(ACCOUNT)

    def test_relevante_nutzen_niemals_commentedby(self) -> None:
        # commentedBy() steht in der Autovervollstaendigung mancher
        # Instanzen, liefert aber nichts oder HTTP 400.
        assert "commentedBy" not in relevant_jql(ACCOUNT)

    def test_relevante_schliessen_eigene_aus(self) -> None:
        assert "assignee != currentUser()" in relevant_jql(ACCOUNT)

    def test_zeitfenster_ist_abschaltbar(self) -> None:
        assert "updated >=" in relevant_jql(ACCOUNT, window_days=30)
        assert "updated >=" not in relevant_jql(ACCOUNT, window_days=0)

    @pytest.mark.parametrize(
        "boese",
        ['" OR key = "ABC-1', "abc def", "", 'x"y', "a\\b"],
    )
    def test_unbrauchbare_kennung_wird_abgelehnt(self, boese: str) -> None:
        # Eine Zeichenkette aus einer Fremdquelle gehoert nie ungeprueft in
        # ein Ausdrucksfeld.
        with pytest.raises(AccountIdError):
            relevant_jql(boese)

    def test_echte_kennung_wird_durchgelassen(self) -> None:
        assert check_account_id(ACCOUNT) == ACCOUNT

    def test_abschluss_abfrage_ohne_konfiguration_ist_leer(self) -> None:
        assert closing_jql(()) == ""

    def test_abschluss_abfrage_zitiert_die_status(self) -> None:
        assert '"Abschluss"' in closing_jql(("Abschluss",))


class TestRollen:
    """Statuszuordnung ist Konfiguration, mit Rueckfall auf die Kategorie."""

    def test_konfigurierter_status_gewinnt(self) -> None:
        assert CONFIG.role_of("In Arbeit", "indeterminate") is Role.ACTIVE
        assert CONFIG.role_of("Bewertung", "indeterminate") is Role.HANDBACK

    def test_vergleich_ist_unabhaengig_von_gross_und_kleinschreibung(self) -> None:
        assert CONFIG.role_of("IN ARBEIT", "indeterminate") is Role.ACTIVE
        assert CONFIG.role_of("  in arbeit  ", "indeterminate") is Role.ACTIVE

    def test_ohne_konfiguration_entscheidet_die_kategorie(self) -> None:
        leer = BoardConfig()
        assert leer.role_of("Irgendwas", "indeterminate") is Role.ACTIVE
        assert leer.role_of("Irgendwas", "new") is Role.BACKLOG
        assert leer.role_of("Irgendwas", "done") is Role.CLOSING

    def test_unbekannte_kategorie_bleibt_unbekannt(self) -> None:
        assert BoardConfig().role_of("Irgendwas", "") is Role.UNKNOWN

    def test_nicht_zugeordnete_status_werden_gemeldet(self) -> None:
        board = build_board([issue("A-1", "Voellig Neu")], CONFIG, NOW)
        # Sie duerfen nicht still in einen Sammeltopf fallen - sonst merkt
        # niemand, dass die Konfiguration nachzuziehen ist.
        assert board.unknown_status == ["Voellig Neu"]


class TestPrioritaet:
    """Rangfolge und obere Gruppe."""

    def test_rangfolge_entspricht_der_absprache(self) -> None:
        assert CONFIG.priority_rank("gesetzlich") < CONFIG.priority_rank("Blocker")
        assert CONFIG.priority_rank("Blocker") < CONFIG.priority_rank("Kritisch")
        assert CONFIG.priority_rank("Kritisch") < CONFIG.priority_rank("High")
        assert CONFIG.priority_rank("High") < CONFIG.priority_rank("Medium")
        assert CONFIG.priority_rank("Low") < CONFIG.priority_rank("None")

    def test_unbekannte_stufe_draengt_sich_nicht_nach_vorn(self) -> None:
        assert CONFIG.priority_rank("Erfunden") > CONFIG.priority_rank("None")

    def test_obere_gruppe_bleibt_selten(self) -> None:
        assert CONFIG.is_high_priority("Kritisch")
        assert not CONFIG.is_high_priority("High")
        assert not CONFIG.is_high_priority("")


class TestMarker:
    """Handlungsbedarf, mehrere Marker gleichzeitig sind moeglich."""

    def test_rueckgabe_nur_bei_fremdem_autor(self) -> None:
        fremd = build_board(
            [issue("A-1", "Bewertung", reporter=OTHER)], CONFIG, NOW, account_id=ACCOUNT
        )
        eigen = build_board(
            [issue("A-2", "Bewertung", reporter=ACCOUNT)], CONFIG, NOW, account_id=ACCOUNT
        )
        assert fremd.tickets[0].has(Marker.HANDBACK)
        assert not eigen.tickets[0].has(Marker.HANDBACK)

    def test_verwaist_ab_der_schwelle(self) -> None:
        alt = build_board(
            [issue("A-1", "Bewertung", updated=NOW - dt.timedelta(days=200))], CONFIG, NOW
        )
        jung = build_board(
            [issue("A-2", "Bewertung", updated=NOW - dt.timedelta(days=100))], CONFIG, NOW
        )
        assert alt.tickets[0].has(Marker.STALE)
        assert not jung.tickets[0].has(Marker.STALE)

    def test_mehrere_marker_gleichzeitig(self) -> None:
        board = build_board(
            [
                issue(
                    "A-1",
                    "Bewertung",
                    updated=NOW - dt.timedelta(days=300),
                    priority="Kritisch",
                    reporter=OTHER,
                )
            ],
            CONFIG,
            NOW,
            account_id=ACCOUNT,
        )
        ticket = board.tickets[0]
        assert ticket.has(Marker.HANDBACK)
        assert ticket.has(Marker.STALE)
        assert ticket.has(Marker.HIGH_PRIORITY)

    def test_rueckgabe_status_mit_eigenem_autor_bleibt_bei_mir(self) -> None:
        # Am echten Bestand aufgefallen: Tickets in einem Rueckgabe-Status,
        # deren Autor man selbst ist, landeten in einer Gruppe namens "nicht
        # bearbeiten" und lagen dort ewig. Es gibt aber niemanden, dem man
        # sie zurueckgeben koennte - der Ball liegt bei einem selbst.
        eigen = build_board(
            [issue("A-1", "Bewertung", reporter=ACCOUNT)], CONFIG, NOW, account_id=ACCOUNT
        )
        fremd = build_board(
            [issue("A-2", "Bewertung", reporter=OTHER)], CONFIG, NOW, account_id=ACCOUNT
        )
        assert eigen.tickets[0].role is Role.ACTIVE
        assert fremd.tickets[0].role is Role.HANDBACK

    def test_ohne_eigene_kennung_gibt_es_keinen_rueckgabe_marker(self) -> None:
        # Beim Bauen aufgefallen und deshalb festgehalten: wer build_board
        # ohne account_id ruft, bekommt eine dauerhaft leere Rueckgabe-Gruppe
        # und merkt nichts davon. Ein fremder Autor ist ohne die eigene
        # Kennung schlicht nicht bestimmbar - die Anwendung MUSS sie reichen.
        ohne = build_board([issue("A-1", "Bewertung", reporter=OTHER)], CONFIG, NOW)
        mit = build_board(
            [issue("A-1", "Bewertung", reporter=OTHER)], CONFIG, NOW, account_id=ACCOUNT
        )
        assert not ohne.tickets[0].foreign_reporter
        assert not ohne.tickets[0].has(Marker.HANDBACK)
        assert mit.tickets[0].has(Marker.HANDBACK)

    def test_blockiert_nur_bei_offenem_vorgaenger(self) -> None:
        def link(kategorie: str) -> list[dict[str, object]]:
            return [
                {
                    "type": {"inward": "has to be done after"},
                    "inwardIssue": {
                        "fields": {"status": {"statusCategory": {"key": kategorie}}}
                    },
                }
            ]

        offen = build_board([issue("A-1", "In Arbeit", links=link("new"))], CONFIG, NOW)
        fertig = build_board([issue("A-2", "In Arbeit", links=link("done"))], CONFIG, NOW)
        assert offen.tickets[0].has(Marker.BLOCKED)
        # Ein erledigter Vorgaenger blockiert nicht - genau das unterscheidet
        # eine echte Abhaengigkeit von einer historischen.
        assert not fertig.tickets[0].has(Marker.BLOCKED)


class TestPileOfShame:
    """Die Regel muss das Dauerticket vom vergessenen Ticket trennen."""

    def _board(self, key: str, updated_days: int, worklog: WorklogInfo | None):
        return build_board(
            [issue(key, "In Arbeit", updated=NOW - dt.timedelta(days=updated_days))],
            CONFIG,
            NOW,
            worklogs={key: worklog} if worklog is not None else None,
        )

    def test_dauerticket_mit_frischer_buchung_faellt_heraus(self) -> None:
        # Nachgebildet nach einem echten Fall: seit viereinhalb Jahren offen,
        # 49 Buchungen, die letzte vor fuenf Tagen. Es ist in Benutzung,
        # nicht vergessen - und braucht keine Ausnahmeliste.
        board = self._board(
            "A-1", updated_days=5, worklog=WorklogInfo(count=49, last=NOW - dt.timedelta(days=5))
        )
        assert not board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_lange_liegezeit_ohne_buchung_faellt_hinein(self) -> None:
        # Ebenfalls ein echter Fall: Status behauptet Arbeit, die letzte
        # gebuchte Stunde ist 895 Tage her.
        board = self._board(
            "A-2", updated_days=149, worklog=WorklogInfo(count=7, last=NOW - dt.timedelta(days=895))
        )
        assert board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_nie_gebucht_faellt_hinein(self) -> None:
        board = self._board("A-3", updated_days=56, worklog=WorklogInfo(count=0, last=None))
        assert board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_ohne_buchungslage_wird_nichts_behauptet(self) -> None:
        # Lieber keinen Marker als einen geratenen.
        board = self._board("A-4", updated_days=900, worklog=None)
        assert not board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_rueckgabe_ist_kein_pile_of_shame(self) -> None:
        # Dort liegt der Ball bei jemand anderem. Die Handlung heisst
        # zurueckgeben, nicht aufholen.
        board = build_board(
            [issue("A-5", "Bewertung", updated=NOW - dt.timedelta(days=400), reporter=OTHER)],
            CONFIG,
            NOW,
            account_id=ACCOUNT,
            worklogs={"A-5": WorklogInfo(count=0, last=None)},
        )
        assert not board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_backlog_ist_kein_pile_of_shame(self) -> None:
        # Vorrat ist keine Schuld.
        board = build_board(
            [issue("A-6", "Bereit", category="new", updated=NOW - dt.timedelta(days=400))],
            CONFIG,
            NOW,
            worklogs={"A-6": WorklogInfo(count=0, last=None)},
        )
        assert not board.tickets[0].has(Marker.PILE_OF_SHAME)

    def test_nur_auffaellige_tickets_brauchen_einen_worklog_abruf(self) -> None:
        board = build_board(
            [
                issue("A-1", "In Arbeit", updated=NOW - dt.timedelta(days=100)),
                issue("A-2", "In Arbeit", updated=NOW),
                issue("A-3", "Bereit", category="new", updated=NOW - dt.timedelta(days=400)),
            ],
            CONFIG,
            NOW,
        )
        # Nur das alte aktive Ticket. Das frische braucht keinen Abruf, das
        # Backlog-Ticket kann gar nicht in den Pile of Shame geraten.
        assert pending_worklog_keys(board, CONFIG) == ["A-1"]


class TestGruppenUndSortierung:
    """Gruppenreihenfolge und die Zugreihenfolge im Backlog."""

    def test_aktive_gruppe_steht_vor_dem_backlog(self) -> None:
        board = build_board(
            [
                issue("A-1", "Bereit", category="new"),
                issue("A-2", "In Arbeit"),
            ],
            CONFIG,
            NOW,
        )
        assert [g.role for g in board.groups] == [Role.ACTIVE, Role.BACKLOG]

    def test_backlog_zieht_fehler_vor(self) -> None:
        board = build_board(
            [
                issue("A-1", "Bereit", category="new", issue_type="Story", priority="Kritisch"),
                issue("A-2", "Bereit", category="new", issue_type="Bug", priority="Low"),
                issue("A-3", "Bereit", category="new", issue_type="Bug", priority="High"),
            ],
            CONFIG,
            NOW,
        )
        backlog = next(g for g in board.groups if g.role is Role.BACKLOG)
        # Erst alle Fehler nach Prioritaet, danach alles andere - auch wenn
        # die Story die hoehere Stufe traegt.
        assert [t.key for t in backlog.tickets] == ["A-3", "A-2", "A-1"]

    def test_andere_gruppen_zeigen_das_aelteste_zuerst(self) -> None:
        board = build_board(
            [
                issue("A-1", "In Arbeit", updated=NOW - dt.timedelta(days=1)),
                issue("A-2", "In Arbeit", updated=NOW - dt.timedelta(days=90)),
            ],
            CONFIG,
            NOW,
        )
        assert [t.key for t in board.groups[0].tickets] == ["A-2", "A-1"]

    def test_doppelte_schluessel_werden_zusammengefasst(self) -> None:
        # Die relevanten Tickets stammen aus mehreren Quellen und
        # ueberschneiden sich.
        board = build_board([issue("A-1", "In Arbeit"), issue("A-1", "In Arbeit")], CONFIG, NOW)
        assert board.count == 1


class TestAuswertung:
    """Zulauf, Abgang und Altersverteilung fuer die Diagramme."""

    def _erledigt(self, key: str, angelegt: dt.datetime, fertig: dt.datetime) -> dict[str, object]:
        row = issue(key, "Fertig", category="done", created=angelegt)
        fields = row["fields"]
        assert isinstance(fields, dict)
        fields["statuscategorychangedate"] = stamp(fertig)
        return row

    def test_saldo_zeigt_ob_der_bestand_waechst(self) -> None:
        stats = build_statistics(
            [
                issue("A-1", "In Arbeit", created=dt.datetime(2026, 7, 2, tzinfo=TZ)),
                issue("A-2", "In Arbeit", created=dt.datetime(2026, 7, 3, tzinfo=TZ)),
                self._erledigt(
                    "A-3",
                    dt.datetime(2026, 7, 1, tzinfo=TZ),
                    dt.datetime(2026, 7, 20, tzinfo=TZ),
                ),
            ],
            now=NOW,
        )
        assert stats.inflow_total == 3
        assert stats.outflow_total == 1
        assert stats.balance_total == 2

    def test_monatsreihe_hat_keine_luecken(self) -> None:
        stats = build_statistics(
            [
                issue("A-1", "In Arbeit", created=dt.datetime(2026, 3, 1, tzinfo=TZ)),
                issue("A-2", "In Arbeit", created=dt.datetime(2026, 8, 1, tzinfo=TZ)),
            ],
            now=NOW,
            months=0,
        )
        # Maerz bis August, auch die bewegungslosen Monate dazwischen. Ein
        # fehlender Monat wuerde die Zeitachse stauchen.
        assert [m.month for m in stats.months] == [
            "2026-03",
            "2026-04",
            "2026-05",
            "2026-06",
            "2026-07",
            "2026-08",
        ]

    def test_kumulierter_bestand_zaehlt_mit(self) -> None:
        stats = build_statistics(
            [
                issue("A-1", "In Arbeit", created=dt.datetime(2026, 6, 1, tzinfo=TZ)),
                issue("A-2", "In Arbeit", created=dt.datetime(2026, 7, 1, tzinfo=TZ)),
                issue("A-3", "In Arbeit", created=dt.datetime(2026, 8, 1, tzinfo=TZ)),
            ],
            now=NOW,
            months=0,
        )
        assert [m.cumulative for m in stats.months] == [1, 2, 3]

    def test_abgang_kommt_aus_statuscategorychangedate(self) -> None:
        # resolutiondate war in der vermessenen Instanz nur bei der Haelfte
        # der erledigten Tickets gesetzt. Wer damit rechnet, halbiert den
        # Durchsatz, ohne es zu merken.
        row = issue("A-1", "Fertig", category="done")
        fields = row["fields"]
        assert isinstance(fields, dict)
        fields["resolutiondate"] = None
        fields["statuscategorychangedate"] = stamp(NOW - dt.timedelta(days=10))
        stats = build_statistics([row], now=NOW)
        assert stats.outflow_total == 1
        assert stats.resolved_recent == 1

    def test_durchlaufzeit_rechnet_in_arbeitstagen(self) -> None:
        stats = build_statistics(
            [
                self._erledigt(
                    "A-1",
                    dt.datetime(2026, 7, 6, 8, 0, tzinfo=TZ),
                    dt.datetime(2026, 7, 10, 18, 0, tzinfo=TZ),
                )
            ],
            now=NOW,
        )
        # Montag frueh bis Freitag Abend sind fuenf Arbeitstage.
        assert stats.lead_time_median == pytest.approx(5.0, abs=0.1)

    def test_altersklassen_bleiben_vollstaendig(self) -> None:
        stats = build_statistics(
            [issue("A-1", "In Arbeit", updated=NOW - dt.timedelta(days=1))], now=NOW
        )
        # Auch leere Klassen gehoeren dazu, sonst hat das Diagramm Luecken.
        assert len(stats.buckets) == 4
        assert stats.buckets[0].count == 1
