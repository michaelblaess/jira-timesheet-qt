"""Tests fuer den Berichts-Kern.

Kein Netzwerk: die Rohdaten sind Attrappen im Format der Jira-API. Genau so
reichen spaeter auch jira-timesheet und jira-timesheet-qt ihre Antworten
herein.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from jira_timesheet_qt.services.ticket_report import (
    build_html,
    build_report,
    lifecycle,
    viewmodel,
    write_report,
)
from jira_timesheet_qt.services.ticket_report.render import e
from jira_timesheet_qt.services.ticket_report.viewmodel import business_seconds, off_hours

BASE = "https://example.atlassian.net/browse"
TZ = dt.timezone(dt.timedelta(hours=2))


def stamp(tag: int, stunde: int = 9, minute: int = 0, sekunde: int = 0) -> str:
    """Baut einen Jira-Zeitstempel im Juli 2026 (der 1.7. ist ein Mittwoch)."""
    return f"2026-07-{tag:02d}T{stunde:02d}:{minute:02d}:{sekunde:02d}.000+0200"


def issue_stub(**felder: Any) -> dict[str, Any]:
    """Minimales Issue-JSON."""
    fields: dict[str, Any] = {
        "summary": "Testticket",
        "created": stamp(1, 9),
        "updated": stamp(3, 9),
        "issuetype": {"name": "Story"},
        "priority": {"name": "Medium"},
        "status": {"name": "IN ARBEIT"},
        "reporter": {"displayName": "Muster, Erika"},
        "assignee": {"displayName": "Beispiel, Max"},
    }
    fields.update(felder)
    return {"key": "ABC-1", "fields": fields}


def changelog_stub(*eintraege: tuple[str, str, list[tuple[str, str, str]]]) -> list[dict[str, Any]]:
    """Baut Changelog-Eintraege aus (Zeitstempel, Autor, [(Feld, von, nach)])."""
    return [
        {
            "created": when,
            "author": {"displayName": who},
            "items": [
                {"field": feld, "fromString": von or None, "toString": nach or None}
                for feld, von, nach in items
            ],
        }
        for when, who, items in eintraege
    ]


def comment_stub(when: str, who: str, text: str) -> dict[str, Any]:
    """Baut einen Kommentar im ADF-Format."""
    return {
        "created": when,
        "author": {"displayName": who},
        "body": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        },
    }


class TestArbeitszeit:
    """Netto-Rechnung - der Kern der Aussage im Bericht."""

    def test_wochenende_zaehlt_nicht(self) -> None:
        # Freitag 17:00 bis Montag 09:00: eine Stunde Freitag, eine Montag.
        freitag = dt.datetime(2026, 7, 3, 17, 0, tzinfo=TZ)
        montag = dt.datetime(2026, 7, 6, 9, 0, tzinfo=TZ)
        assert business_seconds(freitag, montag) == 2 * 3600
        # Kalenderzeit dagegen: 64 Stunden. Genau diese Spreizung ist die
        # Aussage, die der Bericht sichtbar macht.
        assert (montag - freitag).total_seconds() == 64 * 3600

    def test_nacht_zaehlt_nicht(self) -> None:
        abends = dt.datetime(2026, 7, 1, 17, 0, tzinfo=TZ)
        morgens = dt.datetime(2026, 7, 2, 9, 0, tzinfo=TZ)
        assert business_seconds(abends, morgens) == 2 * 3600

    def test_rueckwaerts_ist_null(self) -> None:
        spaet = dt.datetime(2026, 7, 2, 9, 0, tzinfo=TZ)
        frueh = dt.datetime(2026, 7, 1, 9, 0, tzinfo=TZ)
        assert business_seconds(spaet, frueh) == 0

    def test_arbeitsfreie_abschnitte_decken_die_luecke(self) -> None:
        start = dt.datetime(2026, 7, 3, 17, 0, tzinfo=TZ)
        ende = dt.datetime(2026, 7, 6, 9, 0, tzinfo=TZ)
        luecken = off_hours(start, ende)
        frei = sum((bis - von).total_seconds() for von, bis in luecken)
        assert frei + business_seconds(start, ende) == pytest.approx((ende - start).total_seconds())


class TestLebenszyklus:
    """Auswertung des Aenderungsprotokolls."""

    def test_durchgeklickte_status_werden_zusammengefasst(self) -> None:
        life = lifecycle.from_raw(
            issue_stub(),
            changelog_stub(
                (stamp(1, 10, 0, 0), "Beispiel, Max", [("status", "Offen", "Schätzen")]),
                (stamp(1, 10, 0, 2), "Beispiel, Max", [("status", "Schätzen", "Bereit")]),
                (stamp(1, 10, 0, 4), "Beispiel, Max", [("status", "Bereit", "IN ARBEIT")]),
            ),
            [],
        )
        wechsel = [ereignis for ereignis in life.events if ereignis.kind == "status"]
        assert len(wechsel) == 1
        assert wechsel[0].text == "Offen -> IN ARBEIT"
        assert "durchgeklickt" in wechsel[0].detail
        # Die Zwischenstufen duerfen keine eigene Phase bekommen.
        assert [span.status for span in life.spans] == ["Offen", "IN ARBEIT"]

    def test_getrennte_wechsel_bleiben_eigene_phasen(self) -> None:
        life = lifecycle.from_raw(
            issue_stub(),
            changelog_stub(
                (stamp(1, 10), "Beispiel, Max", [("status", "Offen", "Prüfen")]),
                (stamp(2, 10), "Beispiel, Max", [("status", "Prüfen", "IN ARBEIT")]),
            ),
            [],
        )
        assert [span.status for span in life.spans] == ["Offen", "Prüfen", "IN ARBEIT"]

    def test_anhaenge_derselben_minute_werden_gebuendelt(self) -> None:
        life = lifecycle.from_raw(
            issue_stub(),
            changelog_stub(
                (
                    stamp(2, 11),
                    "Muster, Erika",
                    [("Attachment", "", f"bild{i}.png") for i in range(5)],
                ),
            ),
            [],
        )
        anhaenge = [ereignis for ereignis in life.events if ereignis.kind == "attachment"]
        assert len(anhaenge) == 1
        assert anhaenge[0].text == "5 Anhaenge"

    def test_entfernte_verknuepfung_bleibt_sichtbar(self) -> None:
        life = lifecycle.from_raw(
            issue_stub(),
            changelog_stub(
                (stamp(1, 9, 1), "Muster, Erika", [("Link", "", "clones ABC-9")]),
                (stamp(1, 9, 5), "Muster, Erika", [("Link", "clones ABC-9", "")]),
            ),
            [],
        )
        texte = [ereignis.text for ereignis in life.events if ereignis.kind == "link"]
        assert any("ENTFERNT" in text for text in texte)
        assert "ABC-9" in life.mentioned

    def test_besitzzeit_folgt_den_zuweisungen(self) -> None:
        life = lifecycle.from_raw(
            issue_stub(),
            changelog_stub(
                (stamp(1, 9, 30), "Muster, Erika", [("assignee", "", "Beispiel, Max")]),
                (stamp(2, 9, 30), "Beispiel, Max", [("assignee", "Beispiel, Max", "Muster, Erika")]),
            ),
            [],
        )
        anteile = {name: prozent for name, _, prozent in life.ownership_share()}
        assert set(anteile) == {"Beispiel, Max", "Muster, Erika"}
        assert life.handovers() == 1


class TestBericht:
    """Anzeigemodell und Ausgabe."""

    def _report(self, **felder: Any) -> viewmodel.Report:
        return build_report(
            issue_stub(**felder),
            changelog_stub(
                (stamp(1, 10), "Beispiel, Max", [("status", "Offen", "IN ARBEIT")]),
            ),
            [comment_stub(stamp(2, 11), "Muster, Erika", "Bitte pruefen")],
            BASE,
        )

    def test_kennzahlen_sind_vollstaendig(self) -> None:
        report = self._report()
        labels = {metric.label for metric in report.metrics}
        assert labels == {
            "Flow-Effizienz",
            "Erste Reaktion",
            "Aufgreifzeit",
            "Rework-Schleifen",
            "Auftragsänderungen",
        }

    def test_html_ist_self_contained(self) -> None:
        html = build_html(self._report())
        assert html.startswith("<!doctype html>")
        assert html.count("<style>") == 1
        assert html.count("<script>") == 1
        # Keine externe Quelle - der Bericht muss offline laufen.
        assert "http://" not in html.replace("http://www.w3.org", "")
        for muster in ("src=\"http", "cdn.", "fonts.googleapis"):
            assert muster not in html

    def test_titel_mit_sonderzeichen_zerlegt_die_seite_nicht(self) -> None:
        boeser_titel = 'Fix <script>alert("x")</script> & mehr'
        html = build_html(self._report(summary=boeser_titel))
        assert "<script>alert" not in html
        assert e(boeser_titel) in html

    def test_datei_wird_mit_lf_geschrieben(self, tmp_path: Any) -> None:
        ziel = write_report(self._report(), tmp_path / "ABC-1.html")
        rohdaten = ziel.read_bytes()
        assert b"\r\n" not in rohdaten
