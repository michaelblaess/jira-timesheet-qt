"""Tests fuer den Kern des Performance-Boosters.

Alle Zeitpunkte sind fest verdrahtet - kein Test haengt am heutigen Datum.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from jira_timesheet_qt.services.performance import (
    PERIOD_1M,
    PERIOD_3M,
    PERIOD_YTD,
    RULE_LONG,
    RULE_SMALL,
    RULE_TREND,
    RULE_WIP,
    ChangelogCache,
    HintConfig,
    Period,
    active_workdays,
    build_report,
    closed_jql,
    created_jql,
    cumulative_done,
    cycle_buckets,
    done_since_jql,
    done_tickets,
    is_long,
    period_for,
    size_buckets,
    small_tickets,
    worklog_jql,
)
from jira_timesheet_qt.services.ticket_board import AccountIdError, BoardConfig

TZ = dt.timezone(dt.timedelta(hours=2))
ACCOUNT = "712020:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

CONFIG = BoardConfig(
    active_status=("In Arbeit",),
    backlog_status=("Offen",),
    acceptance_status=("Abnahme",),
    done_status=("Fertig",),
)
CATEGORIES = {"offen": "new", "in arbeit": "indeterminate", "abnahme": "indeterminate", "fertig": "done"}


def ts(day: int, hour: int = 8, month: int = 8) -> str:
    """Zeitstempel im Jira-Format, August 2026."""
    return dt.datetime(2026, month, day, hour, tzinfo=TZ).isoformat()


def change(when: str, old: str, new: str) -> dict[str, Any]:
    """Ein Statuswechsel im Aenderungsprotokoll."""
    return {"created": when, "items": [{"field": "status", "fromString": old, "toString": new}]}


def issue(
    key: str,
    *,
    status: str = "Fertig",
    category: str = "done",
    created: str = "",
    done: str = "",
    hours: float = 0.0,
    points: float | None = None,
    issuetype: str = "Aufgabe",
    level: int | None = None,
    updated: str = "",
) -> dict[str, Any]:
    """Eine Rohantwort der Suche."""
    return {
        "key": key,
        "fields": {
            "summary": f"Titel {key}",
            "status": {"name": status, "statusCategory": {"key": category}},
            "issuetype": {"name": issuetype, **({"hierarchyLevel": level} if level is not None else {})},
            "updated": updated or done or ts(20),
            "created": created or ts(3),
            "statuscategorychangedate": done,
            "timespent": int(hours * 3600),
            "customfield_99001": points,
        },
    }


# Mo 03.08. angelegt und begonnen, Mi zur Abnahme, Fr zurueck in Arbeit,
# Mo 10.08. fertig. Aktiv: Mo-Mi (2 AT) + Fr (1 AT) = 3 AT. Die zwei Tage in
# der Abnahme zaehlen nicht.
REWORK = [
    change(ts(3), "Offen", "In Arbeit"),
    change(ts(5), "In Arbeit", "Abnahme"),
    change(ts(7), "Abnahme", "In Arbeit"),
    change(ts(10), "In Arbeit", "Fertig"),
]


class TestPeriod:
    def test_drei_monate_und_gleich_lange_vorperiode(self) -> None:
        current, prior = period_for(PERIOD_3M, dt.date(2026, 9, 23))
        assert current == Period(dt.date(2026, 6, 24), dt.date(2026, 9, 23))
        assert prior.end == dt.date(2026, 6, 23)
        assert prior.days == current.days == 92

    def test_ytd_beginnt_am_ersten_januar(self) -> None:
        current, prior = period_for(PERIOD_YTD, dt.date(2026, 9, 23))
        assert current.start == dt.date(2026, 1, 1)
        assert prior.end == dt.date(2025, 12, 31)
        assert prior.days == current.days

    def test_monatsende_wird_gekappt(self) -> None:
        current, _ = period_for(PERIOD_1M, dt.date(2026, 3, 31))
        assert current.start == dt.date(2026, 3, 1)

    def test_unbekannter_zeitraum(self) -> None:
        with pytest.raises(ValueError):
            period_for("2J", dt.date(2026, 9, 23))


class TestQueries:
    def test_ohne_kennung_der_angemeldete_benutzer(self) -> None:
        assert "assignee = currentUser()" in done_since_jql((), dt.date(2026, 3, 1))
        assert "worklogAuthor = currentUser()" in worklog_jql((), dt.date(2026, 3, 1), dt.date(2026, 9, 1))

    def test_fremde_kennungen(self) -> None:
        jql = worklog_jql((ACCOUNT,), dt.date(2026, 3, 1), dt.date(2026, 9, 1))
        assert f'worklogAuthor IN ("{ACCOUNT}")' in jql
        assert '"2026-03-01"' in jql and '"2026-09-01"' in jql

    def test_unbrauchbare_kennung_bricht_ab(self) -> None:
        with pytest.raises(AccountIdError):
            worklog_jql(('x" OR 1=1',), dt.date(2026, 3, 1), dt.date(2026, 9, 1))


class TestActiveWorkdays:
    def test_wartezeit_in_der_abnahme_zaehlt_nicht(self) -> None:
        created = dt.datetime(2026, 8, 3, 8, tzinfo=TZ)
        done = dt.datetime(2026, 8, 10, 8, tzinfo=TZ)
        assert active_workdays(REWORK, created, done, CONFIG, CATEGORIES) == pytest.approx(3.0)

    def test_nie_aktiv_ist_keine_null(self) -> None:
        log = [change(ts(4), "Offen", "Fertig")]
        created = dt.datetime(2026, 8, 3, 8, tzinfo=TZ)
        done = dt.datetime(2026, 8, 4, 8, tzinfo=TZ)
        assert active_workdays(log, created, done, CONFIG, CATEGORIES) is None

    def test_unkonfigurierter_status_folgt_der_kategorie(self) -> None:
        log = [change(ts(3), "Offen", "Review"), change(ts(4), "Review", "Fertig")]
        created = dt.datetime(2026, 8, 3, 8, tzinfo=TZ)
        done = dt.datetime(2026, 8, 4, 8, tzinfo=TZ)
        categories = {**CATEGORIES, "review": "indeterminate"}
        assert active_workdays(log, created, done, CONFIG, categories) == pytest.approx(1.0)
        # Gegenprobe: ohne Kategorie ist der Status keiner Rolle zuzuordnen.
        assert active_workdays(log, created, done, CONFIG, CATEGORIES) is None


class TestDoneTickets:
    def test_nur_erledigte_ohne_dubletten(self) -> None:
        issues = [
            issue("A-1", done=ts(10), hours=2),
            issue("A-1", done=ts(10), hours=2),
            issue("A-2", status="In Arbeit", category="indeterminate"),
        ]
        tickets = done_tickets(issues, {"A-1": REWORK}, CONFIG, CATEGORIES)
        assert [t.key for t in tickets] == ["A-1"]
        assert tickets[0].active_days == pytest.approx(3.0)
        assert tickets[0].hours == pytest.approx(2.0)

    def test_fehlendes_protokoll_wird_nicht_geraten(self) -> None:
        tickets = done_tickets([issue("A-1", done=ts(10))], {}, CONFIG, CATEGORIES)
        assert tickets[0].active_days is None


def _report(issues: list[dict[str, Any]], histories: dict[str, Any], **kwargs: Any) -> Any:
    period = Period(dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    prior = Period(dt.date(2026, 7, 1), dt.date(2026, 7, 31))
    return build_report(
        member="Ich",
        period=period,
        prior_period=prior,
        issues=issues,
        histories=histories,
        worklogs=kwargs.pop("worklogs", []),
        config=CONFIG,
        categories=CATEGORIES,
        hint_config=kwargs.pop("hint_config", HintConfig()),
        points_field=kwargs.pop("points_field", ""),
        created=kwargs.pop("created", ()),
        closed=kwargs.pop("closed", (None, None)),
    )


def _long_log(start_day: int, end_day: int, month: int = 8) -> list[dict[str, Any]]:
    return [
        change(ts(start_day, month=month), "Offen", "In Arbeit"),
        change(ts(end_day, month=month), "In Arbeit", "Fertig"),
    ]


class TestReport:
    def test_zeitraum_und_vorperiode_getrennt(self) -> None:
        issues = [
            issue("A-1", done=ts(10), hours=3),
            issue("A-2", done=ts(15, month=7), created=ts(1, month=7), hours=3),
        ]
        worklogs = [(dt.date(2026, 8, 4), 7200.0), (dt.date(2026, 7, 4), 3600.0)]
        report = _report(issues, {"A-1": REWORK}, worklogs=worklogs)
        assert [t.key for t in report.tickets] == ["A-1"]
        assert [t.key for t in report.prior_tickets] == ["A-2"]
        assert report.current.booked_hours == pytest.approx(2.0)
        assert report.prior.booked_hours == pytest.approx(1.0)

    def test_anteil_klein_ohne_ungebuchte(self) -> None:
        issues = [
            issue("A-1", done=ts(10), hours=0.5),
            issue("A-2", done=ts(11), hours=4),
            issue("A-3", done=ts(12), hours=0),
        ]
        report = _report(issues, {})
        assert report.current.small_share == pytest.approx(50.0)
        assert report.current.done == 3

    def test_hinweis_lange_tickets(self) -> None:
        # 3. bis 31.08. aktiv sind 20 Arbeitstage, die Schwelle liegt bei 15.
        issues = [issue("A-1", done=ts(31), hours=40), issue("A-2", done=ts(10), hours=40)]
        histories = {"A-1": _long_log(3, 31), "A-2": REWORK}
        report = _report(issues, histories)
        long = [h for h in report.hints if h.rule == RULE_LONG]
        assert len(long) == 1 and long[0].keys == ("A-1",)
        # Gegenprobe: hoehere Schwelle, kein Hinweis.
        report = _report(issues, histories, hint_config=HintConfig(long_days=25))
        assert not [h for h in report.hints if h.rule == RULE_LONG]

    def test_hinweis_kleine_tickets(self) -> None:
        issues = [issue(f"A-{n}", done=ts(10 + n), hours=0.25) for n in range(3)]
        issues.append(issue("A-9", done=ts(20), hours=8))
        report = _report(issues, {})
        small = [h for h in report.hints if h.rule == RULE_SMALL]
        assert len(small) == 1 and set(small[0].keys) == {"A-0", "A-1", "A-2"}
        assert "75 %" in small[0].text
        report = _report(issues, {}, hint_config=HintConfig(small_share=80))
        assert not [h for h in report.hints if h.rule == RULE_SMALL]

    def test_hinweis_parallel_in_arbeit(self) -> None:
        issues = [issue(f"B-{n}", status="In Arbeit", category="indeterminate") for n in range(3)]
        issues.append(issue("B-9", status="Abnahme", category="indeterminate"))
        report = _report(issues, {})
        wip = [h for h in report.hints if h.rule == RULE_WIP]
        assert len(wip) == 1 and set(wip[0].keys) == {"B-0", "B-1", "B-2"}
        report = _report(issues, {}, hint_config=HintConfig(wip_limit=4))
        assert not [h for h in report.hints if h.rule == RULE_WIP]

    def test_hinweis_trend(self) -> None:
        issues = [
            issue("A-1", done=ts(10), hours=4),
            issue("A-2", done=ts(9, month=7), created=ts(1, month=7), hours=4),
        ]
        histories = {"A-1": REWORK, "A-2": _long_log(6, 8, month=7)}
        report = _report(issues, histories)
        assert report.prior.median_active_days == pytest.approx(2.0)
        trend = [h for h in report.hints if h.rule == RULE_TREND]
        assert len(trend) == 1 and "+50 %" in trend[0].text
        report = _report(issues, histories, hint_config=HintConfig(trend_percent=60))
        assert not [h for h in report.hints if h.rule == RULE_TREND]


def test_null_schaltet_jede_regel_ab() -> None:
    issues = [issue(f"A-{n}", done=ts(10 + n), hours=0.25) for n in range(3)]
    issues += [issue(f"B-{n}", status="In Arbeit", category="indeterminate") for n in range(5)]
    issues.append(issue("C-1", done=ts(31), hours=40))
    off = HintConfig(long_days=0, small_share=0, wip_limit=0, trend_percent=0)
    assert _report(issues, {"C-1": _long_log(3, 31)}).hints
    assert _report(issues, {"C-1": _long_log(3, 31)}, hint_config=off).hints == []


def test_ungebuchte_tickets_sind_nicht_klein() -> None:
    issues = [
        issue("A-1", done=ts(10), hours=0),
        issue("A-2", done=ts(11), hours=0.5),
        issue("A-3", done=ts(12), hours=2),
    ]
    tickets = done_tickets(issues, {}, CONFIG, CATEGORIES)
    assert [t.key for t in small_tickets(tickets, HintConfig())] == ["A-2"]
    buckets = size_buckets(tickets, 1.0)
    assert buckets[0] == ("0 h", 1, False)
    assert buckets[1] == ("< 1 h", 1, True)
    assert sum(count for _, count, _ in buckets) == 3


def test_kurs_kumuliert_je_tag() -> None:
    issues = [issue("A-1", done=ts(2)), issue("A-2", done=ts(2)), issue("A-3", done=ts(4))]
    tickets = done_tickets(issues, {}, CONFIG, CATEGORIES)
    series = cumulative_done(tickets, Period(dt.date(2026, 8, 1), dt.date(2026, 8, 5)))
    assert series == [0, 2, 2, 3, 3]


class TestChangelogCache:
    def test_passender_stand_wird_gelesen(self, tmp_path: Path) -> None:
        cache = ChangelogCache(tmp_path, "https://example.atlassian.net")
        cache.save("A-1", "stamp-1", REWORK)
        assert cache.load("A-1", "stamp-1") == REWORK

    def test_neuer_abschluss_macht_den_stand_ungueltig(self, tmp_path: Path) -> None:
        cache = ChangelogCache(tmp_path, "https://example.atlassian.net")
        cache.save("A-1", "stamp-1", REWORK)
        assert cache.load("A-1", "stamp-2") is None

    def test_host_trennt(self, tmp_path: Path) -> None:
        ChangelogCache(tmp_path, "https://a.example").save("A-1", "s", REWORK)
        assert ChangelogCache(tmp_path, "https://b.example").load("A-1", "s") is None

    def test_kein_pfad_aus_fremden_zeichen(self, tmp_path: Path) -> None:
        cache = ChangelogCache(tmp_path, "h")
        cache.save("../boese", "s", REWORK)
        assert not list(tmp_path.rglob("*.json"))


class TestStoryPoints:
    def test_feld_wird_gelesen_und_null_ist_keine_schaetzung(self) -> None:
        issues = [
            issue("A-1", done=ts(10), hours=8, points=3),
            issue("A-2", done=ts(11), hours=2, points=0),
            issue("A-3", done=ts(12), hours=2),
        ]
        tickets = done_tickets(issues, {"A-1": REWORK}, CONFIG, CATEGORIES, "customfield_99001")
        assert [t.story_points for t in tickets] == [3.0, None, None]
        assert tickets[0].days_per_point == pytest.approx(1.0)
        # Ohne Feld-ID gibt es keine Schaetzung, auch wenn der Wert daneben steht.
        assert done_tickets(issues, {}, CONFIG, CATEGORIES)[0].story_points is None

    def test_kennzahlen_je_punkt_nur_ueber_geschaetzte(self) -> None:
        issues = [issue("A-1", done=ts(10), hours=9, points=3), issue("A-2", done=ts(11), hours=50)]
        report = _report(issues, {"A-1": REWORK}, points_field="customfield_99001")
        assert report.current.estimated == 1
        assert report.current.median_days_per_point == pytest.approx(1.0)
        assert report.current.hours_per_point == pytest.approx(3.0)

    def test_grosses_ticket_darf_laenger_dauern(self) -> None:
        # 20 aktive Tage: ohne Schaetzung lang (> 15), mit 13 SP nicht (1,5 AT je SP < 3).
        issues = [issue("A-1", done=ts(31), hours=80, points=13), issue("A-2", done=ts(31), hours=80)]
        histories = {"A-1": _long_log(3, 31), "A-2": _long_log(3, 31)}
        report = _report(issues, histories, points_field="customfield_99001")
        long = [h for h in report.hints if h.rule == RULE_LONG]
        assert long and long[0].keys == ("A-2",)
        # Gegenprobe: mit strengerer Schwelle je Punkt wird auch das geschaetzte lang.
        strict = HintConfig(days_per_point=1.0)
        assert is_long(report.tickets[0], strict)

    def test_kleines_ticket_mit_langer_laufzeit_je_punkt(self) -> None:
        # 3 aktive Tage bei 0,5 SP sind 6 AT je Punkt - lang, obwohl absolut kurz.
        issues = [issue("A-1", done=ts(10), hours=4, points=0.5)]
        report = _report(issues, {"A-1": REWORK}, points_field="customfield_99001")
        assert [h.keys for h in report.hints if h.rule == RULE_LONG] == [("A-1",)]


class TestZulaufUndProfil:
    def test_erstellt_wird_nach_zeitraum_getrennt(self) -> None:
        created = [dt.date(2026, 8, 3), dt.date(2026, 8, 30), dt.date(2026, 7, 9), dt.date(2026, 6, 1)]
        report = _report([], {}, created=created, closed=(5, 2))
        assert report.current.created == 2 and report.prior.created == 1
        assert report.created == [dt.date(2026, 8, 3), dt.date(2026, 8, 30)]
        assert (report.current.closed, report.prior.closed) == (5, 2)

    def test_erstellt_nach_autor(self) -> None:
        assert created_jql((), dt.date(2026, 6, 24), dt.date(2026, 9, 23)).startswith("reporter = currentUser()")
        jql = created_jql((ACCOUNT, ACCOUNT.replace("a", "b")), dt.date(2026, 6, 24), dt.date(2026, 9, 23))
        assert jql.startswith("reporter IN (")
        assert '"2026-09-23 23:59"' in jql

    def test_geschlossen_je_status_und_person(self) -> None:
        jql = closed_jql(
            (ACCOUNT,), ["Fertig", "Übergabe Betrieb", "fertig"], dt.date(2026, 6, 24), dt.date(2026, 9, 23)
        )
        assert jql.count("status CHANGED TO") == 3
        assert f'BY "{ACCOUNT}"' in jql and '"Übergabe Betrieb"' in jql
        assert closed_jql((), [], dt.date(2026, 6, 24), dt.date(2026, 9, 23)) == ""
        assert "BY currentUser()" in closed_jql((), ["Fertig"], dt.date(2026, 6, 24), dt.date(2026, 9, 23))

    def test_anfuehrungszeichen_im_status_brechen_nichts(self) -> None:
        jql = closed_jql((), ['Sag "ja"'], dt.date(2026, 6, 24), dt.date(2026, 9, 23))
        assert 'TO "Sag \\"ja\\"" BY' in jql


def test_durchlaufzeit_in_klassen() -> None:
    issues = [issue(f"A-{n}", done=ts(31), hours=1) for n in range(4)]
    histories = {
        "A-0": [change(ts(3), "Offen", "Fertig")],
        "A-1": [change(ts(3), "Offen", "In Arbeit"), change(ts(4), "In Arbeit", "Fertig")],
        "A-2": REWORK,
        "A-3": _long_log(3, 31),
    }
    tickets = done_tickets(issues, histories, CONFIG, CATEGORIES)
    buckets = cycle_buckets(tickets, 15.0)
    assert [label for label, _, _ in buckets] == ["nie aktiv", "< 2", "2-5", "5-15", "> 15"]
    assert [count for _, count, _ in buckets] == [1, 1, 1, 0, 1]
    assert [long for _, _, long in buckets] == [False, False, False, False, True]


def test_ticketnummer_sortiert_numerisch() -> None:
    from jira_timesheet_qt.services.ticket_board import key_sort_value

    keys = ["ABC-17741", "ABC-5979", "ABC-2", "ABC-17132", "ohne-nummer"]
    assert sorted(keys, key=key_sort_value) == ["ABC-2", "ABC-5979", "ABC-17132", "ABC-17741", "ohne-nummer"]


class TestContainerUndZeitbezug:
    def test_epic_zaehlt_nicht_als_erledigt(self) -> None:
        issues = [issue("E-1", done=ts(10), issuetype="Epic", level=1), issue("A-1", done=ts(10))]
        assert [t.key for t in done_tickets(issues, {}, CONFIG, CATEGORIES)] == ["A-1"]

    def test_hierarchiestufe_schlaegt_den_namen(self) -> None:
        # Ein lokal "Epic" genannter Typ auf Stufe 0 ist ein Arbeitspaket,
        # ein anders benannter Typ auf Stufe 2 ein Container.
        issues = [
            issue("A-1", done=ts(10), issuetype="Epic", level=0),
            issue("A-2", done=ts(10), issuetype="Vorhaben", level=2),
        ]
        assert [t.key for t in done_tickets(issues, {}, CONFIG, CATEGORIES)] == ["A-1"]

    def test_alte_tickets_in_arbeit_zaehlen_nicht(self) -> None:
        issues = [
            issue("OLD-1", status="In Arbeit", category="indeterminate", updated=ts(1, month=3)),
            issue("NEW-1", status="In Arbeit", category="indeterminate", updated=ts(12)),
            issue("EPIC-1", status="In Arbeit", category="indeterminate", updated=ts(12), issuetype="Initiative"),
        ]
        report = _report(issues, {})
        assert [t.key for t in report.active_open] == ["NEW-1"]
        assert [t.key for t in report.all_tickets] == ["NEW-1"]
        assert report.notes[0].startswith("1 Epics/Initiativen nicht mitgezählt")
