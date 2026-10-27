"""Tests fuer den Kern des Ticketflusses.

Alle Namen sind erfunden, alle Zeitpunkte fest - kein Test haengt am heutigen Datum.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from jira_timesheet_qt.services import ticket_flow
from jira_timesheet_qt.services.ticket_board import AccountIdError
from jira_timesheet_qt.services.ticket_flow import (
    EDGE_ACCEPTANCE,
    EDGE_HANDOVER,
    EDGE_KINDS,
    EDGE_ORDER,
    FLOW_1M,
    FLOW_12M,
    FLOW_ALL,
    FLOW_FIELDS,
    FLOW_YTD,
    build_star,
    extract_flow,
    flow_jqls,
    flow_since,
    load_flow,
    merge_accounts,
    merge_load,
    top_contacts,
)

TZ = dt.timezone(dt.timedelta(hours=2))
ACCOUNT = "712020:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

ANNA, BERT, CARL, DORA = "id-anna", "id-bert", "id-carl", "id-dora"
NAMES = {ANNA: "Muster, Anna", BERT: "Beispiel, Bert", CARL: "Mustermann, Carl", DORA: "Probe, Dora"}


def ts(day: int, month: int = 8) -> str:
    """Zeitstempel im Jira-Format, 2026."""
    return dt.datetime(2026, month, day, 9, tzinfo=TZ).isoformat()


def person(account: str) -> dict[str, str]:
    """Personen-Objekt wie in der API."""
    return {"accountId": account, "displayName": NAMES[account]}


def issue(key: str, reporter: str, assignee: str | None, created: str = "") -> dict[str, Any]:
    """Rohantwort der Suche."""
    return {
        "key": key,
        "fields": {
            "created": created or ts(1),
            "reporter": person(reporter),
            "assignee": person(assignee) if assignee else None,
        },
    }


def handover(when: str, old: str | None, new: str | None) -> dict[str, Any]:
    """Ein Bearbeiterwechsel im Aenderungsprotokoll."""
    return {
        "created": when,
        "items": [
            {
                "field": "assignee",
                "fieldId": "assignee",
                "from": old,
                "fromString": NAMES[old] if old else None,
                "to": new,
                "toString": NAMES[new] if new else None,
            }
        ],
    }


class TestKanten:
    def test_ohne_wechsel_ist_der_heutige_bearbeiter_der_erste(self) -> None:
        data = extract_flow([issue("X-1", ANNA, BERT)], {"X-1": []})
        assert [(e.kind, e.source, e.target) for e in data.edges] == [(EDGE_ORDER, ANNA, BERT)]

    def test_eigenes_ticket_ist_kein_auftrag(self) -> None:
        data = extract_flow([issue("X-1", ANNA, ANNA)], {"X-1": []})
        assert data.edges == ()

    def test_der_erste_bearbeiter_kommt_aus_dem_protokoll(self) -> None:
        # Heute bearbeitet Carl, angefangen hat Bert - der Auftrag ging an Bert.
        log = [handover(ts(5), BERT, CARL)]
        data = extract_flow([issue("X-1", ANNA, CARL)], {"X-1": log})
        assert [(e.kind, e.source, e.target) for e in data.edges] == [
            (EDGE_ORDER, ANNA, BERT),
            (EDGE_HANDOVER, BERT, CARL),
        ]

    def test_unzugewiesen_angelegt_zaehlt_die_erste_zuweisung(self) -> None:
        log = [handover(ts(3), None, BERT), handover(ts(7), BERT, CARL)]
        data = extract_flow([issue("X-1", ANNA, CARL)], {"X-1": log})
        order, hand = data.edges
        assert (order.kind, order.target, order.when.day) == (EDGE_ORDER, BERT, 3)
        assert (hand.kind, hand.source, hand.target) == (EDGE_HANDOVER, BERT, CARL)

    def test_ein_leerer_zwischenstand_unterbricht_die_kette_nicht(self) -> None:
        log = [handover(ts(3), BERT, None), handover(ts(4), None, CARL)]
        data = extract_flow([issue("X-1", ANNA, CARL)], {"X-1": log})
        assert [(e.kind, e.source, e.target) for e in data.edges][1:] == [(EDGE_HANDOVER, BERT, CARL)]

    def test_das_protokoll_wird_zeitlich_sortiert(self) -> None:
        log = [handover(ts(9), CARL, DORA), handover(ts(5), BERT, CARL)]
        data = extract_flow([issue("X-1", ANNA, DORA)], {"X-1": log})
        assert [(e.source, e.target) for e in data.edges] == [(ANNA, BERT), (BERT, CARL), (CARL, DORA)]

    def test_ohne_protokoll_wird_nicht_geraten(self) -> None:
        data = extract_flow([issue("X-1", ANNA, BERT)], {})
        assert data.edges == ()
        assert data.missing == ("X-1",)
        assert data.people[ANNA] == "Anna Muster"

    def test_dubletten_zaehlen_einmal(self) -> None:
        data = extract_flow([issue("X-1", ANNA, BERT), issue("X-1", ANNA, BERT)], {"X-1": []})
        assert len(data.edges) == 1

    def test_titel_fuer_die_ticketliste(self) -> None:
        raw = issue("X-1", ANNA, BERT)
        raw["fields"]["summary"] = "Kaffee nachfuellen"
        assert extract_flow([raw], {}).titles == {"X-1": "Kaffee nachfuellen"}

    def test_namen_in_leseform(self) -> None:
        data = extract_flow([issue("X-1", ANNA, BERT)], {"X-1": []})
        assert data.people == {ANNA: "Anna Muster", BERT: "Bert Beispiel"}


def _netz() -> Any:
    """Anna in der Mitte: liefert an Bert und Carl, bekommt von Dora."""
    issues = [
        issue("X-1", ANNA, BERT, ts(1)),
        issue("X-2", ANNA, BERT, ts(2)),
        issue("X-3", ANNA, CARL, ts(3)),
        issue("X-4", DORA, ANNA, ts(4)),
        issue("X-5", BERT, CARL, ts(5)),  # ohne Anna - bleibt aussen vor
        issue("X-6", DORA, DORA, ts(6)),
    ]
    histories: dict[str, list[dict[str, Any]]] = {i["key"]: [] for i in issues}
    histories["X-6"] = [handover(ts(20), DORA, ANNA)]
    return extract_flow(issues, histories)


def done(ticket: dict[str, Any], when: str | None) -> dict[str, Any]:
    """Setzt ein Ticket auf Fertig, when = statuscategorychangedate."""
    ticket["fields"]["status"] = {"name": "Erledigt", "statusCategory": {"key": "done"}}
    if when is not None:
        ticket["fields"]["statuscategorychangedate"] = when
    return ticket


def kinds_of(data: Any) -> list[tuple[str, str, str]]:
    return [(e.kind, e.source, e.target) for e in data.edges]


class TestAbnahme:
    def test_bearbeiter_gibt_an_den_ersteller_zurueck(self) -> None:
        data = extract_flow([done(issue("X-1", ANNA, BERT), ts(10))], {"X-1": []})
        assert kinds_of(data) == [(EDGE_ORDER, ANNA, BERT), (EDGE_ACCEPTANCE, BERT, ANNA)]
        assert data.edges[-1].when == dt.datetime(2026, 8, 10, 9, tzinfo=TZ)

    def test_offenes_ticket_hat_keine_abnahme(self) -> None:
        ticket = issue("X-1", ANNA, BERT)
        ticket["fields"]["status"] = {"name": "In Arbeit", "statusCategory": {"key": "indeterminate"}}
        ticket["fields"]["statuscategorychangedate"] = ts(10)
        data = extract_flow([ticket], {"X-1": []})
        assert kinds_of(data) == [(EDGE_ORDER, ANNA, BERT)]

    def test_zaehlt_wer_es_beim_abschluss_hatte(self) -> None:
        # Carl hat abgeschlossen, Dora bekam es erst danach - die Abnahme kommt von Carl.
        log = [handover(ts(5), BERT, CARL), handover(ts(12), CARL, DORA)]
        data = extract_flow([done(issue("X-1", ANNA, DORA), ts(10))], {"X-1": log})
        assert kinds_of(data) == [
            (EDGE_ORDER, ANNA, BERT),
            (EDGE_HANDOVER, BERT, CARL),
            (EDGE_ACCEPTANCE, CARL, ANNA),
            (EDGE_HANDOVER, CARL, DORA),
        ]

    def test_ohne_bearbeiter_abgeschlossen_zaehlt_der_letzte(self) -> None:
        log = [handover(ts(8), BERT, None)]
        data = extract_flow([done(issue("X-1", ANNA, None), ts(10))], {"X-1": log})
        assert (EDGE_ACCEPTANCE, BERT, ANNA) in kinds_of(data)

    def test_selbst_abgeschlossen_ist_keine_abnahme(self) -> None:
        log = [handover(ts(5), BERT, ANNA)]
        data = extract_flow([done(issue("X-1", ANNA, ANNA), ts(10))], {"X-1": log})
        assert EDGE_ACCEPTANCE not in [e.kind for e in data.edges]

    def test_ohne_zeitpunkt_wird_nicht_geraten(self) -> None:
        data = extract_flow([done(issue("X-1", ANNA, BERT), None)], {"X-1": []})
        assert kinds_of(data) == [(EDGE_ORDER, ANNA, BERT)]

    def test_im_stern_eingehend_und_abschaltbar(self) -> None:
        data = extract_flow([done(issue("X-1", ANNA, BERT), ts(10))], {"X-1": []})
        star = build_star(data, [ANNA], (EDGE_ACCEPTANCE,), None)
        assert [(s.person.account_id if s.person else "", s.outgoing, s.incoming) for s in star.spokes] == [
            (BERT, (), ("X-1",))
        ]
        assert build_star(data, [ANNA], (EDGE_ORDER, EDGE_HANDOVER), None).spokes[0].incoming == ()

    def test_suche_liefert_den_zeitpunkt(self) -> None:
        assert "statuscategorychangedate" in FLOW_FIELDS.split(",")

    def test_ist_dritte_pfeilart(self) -> None:
        assert EDGE_KINDS == (EDGE_ORDER, EDGE_HANDOVER, EDGE_ACCEPTANCE)


class TestStern:
    def test_wege_je_person_und_richtung(self) -> None:
        star = build_star(_netz(), [ANNA], EDGE_KINDS, None)
        wege = {s.person.name: (s.outgoing, s.incoming) for s in star.spokes if s.person}
        assert wege == {
            "Bert Beispiel": (("X-1", "X-2"), ()),
            "Carl Mustermann": (("X-3",), ()),
            "Dora Probe": ((), ("X-4", "X-6")),
        }
        assert star.center.name == "Anna Muster"
        assert star.others is None

    def test_speichen_stehen_alphabetisch_nicht_nach_menge(self) -> None:
        star = build_star(_netz(), [ANNA], EDGE_KINDS, None)
        assert [s.person.name for s in star.spokes if s.person] == ["Bert Beispiel", "Carl Mustermann", "Dora Probe"]

    def test_kantenart_abschaltbar(self) -> None:
        nur_auftrag = build_star(_netz(), [ANNA], {EDGE_ORDER}, None)
        dora = next(s for s in nur_auftrag.spokes if s.person and s.person.account_id == DORA)
        assert dora.incoming == ("X-4",)
        nur_uebergabe = build_star(_netz(), [ANNA], {EDGE_HANDOVER}, None)
        assert [(s.person.account_id, s.incoming) for s in nur_uebergabe.spokes if s.person] == [(DORA, ("X-6",))]

    def test_zeitraum_schneidet_nach_kantenzeit(self) -> None:
        star = build_star(_netz(), [ANNA], EDGE_KINDS, dt.date(2026, 8, 4))
        assert [(s.person.account_id, s.total) for s in star.spokes if s.person] == [(DORA, 2)]

    def test_rest_unter_sonstige(self) -> None:
        star = build_star(_netz(), [ANNA], EDGE_KINDS, None, limit=2)
        # Bert und Dora haben je zwei Wege, Carl einen - Carl wandert zu Sonstige.
        assert [s.person.account_id for s in star.spokes if s.person] == [BERT, DORA]
        assert star.others is not None
        assert (star.others.members, star.others.outgoing) == (1, ("X-3",))

    def test_ohne_verbindung_ist_der_stern_leer(self) -> None:
        assert build_star(_netz(), [ANNA], EDGE_KINDS, dt.date(2026, 12, 1)).is_empty

    def test_unbekannte_mitte_behaelt_ihre_kennung(self) -> None:
        assert build_star(_netz(), ["id-fremd"], EDGE_KINDS, None).center.name == "id-fremd"

    def test_mehrere_konten_sind_eine_mitte(self) -> None:
        # Anna hat ein zweites Konto, an das Dora uebergibt - Wege zwischen
        # Annas Konten zaehlen nicht, Doras Uebergabe zaehlt bei Anna.
        zweit = "id-anna-2"
        issues = [issue("X-1", ANNA, BERT), issue("X-2", DORA, DORA)]
        log = [
            handover(ts(5), DORA, None),
            {"created": ts(6), "items": [{"field": "assignee", "from": None, "to": zweit}]},
        ]
        data = extract_flow(issues, {"X-1": [], "X-2": log})
        star = build_star(data, [ANNA, zweit], EDGE_KINDS, None)
        assert [(s.person.account_id, s.outgoing, s.incoming) for s in star.spokes if s.person] == [
            (BERT, ("X-1",), ()),
            (DORA, (), ("X-2",)),
        ]
        assert star.center.name == "Anna Muster"

    def test_name_der_mitte_aus_der_merkliste(self) -> None:
        star = build_star(_netz(), [ANNA], EDGE_KINDS, None, center_name="Anni")
        assert star.center.name == "Anni"


class TestKontenZusammenfassen:
    """Carl ist hier das Zweitkonto von Bert, wie in der Merkliste von Mein Team."""

    GRUPPEN = [(BERT, CARL)]

    def _data(self) -> Any:
        issues = [issue("X-1", ANNA, BERT), issue("X-2", ANNA, CARL), issue("X-3", DORA, ANNA)]
        return extract_flow(issues, {"X-1": [], "X-2": [], "X-3": []})

    def test_zwei_konten_eine_speiche(self) -> None:
        data = merge_accounts(self._data(), self.GRUPPEN)
        star = build_star(data, [ANNA], EDGE_KINDS, None)
        assert [(s.person.account_id if s.person else "", s.outgoing) for s in star.spokes] == [
            (BERT, ("X-1", "X-2")),
            (DORA, ()),
        ]

    def test_weg_zwischen_den_konten_faellt_weg(self) -> None:
        log = [handover(ts(5), BERT, CARL)]
        data = merge_accounts(extract_flow([issue("X-1", ANNA, CARL)], {"X-1": log}), self.GRUPPEN)
        assert [(e.kind, e.source, e.target) for e in data.edges] == [(EDGE_ORDER, ANNA, BERT)]

    def test_name_und_bild_der_ersten_kennung(self) -> None:
        issues = [issue("X-1", ANNA, BERT), issue("X-2", ANNA, CARL)]
        issues[1]["fields"]["assignee"]["avatarUrls"] = {"48x48": "https://bilder.example/carl"}
        data = merge_accounts(extract_flow(issues, {"X-1": [], "X-2": []}), self.GRUPPEN)
        assert data.people[BERT] == "Bert Beispiel"
        assert CARL not in data.people
        # Bert selbst hat kein Bild, also gilt das des Zweitkontos.
        assert data.avatars == {BERT: "https://bilder.example/carl"}

    def test_kontakte_zaehlen_beide_konten(self) -> None:
        data = merge_accounts(self._data(), self.GRUPPEN)
        assert [
            (c.person.account_id if c.person else "", c.total) for c in top_contacts(data, [ANNA], EDGE_KINDS, None)
        ] == [
            (BERT, 2),
            (DORA, 1),
        ]

    def test_ohne_gruppen_unveraendert(self) -> None:
        data = self._data()
        assert merge_accounts(data, []) is data
        assert merge_accounts(data, [(BERT,)]) is data

    def test_mitte_mit_zweitkonto(self) -> None:
        load = ticket_flow.FlowLoad((CARL, ANNA), None, self._data(), cached=0, fetched=0)
        merged = merge_load(load, [(ANNA, CARL)])
        assert merged.center == (ANNA,)
        assert load.center == (CARL, ANNA)


class TestZeitraum:
    @pytest.mark.parametrize(
        ("kind", "erwartet"),
        [
            (FLOW_YTD, dt.date(2026, 1, 1)),
            (FLOW_1M, dt.date(2026, 9, 27)),
            (FLOW_12M, dt.date(2025, 10, 27)),
            (FLOW_ALL, None),
        ],
    )
    def test_erster_tag(self, kind: str, erwartet: dt.date | None) -> None:
        assert flow_since(kind, dt.date(2026, 10, 26)) == erwartet

    def test_unbekanntes_kuerzel(self) -> None:
        with pytest.raises(ValueError):
            flow_since("6M", dt.date(2026, 10, 26))


class TestAbfrage:
    def test_zwei_ausdruecke_mit_untergrenze(self) -> None:
        tail = ' AND updated >= "2025-10-27" ORDER BY updated DESC'
        assert flow_jqls([ACCOUNT], dt.date(2025, 10, 27)) == [
            f'reporter IN ("{ACCOUNT}"){tail}',
            f'assignee WAS "{ACCOUNT}"{tail}',
        ]

    def test_ohne_untergrenze(self) -> None:
        assert all("updated >=" not in jql for jql in flow_jqls([ACCOUNT], None))

    def test_mehrere_kennungen(self) -> None:
        reporter, assignee = flow_jqls(["id-a", "id-b"], None)
        assert reporter.startswith('reporter IN ("id-a", "id-b")')
        # Klammern, damit eine spaetere Untergrenze fuer beide Kennungen gilt.
        assert assignee.startswith('(assignee WAS "id-a" OR assignee WAS "id-b")')

    def test_ohne_kennung(self) -> None:
        with pytest.raises(AccountIdError):
            flow_jqls([], None)

    def test_kennung_wird_geprueft(self) -> None:
        with pytest.raises(AccountIdError):
            flow_jqls([ACCOUNT, 'x" OR project = Y'], None)


class FakeSource:
    """Steht fuer den JiraClient: liefert feste Tickets und merkt sich die Abrufe."""

    def __init__(
        self,
        issues: list[dict[str, Any]],
        logs: dict[str, list[dict[str, Any]]],
        own: str = ANNA,
        bulk: bool = False,
    ) -> None:
        self.issues = issues
        self.logs = logs
        self.own = own
        self.bulk = bulk
        self.jqls: list[str] = []
        self.parallel: list[bool] = []
        self.requested: list[list[str]] = []
        self.concurrency: list[int] = []
        self.bulk_ids: list[list[str]] = []

    async def fetch_issues(
        self, build_jqls: Callable[[str], Sequence[str]], fields: str, parallel: bool = False
    ) -> tuple[str, list[dict[str, Any]]]:
        self.jqls.extend(build_jqls(self.own))
        self.parallel.append(parallel)
        return self.own, self.issues

    async def fetch_changelogs(self, keys: Sequence[str], concurrency: int = 4) -> dict[str, list[dict[str, Any]]]:
        self.requested.append(list(keys))
        self.concurrency.append(concurrency)
        # Wie der echte Client: was scheitert, fehlt im Ergebnis.
        return {key: self.logs[key] for key in keys if key in self.logs}

    async def fetch_changelogs_bulk(
        self, issue_ids: Sequence[str], field_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]] | None:
        self.bulk_ids.append(list(issue_ids))
        if not self.bulk:
            return None
        # Wie der echte Client: jede Id steht drin, ohne Wechsel mit leerer Liste.
        keys = {str(i["id"]): i["key"] for i in self.issues if "id" in i}
        return {i: self.logs.get(keys[i], []) for i in issue_ids}


class MemoryStore:
    """Steht fuer den ChangelogCache."""

    def __init__(self) -> None:
        self.items: dict[str, tuple[str, list[dict[str, Any]]]] = {}

    def load(self, key: str, stamp: str) -> list[dict[str, Any]] | None:
        stored = self.items.get(key)
        return stored[1] if stored is not None and stored[0] == stamp else None

    def save(self, key: str, stamp: str, histories: list[dict[str, Any]]) -> None:
        self.items[key] = (stamp, histories)


def stamped(key: str, reporter: str, assignee: str, updated: str, with_id: bool = False) -> dict[str, Any]:
    """Suchtreffer mit ``updated`` als Stempel, auf Wunsch mit numerischer Id."""
    raw = issue(key, reporter, assignee)
    raw["fields"]["updated"] = updated
    if with_id:
        raw["id"] = f"100{key.split('-')[1]}"
    return raw


class TestLader:
    def test_ohne_kennung_gilt_die_eigene_aus_der_sitzung(self) -> None:
        source = FakeSource([stamped("X-1", ANNA, BERT, ts(9))], {"X-1": []})
        result = asyncio.run(load_flow(source, MemoryStore(), [], None))
        assert result.center == (ANNA,)
        assert f'assignee WAS "{ANNA}"' in source.jqls[1]

    def test_ablage_mit_gleichem_stempel_spart_den_abruf(self) -> None:
        store = MemoryStore()
        store.save("X-1", ts(9), [])
        store.save("X-2", ts(1), [])
        source = FakeSource(
            [stamped("X-1", ANNA, BERT, ts(9)), stamped("X-2", ANNA, CARL, ts(9))],
            {"X-1": [], "X-2": [handover(ts(5), CARL, DORA)]},
        )
        result = asyncio.run(load_flow(source, store, [ANNA], None))
        # X-2 wurde seit dem Ablegen bewegt - neu geholt und neu abgelegt.
        assert source.requested == [["X-2"]]
        assert (result.cached, result.fetched) == (1, 1)
        assert store.items["X-2"][0] == ts(9)

    def test_gescheiterter_abruf_wird_nicht_abgelegt(self) -> None:
        store = MemoryStore()
        source = FakeSource([stamped("X-1", ANNA, BERT, ts(9))], {})
        result = asyncio.run(load_flow(source, store, [ANNA], None))
        assert result.data.missing == ("X-1",)
        assert store.items == {}

    def test_ohne_stempel_wird_geholt_aber_nicht_abgelegt(self) -> None:
        store = MemoryStore()
        source = FakeSource([issue("X-1", ANNA, BERT)], {"X-1": []})
        result = asyncio.run(load_flow(source, store, [ANNA], None))
        assert result.fetched == 1
        assert store.items == {}

    def test_abruf_in_paketen_mit_zwischenstand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ticket_flow.loader, "CHANGELOG_CHUNK", 2)
        keys = [f"X-{n}" for n in range(1, 6)]
        source = FakeSource([stamped(k, ANNA, BERT, ts(9)) for k in keys], {k: [] for k in keys})
        meldungen: list[str] = []
        asyncio.run(load_flow(source, MemoryStore(), [ANNA], None, meldungen.append))
        assert [len(chunk) for chunk in source.requested] == [2, 2, 1]
        assert [m.split(":")[1].split(" geholt")[0].strip() for m in meldungen] == ["0 von 5", "2 von 5", "4 von 5"]

    def test_beide_suchen_laufen_gleichzeitig(self) -> None:
        source = FakeSource([stamped("X-1", ANNA, BERT, ts(9))], {"X-1": []})
        asyncio.run(load_flow(source, MemoryStore(), [ANNA], None))
        assert len(source.jqls) == 2
        assert source.parallel == [True]


class TestSammelabruf:
    def test_ersetzt_die_einzelabrufe(self) -> None:
        store = MemoryStore()
        issues = [stamped("X-1", ANNA, BERT, ts(9), True), stamped("X-2", ANNA, CARL, ts(9), True)]
        source = FakeSource(issues, {"X-2": [handover(ts(5), CARL, DORA)]}, bulk=True)
        result = asyncio.run(load_flow(source, store, [ANNA], None))
        assert source.bulk_ids == [["1001", "1002"]]
        assert source.requested == []
        # Ein Ticket ohne Bearbeiterwechsel hat ein leeres Protokoll, es fehlt nicht.
        assert result.data.missing == ()
        assert result.fetched == 2
        assert store.items["X-1"] == (ts(9), [])

    def test_ohne_endpunkt_einzeln_mit_acht_gleichzeitig(self) -> None:
        issues = [stamped("X-1", ANNA, BERT, ts(9), True)]
        source = FakeSource(issues, {"X-1": []}, bulk=False)
        result = asyncio.run(load_flow(source, MemoryStore(), [ANNA], None))
        assert source.bulk_ids == [["1001"]]
        assert source.requested == [["X-1"]]
        assert source.concurrency == [ticket_flow.CHANGELOG_CONCURRENCY] == [8]
        assert result.fetched == 1

    def test_ablage_geht_vor(self) -> None:
        store = MemoryStore()
        store.save("X-1", ts(9), [])
        issues = [stamped("X-1", ANNA, BERT, ts(9), True), stamped("X-2", ANNA, CARL, ts(9), True)]
        source = FakeSource(issues, {}, bulk=True)
        asyncio.run(load_flow(source, store, [ANNA], None))
        assert source.bulk_ids == [["1002"]]


class TestProfilbilder:
    def test_groesste_adresse_aus_der_suche(self) -> None:
        raw = issue("X-1", ANNA, BERT)
        raw["fields"]["reporter"]["avatarUrls"] = {"16x16": "https://a/16", "48x48": "https://a/48"}
        data = extract_flow([raw], {"X-1": []})
        assert data.avatars == {ANNA: "https://a/48"}

    def test_auch_ohne_protokoll(self) -> None:
        raw = issue("X-1", ANNA, BERT)
        raw["fields"]["assignee"]["avatarUrls"] = {"24x24": "https://b/24"}
        assert extract_flow([raw], {}).avatars == {BERT: "https://b/24"}


class TestKontakte:
    def test_meiste_gemeinsame_tickets_zuerst(self) -> None:
        kontakte = top_contacts(_netz(), [ANNA], EDGE_KINDS, None)
        # Bert und Dora je zwei Tickets, Carl eins - bei Gleichstand nach Namen.
        assert [k.person.account_id for k in kontakte if k.person] == [BERT, DORA, CARL]

    def test_hin_und_zurueck_zaehlt_einmal(self) -> None:
        issues = [issue("X-1", ANNA, BERT), issue("X-2", CARL, ANNA), issue("X-3", CARL, ANNA)]
        histories: dict[str, list[dict[str, Any]]] = {
            "X-1": [handover(ts(5), BERT, ANNA)],
            "X-2": [],
            "X-3": [],
        }
        kontakte = top_contacts(extract_flow(issues, histories), [ANNA], EDGE_KINDS, None)
        # Mit Bert ging X-1 hin und zurueck: ein Ticket. Mit Carl zwei.
        assert [(k.person.account_id, len(set(k.outgoing) | set(k.incoming))) for k in kontakte if k.person] == [
            (CARL, 2),
            (BERT, 1),
        ]

    def test_grenze(self) -> None:
        assert len(top_contacts(_netz(), [ANNA], EDGE_KINDS, None, limit=1)) == 1


class TestEpochZeitstempel:
    """Der Sammelabruf liefert ``created`` als Epoch-Millisekunden (gemessen am 26.10.2026)."""

    def test_wird_zu_iso_mit_utc(self) -> None:
        from jira_timesheet_qt.services.jira_client import _with_iso_created

        eintrag = _with_iso_created({"created": 1_788_861_600_000, "items": []})
        assert eintrag["created"] == "2026-09-08T10:00:00.000+00:00"

    def test_iso_bleibt_wie_es_ist(self) -> None:
        from jira_timesheet_qt.services.jira_client import _with_iso_created

        roh = {"created": ts(5)}
        assert _with_iso_created(roh) is roh

    def test_ergibt_eine_kante_zur_richtigen_zeit(self) -> None:
        from jira_timesheet_qt.services.jira_client import _with_iso_created

        roh = handover(ts(5), BERT, CARL)
        roh["created"] = 1_788_861_600_000
        data = extract_flow([issue("X-1", ANNA, CARL)], {"X-1": [_with_iso_created(roh)]})
        uebergabe = data.edges[-1]
        assert (uebergabe.kind, uebergabe.source, uebergabe.target) == (EDGE_HANDOVER, BERT, CARL)
        assert uebergabe.when == dt.datetime(2026, 9, 8, 10, tzinfo=dt.UTC)
