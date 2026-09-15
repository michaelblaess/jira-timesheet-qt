"""Der oberflaechenfreie Kern der Ticket-Vorschau.

Alle Namen und Inhalte sind erfunden. Die Struktur des Jira-JSON entspricht
dem, was Proben gegen eine echte Cloud-Instanz am 14.09.2026 geliefert haben:
Personen mit displayName, Auswahlfelder mit value, Versionen mit name, die
gebuchte Zeit als Sekunden in timespent, die Beschreibung als fertiges HTML
in renderedFields.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.ticket_preview import (
    CACHE_SCHEMA,
    IssuePreviewCache,
    TicketPreviewData,
    field_value_text,
    german_date,
    german_datetime,
    hours_text,
    image_folder,
    image_sources,
    parse_extra_field_names,
    parse_issue,
    resolve_field_ids,
    rewrite_images,
    seconds_value,
)

ABRUF = datetime(2026, 9, 14, 15, 3, 21)


def _roh(**felder: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "summary": "Beispielticket",
        "status": {"name": "In Arbeit", "statusCategory": {"key": "indeterminate", "colorName": "yellow"}},
        "issuetype": {"name": "Aufgabe"},
        "priority": {"name": "Hoch"},
        "assignee": {"displayName": "Max Mustermann"},
        "creator": {"displayName": "Erika Musterfrau"},
        "duedate": None,
        "updated": "2026-09-14T14:00:00.000+0200",
        "timespent": 9000,
        "timeoriginalestimate": None,
        "fixVersions": [{"name": "2026.10"}, {"name": "2026.11"}],
        "customfield_1": [{"value": "prod"}, {"value": "test"}],
        "customfield_2": {"value": "Team A"},
    }
    fields.update(felder)
    return {
        "key": "ABC-1",
        "fields": fields,
        "renderedFields": {"description": "<p>Hallo <a class=\"user-hover\">Max</a></p>"},
    }


class TestAbbildung:
    def test_kopffelder(self) -> None:
        daten = parse_issue(_roh(), {"Environments": "customfield_1", "Team[Single]": "customfield_2"}, ABRUF)
        assert daten.key == "ABC-1"
        assert daten.summary == "Beispielticket"
        assert (daten.status, daten.issue_type, daten.priority) == ("In Arbeit", "Aufgabe", "Hoch")
        assert daten.status_category == "indeterminate"
        assert daten.assignee == "Max Mustermann"
        assert daten.creator == "Erika Musterfrau", "Autor ist der Ersteller, nicht der Reporter"
        assert daten.due_date == ""
        assert daten.extra == [("Environments", "prod, test"), ("Team[Single]", "Team A")]
        assert daten.fetched_at == "2026-09-14T15:03:21"

    @pytest.mark.parametrize(
        ("status", "kategorie"),
        [
            ({"name": "Offen", "statusCategory": {"key": "new"}}, "new"),
            ({"name": "Fertig", "statusCategory": {"key": "done"}}, "done"),
            ({"name": "Seltsam", "statusCategory": {"key": "undefined"}}, ""),
            ({"name": "Ohne Kategorie"}, ""),
            (None, ""),
        ],
    )
    def test_statuskategorie(self, status: Any, kategorie: str) -> None:
        """Die Farbe haengt an der Kategorie - Namen sind je Instanz verschieden."""
        assert parse_issue(_roh(status=status), {}, ABRUF).status_category == kategorie

    def test_gebuchte_zeit_und_loesungsversionen(self) -> None:
        daten = parse_issue(_roh(timeoriginalestimate=14400), {}, ABRUF)
        assert daten.time_spent_seconds == 9000
        assert daten.original_estimate_seconds == 14400
        assert daten.fix_versions == "2026.10, 2026.11"

    def test_ohne_zeit_und_versionen(self) -> None:
        """So lag das echte Ticket vor: keine Schaetzung, keine Loesungsversion."""
        daten = parse_issue(_roh(timespent=None, fixVersions=[]), {}, ABRUF)
        assert (daten.time_spent_seconds, daten.original_estimate_seconds, daten.fix_versions) == (0, 0, "")

    def test_das_fertige_html_wird_uebernommen(self) -> None:
        daten = parse_issue(_roh(), {}, ABRUF)
        assert daten.description_html == "<p>Hallo <a class=\"user-hover\">Max</a></p>"

    def test_ohne_gerendertes_html_wird_der_text_escaped(self) -> None:
        roh = _roh(description="Erste Zeile <b>\nzweite\n\nNeuer Absatz & Co")
        roh["renderedFields"] = {}
        daten = parse_issue(roh, {}, ABRUF)
        assert daten.description_html == "<p>Erste Zeile &lt;b&gt;<br>zweite</p><p>Neuer Absatz &amp; Co</p>"

    def test_uebergeordnetes_ticket(self) -> None:
        daten = parse_issue(_roh(parent={"key": "ABC-0", "fields": {"summary": "Epic"}}), {}, ABRUF)
        assert daten.parent == "ABC-0 Epic"

    def test_kennungen_der_personen(self) -> None:
        """Ueber die Kennung fuehrt die Vorschau nach "Mein Team" - der Name trifft nicht sicher."""
        daten = parse_issue(
            _roh(
                assignee={"displayName": "Max Mustermann", "accountId": "5cf79d64eba18b0ea85a7b53"},
                creator={"displayName": "Erika Musterfrau", "accountId": "712020:e1153ec2"},
            ),
            {},
            ABRUF,
        )
        assert (daten.assignee_id, daten.creator_id) == ("5cf79d64eba18b0ea85a7b53", "712020:e1153ec2")

    def test_ohne_person_keine_kennung(self) -> None:
        daten = parse_issue(_roh(assignee=None, creator={"displayName": "Erika Musterfrau"}), {}, ABRUF)
        assert (daten.assignee_id, daten.creator_id) == ("", "")

    def test_kennungen_ueberstehen_den_cache(self) -> None:
        daten = TicketPreviewData(key="ABC-1", assignee_id="a1", creator_id="c2")
        zurueck = TicketPreviewData.from_dict(json.loads(json.dumps(daten.to_dict())))
        assert (zurueck.assignee_id, zurueck.creator_id) == ("a1", "c2")

    @pytest.mark.parametrize(
        ("wert", "text"),
        [
            (None, ""),
            ("frei", "frei"),
            (3, "3"),
            ({"displayName": "Max"}, "Max"),
            ({"name": "Team X"}, "Team X"),
            ({"value": "prod"}, "prod"),
            ([{"value": "a"}, None, {"value": "b"}], "a, b"),
            ({"unbekannt": 1}, ""),
        ],
    )
    def test_feldwerte(self, wert: Any, text: str) -> None:
        assert field_value_text(wert) == text


class TestStunden:
    @pytest.mark.parametrize(("wert", "sekunden"), [(9000, 9000), ("60", 60), (None, 0), ("x", 0), (-5, 0), (True, 0)])
    def test_sekunden(self, wert: Any, sekunden: int) -> None:
        assert seconds_value(wert) == sekunden

    @pytest.mark.parametrize(("sekunden", "text"), [(9000, "2,50 h"), (0, "0,00 h"), (900, "0,25 h"), (37800, "10,50 h")])
    def test_stundentext(self, sekunden: int, text: str) -> None:
        assert hours_text(sekunden) == text


class TestFeldnamen:
    def test_eingabe_wird_zerlegt(self) -> None:
        assert parse_extra_field_names(" Environments, Team[Single],,environments ") == ["Environments", "Team[Single]"]

    def test_nur_ganze_namen_treffen(self) -> None:
        """'Team' darf nicht 'Team[Single]' treffen - Instanzen fuehren aehnliche Felder nebeneinander."""
        felder = [
            {"id": "customfield_9", "name": "Team"},
            {"id": "customfield_2", "name": "Team[Single]"},
            {"id": "customfield_1", "name": "Environments"},
        ]
        assert resolve_field_ids(felder, ["environments", "Team[Single]", "Fehlt"]) == {
            "environments": "customfield_1",
            "Team[Single]": "customfield_2",
        }


class TestDatum:
    def test_datum(self) -> None:
        assert german_date("2026-09-30") == "30.09.2026"
        assert german_date("") == ""
        assert german_date("kaputt") == "kaputt"

    def test_zeitstempel(self) -> None:
        assert german_datetime("2026-09-14T15:03:21.000+0200") == "14.09.2026 15:03"
        assert german_datetime("2026-09-14") == "14.09.2026"


class TestCache:
    def test_rundlauf(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, "https://beispiel.atlassian.net")
        daten = parse_issue(_roh(), {"Environments": "customfield_1"}, ABRUF)
        cache.save(daten)
        assert cache.load("ABC-1") == daten

    def test_eine_aeltere_fassung_wird_neu_geladen(self, tmp_path: Path) -> None:
        """Ein Eintrag von vor den Stunden bliebe sonst dauerhaft ohne sie."""
        cache = IssuePreviewCache(tmp_path, "https://beispiel.example")
        cache.save(TicketPreviewData(key="ABC-1"))
        datei = cache.directory / "ABC-1.json"
        roh = json.loads(datei.read_text(encoding="utf-8"))
        roh["schema"] = CACHE_SCHEMA - 1
        datei.write_text(json.dumps(roh), encoding="utf-8")
        assert cache.load("ABC-1") is None
        del roh["schema"]
        datei.write_text(json.dumps(roh), encoding="utf-8")
        assert cache.load("ABC-1") is None

    def test_hosts_bleiben_getrennt(self, tmp_path: Path) -> None:
        IssuePreviewCache(tmp_path, "https://eins.example").save(TicketPreviewData(key="ABC-1", summary="eins"))
        assert IssuePreviewCache(tmp_path, "https://zwei.example").load("ABC-1") is None

    @pytest.mark.parametrize("schluessel", ["../boese-1", "ABC-1/../../x", "", "ABC"])
    def test_unsaubere_schluessel_werden_nie_zu_pfaden(self, tmp_path: Path, schluessel: str) -> None:
        cache = IssuePreviewCache(tmp_path, "https://beispiel.example")
        cache.save(TicketPreviewData(key=schluessel))
        assert not any(tmp_path.rglob("*.json"))
        assert cache.load(schluessel) is None

    def test_kaputte_datei_gilt_als_leer(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, "https://beispiel.example")
        cache.directory.mkdir(parents=True)
        (cache.directory / "ABC-1.json").write_text("{kein json", encoding="utf-8")
        assert cache.load("ABC-1") is None

    def test_feld_ids_gelten_nur_fuer_dieselben_namen(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, "https://beispiel.example")
        cache.save_field_ids(["Environments"], {"Environments": "customfield_1"})
        assert cache.load_field_ids(["Environments"]) == {"Environments": "customfield_1"}
        assert cache.load_field_ids(["Environments", "Team"]) is None

    def test_aufraeumen_nach_alter(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, "https://beispiel.example")
        cache.save(TicketPreviewData(key="ABC-1", fetched_at=(ABRUF - timedelta(days=100)).isoformat()))
        cache.save(TicketPreviewData(key="ABC-2", fetched_at=(ABRUF - timedelta(days=10)).isoformat()))
        cache.save_field_ids(["X"], {})
        assert cache.prune(ABRUF) == 1
        assert cache.load("ABC-1") is None
        assert cache.load("ABC-2") is not None
        assert cache.load_field_ids(["X"]) == {}


HOST = "https://beispiel.atlassian.net"


class TestBilder:
    """Wie die Probe am 14.09.2026: absolute Adresse auf dem eigenen Host, mit width und style."""

    EIGEN = f"{HOST}/rest/api/3/attachment/content/10001"

    def test_nur_bilder_vom_eigenen_host_werden_geholt(self) -> None:
        beschreibung = (
            f'<p><img src="{self.EIGEN}" width="900" style="x"></p>'
            '<p><img src="/rest/api/3/attachment/content/10002"></p>'
            '<p><img src="https://fremd.example/bild.png"></p>'
            '<p><img src="//fremd.example/zwei.png"></p>'
            f'<p><img src="{self.EIGEN}"></p>'
        )
        assert image_sources(beschreibung, HOST) == [self.EIGEN, "/rest/api/3/attachment/content/10002"]

    def test_hoechstens_zwanzig_bilder(self) -> None:
        beschreibung = "".join(f'<img src="{HOST}/a/{i}">' for i in range(30))
        assert len(image_sources(beschreibung, HOST)) == 20

    def test_escapte_adressen_werden_gelesen(self) -> None:
        assert image_sources(f'<img src="{HOST}/a?x=1&amp;y=2">', HOST) == [f"{HOST}/a?x=1&y=2"]

    def test_umschreiben(self) -> None:
        beschreibung = (
            f'<p><img src="{self.EIGEN}" alt="Screenshot" width="900" style="max-width:100%"></p>'
            '<p><img src="https://fremd.example/b.png" alt="Fremd &amp; mehr"></p>'
            '<p><img src="https://fremd.example/c.png"></p>'
        )
        ergebnis = rewrite_images(beschreibung, {self.EIGEN: "abc.png"})
        assert '<img src="abc.png" alt="Screenshot">' in ergebnis
        assert "width" not in ergebnis and "style" not in ergebnis
        assert "<i>[Bild: Fremd &amp; mehr]</i>" in ergebnis
        assert "<i>[Bild]</i>" in ergebnis
        assert "fremd.example" not in ergebnis

    def test_speichern_mit_grenzen(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, HOST)
        name = cache.save_image("ABC-1", self.EIGEN, b"png", "image/png; charset=binary")
        assert name is not None and name.endswith(".png")
        ordner = image_folder(cache.directory, "ABC-1")
        assert ordner is not None and (ordner / name).read_bytes() == b"png"
        assert cache.save_image("ABC-1", self.EIGEN, b"<html>", "text/html") is None, "Nur Bildtypen"
        assert cache.save_image("../boese-1", self.EIGEN, b"png", "image/png") is None
        assert image_folder(cache.directory, "../boese-1") is None

    def test_zu_grosse_bilder_werden_nicht_gespeichert(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from jira_timesheet_qt.services import ticket_preview

        monkeypatch.setattr(ticket_preview, "MAX_IMAGE_BYTES", 10)
        cache = IssuePreviewCache(tmp_path, HOST)
        assert cache.save_image("ABC-1", self.EIGEN, b"x" * 11, "image/png") is None

    def test_aufraeumen_nimmt_den_bildordner_mit(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, HOST)
        cache.save(TicketPreviewData(key="ABC-1", fetched_at=(ABRUF - timedelta(days=100)).isoformat()))
        cache.save_image("ABC-1", self.EIGEN, b"png", "image/png")
        ordner = image_folder(cache.directory, "ABC-1")
        assert ordner is not None and ordner.is_dir()
        cache.prune(ABRUF)
        assert not ordner.exists()

    def test_bilder_ueberstehen_den_cache(self, tmp_path: Path) -> None:
        cache = IssuePreviewCache(tmp_path, HOST)
        daten = TicketPreviewData(key="ABC-1", images={self.EIGEN: "abc.png"})
        cache.save(daten)
        assert cache.load("ABC-1") == daten


class TestEinstellungen:
    def test_vorgaben(self) -> None:
        assert Settings().show_ticket_preview is False
        assert Settings().preview_extra_fields == []

    def test_rundlauf(self) -> None:
        """Alle drei Stellen: Feld, _FIELDS und _from_dict."""
        einstellungen = Settings(show_ticket_preview=True, preview_extra_fields=["Environments", "Team[Single]"])
        roh = json.loads(json.dumps(einstellungen.to_dict()))
        wieder = Settings._from_dict(roh)
        assert wieder.show_ticket_preview is True
        assert wieder.preview_extra_fields == ["Environments", "Team[Single]"]
