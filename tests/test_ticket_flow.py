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
    EDGE_HANDOVER,
    EDGE_KINDS,
    EDGE_ORDER,
    FLOW_1M,
    FLOW_12M,
    FLOW_ALL,
    FLOW_YTD,
    build_star,
    extract_flow,
    flow_jql,
    flow_since,
    load_flow,
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
    def test_mit_untergrenze(self) -> None:
        assert flow_jql([ACCOUNT], dt.date(2025, 10, 27)) == (
            f'(reporter IN ("{ACCOUNT}") OR assignee WAS "{ACCOUNT}") AND updated >= "2025-10-27" ORDER BY updated DESC'
        )

    def test_ohne_untergrenze(self) -> None:
        assert "updated >=" not in flow_jql([ACCOUNT], None)

    def test_mehrere_kennungen(self) -> None:
        jql = flow_jql(["id-a", "id-b"], None)
        assert jql.startswith('(reporter IN ("id-a", "id-b") OR assignee WAS "id-a" OR assignee WAS "id-b")')

    def test_ohne_kennung(self) -> None:
        with pytest.raises(AccountIdError):
            flow_jql([], None)

    def test_kennung_wird_geprueft(self) -> None:
        with pytest.raises(AccountIdError):
            flow_jql([ACCOUNT, 'x" OR project = Y'], None)


class FakeSource:
    """Steht fuer den JiraClient: liefert feste Tickets und merkt sich die Abrufe."""

    def __init__(self, issues: list[dict[str, Any]], logs: dict[str, list[dict[str, Any]]], own: str = ANNA) -> None:
        self.issues = issues
        self.logs = logs
        self.own = own
        self.jqls: list[str] = []
        self.requested: list[list[str]] = []

    async def fetch_issues(
        self, build_jqls: Callable[[str], Sequence[str]], fields: str
    ) -> tuple[str, list[dict[str, Any]]]:
        self.jqls.extend(build_jqls(self.own))
        return self.own, self.issues

    async def fetch_changelogs(self, keys: Sequence[str], concurrency: int = 4) -> dict[str, list[dict[str, Any]]]:
        self.requested.append(list(keys))
        # Wie der echte Client: was scheitert, fehlt im Ergebnis.
        return {key: self.logs[key] for key in keys if key in self.logs}


class MemoryStore:
    """Steht fuer den ChangelogCache."""

    def __init__(self) -> None:
        self.items: dict[str, tuple[str, list[dict[str, Any]]]] = {}

    def load(self, key: str, stamp: str) -> list[dict[str, Any]] | None:
        stored = self.items.get(key)
        return stored[1] if stored is not None and stored[0] == stamp else None

    def save(self, key: str, stamp: str, histories: list[dict[str, Any]]) -> None:
        self.items[key] = (stamp, histories)


def stamped(key: str, reporter: str, assignee: str, updated: str) -> dict[str, Any]:
    """Suchtreffer mit ``updated`` als Stempel."""
    raw = issue(key, reporter, assignee)
    raw["fields"]["updated"] = updated
    return raw


class TestLader:
    def test_ohne_kennung_gilt_die_eigene_aus_der_sitzung(self) -> None:
        source = FakeSource([stamped("X-1", ANNA, BERT, ts(9))], {"X-1": []})
        result = asyncio.run(load_flow(source, MemoryStore(), [], None))
        assert result.center == (ANNA,)
        assert f'assignee WAS "{ANNA}"' in source.jqls[0]

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
