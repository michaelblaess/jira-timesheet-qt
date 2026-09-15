"""Ticket-Vorschau: Widget, Worker und Ablauf im Hauptfenster.

Kein Test spricht mit Jira. Der Worker bekommt einen Attrappen-Client, das
Hauptfenster einen Attrappen-Worker - geprueft wird die Ablaufsteuerung, nicht
das Netz.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QModelIndex, QObject, QUrl, Signal
from PySide6.QtWidgets import QApplication
from QAppFramework.color import contrast_ratio

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import WorklogEntry
from jira_timesheet_qt.services.ticket_preview import IssuePreviewCache, TicketPreviewData
from jira_timesheet_qt.ui.theme import PREVIEW_PAPER, Mode, build_qss
from jira_timesheet_qt.ui.ticket_preview import LINK_CONTRAST, TicketPreview, link_color

HOST = "https://beispiel.example"


def _entry(ticket: str) -> WorklogEntry:
    return WorklogEntry(
        date=date(2026, 9, 10), ticket=ticket, summary="Arbeit", author="Max Mustermann", budget="", hours=1.0
    )


def _daten(key: str = "ABC-1", **werte: Any) -> TicketPreviewData:
    felder: dict[str, Any] = {
        "summary": "Beispielticket",
        "status": "Im Code Review",
        "status_category": "indeterminate",
        "assignee": "Max Mustermann",
        "creator": "Erika Musterfrau",
        "due_date": "2026-09-30",
        "updated": "2026-09-14T14:00:00.000+0200",
        "time_spent_seconds": 9000,
        "extra": [("Environments", "prod, test")],
        "description_html": "<p>Hallo</p>",
        "fetched_at": "2026-09-14T15:03:21",
    }
    felder.update(werte)
    return TicketPreviewData(key=key, **felder)


class TestWidget:
    def test_zeigt_kopf_titel_und_leere_felder(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.set_host(HOST)
        vorschau.show_data(_daten(fix_versions="2026.10"))
        paare = dict(vorschau.field_pairs())
        assert paare["Zugewiesene Person"] == "Max Mustermann"
        assert paare["Autor"] == "Erika Musterfrau"
        assert paare["Fälligkeitsdatum"] == "30.09.2026"
        assert paare["Lösungsversionen"] == "2026.10"
        assert paare["Environments"] == "prod, test"
        assert "Übergeordnet" not in paare, "Leere Felder bleiben weg"
        assert vorschau._title.text() == "Beispielticket"
        assert f"{HOST}/browse/ABC-1" in vorschau._key.text()
        assert vorschau._stand.text() == "Stand 14.09.2026 15:03"

    @pytest.mark.parametrize(
        ("gebucht", "geschaetzt", "erwartet"),
        [
            (9000, 0, ("2,50 h", "")),
            (9000, 14400, ("2,50 h", "von 4,00 h")),
            (0, 0, ("0,00 h", "")),
        ],
    )
    def test_gebuchte_stunden(self, qapp: QApplication, gebucht: int, geschaetzt: int, erwartet: tuple[str, str]) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten(time_spent_seconds=gebucht, original_estimate_seconds=geschaetzt))
        assert vorschau.hours_texts() == erwartet

    def test_status_steht_als_etikett_neben_den_stunden(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten())
        assert vorschau.status_label() == ("Im Code Review", "indeterminate", False)
        assert "Status" not in dict(vorschau.field_pairs()), "Der Status steht nicht doppelt da"
        vorschau.show_data(_daten(status="", status_category=""))
        assert vorschau.status_label()[2] is True, "Ohne Status kein leeres Etikett"

    def test_status_regeln_im_stylesheet(self) -> None:
        qss = build_qss(Mode.DARK, "", "")
        assert '#PreviewStatus[category="indeterminate"]' in qss
        assert '#PreviewStatus[category="done"]' in qss

    def test_leere_loesungsversion_bleibt_weg(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten())
        assert "Lösungsversionen" not in dict(vorschau.field_pairs())

    @pytest.mark.parametrize("modus", [Mode.DARK, Mode.LIGHT])
    def test_links_bleiben_auf_weiss_lesbar(self, qapp: QApplication, modus: Mode) -> None:
        """Der orange Grundakzent kommt auf Weiss nur auf 3,58 - zu wenig fuer Text."""
        assert contrast_ratio(link_color(modus), PREVIEW_PAPER) >= LINK_CONTRAST
        vorschau = TicketPreview(modus)
        assert link_color(modus) in vorschau._body.document().defaultStyleSheet()

    def test_die_beschreibung_steht_auf_weiss(self) -> None:
        regel = re.search(r"#PreviewBody \{([^}]*)\}", build_qss(Mode.DARK, "", ""))
        assert regel is not None
        assert f"background-color: {PREVIEW_PAPER}" in regel.group(1)

    def test_links_oeffnen_nie_von_selbst(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        assert vorschau._body.openLinks() is False
        assert vorschau._body.openExternalLinks() is False
        assert vorschau._key.openExternalLinks() is False

    def test_relative_links_gehen_an_den_host(
        self, qapp: QApplication, blockierte_browser_aufrufe: list[str]
    ) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.set_host(HOST)
        vorschau._open_link(QUrl("/jira/people/123"))
        assert any(f"{HOST}/jira/people/123" in str(aufruf) for aufruf in blockierte_browser_aufrufe)

    @pytest.mark.parametrize("ziel", ["javascript:alert(1)", "file:///C:/Windows/system.ini"])
    def test_andere_schemata_werden_nicht_geoeffnet(
        self, qapp: QApplication, blockierte_browser_aufrufe: list[str], ziel: str
    ) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.set_host(HOST)
        vorschau._open_link(QUrl(ziel))
        assert blockierte_browser_aufrufe == []

    def test_bilder_nur_aus_dem_ordner_und_auf_die_breite(self, qapp: QApplication, tmp_path: Path) -> None:
        from jira_timesheet_qt.ui.ticket_preview import PreviewBrowser

        (tmp_path / "gross.png").write_bytes(_png(1200, 600))
        browser = PreviewBrowser()
        browser.resize(400, 300)
        browser.image_dir = tmp_path
        bild = browser.local_image(QUrl("gross.png"))
        assert not bild.isNull()
        assert bild.width() <= max(160, browser.viewport().width() - 32)
        assert bild.height() * 2 == bild.width(), "Seitenverhaeltnis bleibt"

        browser.image_dir = tmp_path / "unterordner"
        assert browser.local_image(QUrl("../gross.png")).isNull(), "Aus der Adresse zaehlt nur der Dateiname"
        browser.image_dir = tmp_path
        assert browser.local_image(QUrl("https://fremd.example/gross.png")).isNull()
        browser.image_dir = None
        assert browser.local_image(QUrl("gross.png")).isNull()

    def test_platzhalter_vergisst_das_ticket(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten())
        vorschau.show_placeholder("Kein Eintrag gewählt")
        assert vorschau.current_data is None
        assert vorschau._stack.currentIndex() == 0


class TestKopf:
    """Der Kopf als Ticketkarte: gruppiert, ohne Leeres, mit Hervorhebungen."""

    def test_gleiche_person_steht_nur_einmal(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten(assignee="Max Mustermann", creator="Max Mustermann"))
        paare = vorschau.field_pairs()
        assert ("Zugewiesen und Autor", "Max Mustermann") in paare
        assert all(label not in ("Zugewiesene Person", "Autor") for label, _ in paare)

    def test_ohne_zuweisung_und_faelligkeit_bleibt_die_auskunft(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten(assignee="", due_date=""))
        paare = dict(vorschau.field_pairs())
        assert paare["Zugewiesene Person"] == "nicht zugewiesen"
        assert paare["Fälligkeitsdatum"] == "keine"

    def test_prioritaet_none_steht_nicht_da(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten(issue_type="Aufgabe", priority="None"))
        assert vorschau.meta_text() == "Aufgabe"
        vorschau.show_data(_daten(issue_type="Aufgabe", priority="Hoch"))
        assert vorschau.meta_text() == "Aufgabe · Priorität Hoch"

    @pytest.mark.parametrize(
        ("faellig", "erwartet"),
        [("2026-09-10", "overdue"), ("2026-09-16", "soon"), ("2026-09-17", "")],
    )
    def test_faelligkeit_wird_gefaerbt(self, qapp: QApplication, faellig: str, erwartet: str) -> None:
        vorschau = TicketPreview(Mode.DARK)
        # Freitag: bis Mittwoch sind es drei Werktage, das Wochenende zaehlt nicht.
        vorschau.today = lambda: date(2026, 9, 11)
        vorschau.show_data(_daten(due_date=faellig))
        assert vorschau.field_due_state() == erwartet

    def test_faerberegeln_im_stylesheet(self) -> None:
        qss = build_qss(Mode.DARK, "", "")
        assert '#PreviewValue[due="overdue"]' in qss
        assert '#PreviewValue[due="soon"]' in qss
        assert '#PreviewEstimate[over="true"]::chunk' in qss

    def test_schaetzungsbalken(self, qapp: QApplication) -> None:
        vorschau = TicketPreview(Mode.DARK)
        vorschau.show_data(_daten(time_spent_seconds=9000, original_estimate_seconds=0))
        assert vorschau.estimate_state()[0] is False, "Ohne Schaetzung kein Balken"
        vorschau.show_data(_daten(time_spent_seconds=9000, original_estimate_seconds=18000))
        assert vorschau.estimate_state() == (True, 50, False)
        vorschau.show_data(_daten(time_spent_seconds=27000, original_estimate_seconds=18000))
        assert vorschau.estimate_state() == (True, 100, True)

    def test_uebergeordnet_ist_ein_link(self, qapp: QApplication, blockierte_browser_aufrufe: list[str]) -> None:
        from PySide6.QtWidgets import QLabel

        vorschau = TicketPreview(Mode.DARK)
        vorschau.set_host(HOST)
        vorschau.show_data(_daten(parent="ABC-0 Ein <b>Epos</b>"))
        treffer = [label for label in vorschau.findChildren(QLabel) if "ABC-0" in label.text()]
        assert len(treffer) == 1
        assert f'href="{HOST}/browse/ABC-0"' in treffer[0].text()
        assert "<b>" not in treffer[0].text(), "Der Titel aus Jira wird maskiert"
        treffer[0].linkActivated.emit(f"{HOST}/browse/ABC-0")
        assert blockierte_browser_aufrufe

    def test_fusszeile_trennt_jira_und_abruf(self, qapp: QApplication) -> None:
        from datetime import datetime, timedelta, timezone

        vorschau = TicketPreview(Mode.DARK)
        vorschau.now = lambda: datetime(2026, 9, 14, 20, 0, tzinfo=timezone(timedelta(hours=2)))
        vorschau.show_data(_daten())
        assert vorschau.updated_text() == "In Jira geändert vor 6 Std."
        assert vorschau._stand.text() == "Stand 14.09.2026 15:03"

    def test_nur_die_feldbloecke_haben_eine_hoechstbreite(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.ticket_preview import HEADER_MAX_WIDTH

        vorschau = TicketPreview(Mode.DARK)
        vorschau.resize(1100, 600)
        vorschau.show_data(_daten(summary="Ein Titel " * 20))
        vorschau.show()
        QApplication.processEvents()
        assert vorschau._fields_area.maximumWidth() == HEADER_MAX_WIDTH
        # Der Titel darf breiter werden als die Felder - sonst bricht er unnoetig um.
        assert vorschau._title.width() > HEADER_MAX_WIDTH - 200
        vorschau.hide()


class TestZeitUndFaelligkeit:
    """Die reinen Hilfsfunktionen hinter dem Kopf."""

    @pytest.mark.parametrize(
        ("heute", "faellig", "erwartet"),
        [
            (date(2026, 9, 11), "", ""),
            (date(2026, 9, 11), "kaputt", ""),
            (date(2026, 9, 11), "2026-09-10", "overdue"),
            (date(2026, 9, 11), "2026-09-11", "soon"),
            (date(2026, 9, 11), "2026-09-13", "soon"),
            (date(2026, 9, 11), "2026-09-16", "soon"),
            (date(2026, 9, 11), "2026-09-17", ""),
            (date(2026, 9, 14), "2026-12-24", ""),
        ],
    )
    def test_due_state(self, heute: date, faellig: str, erwartet: str) -> None:
        from jira_timesheet_qt.services.ticket_preview import due_state

        assert due_state(faellig, heute) == erwartet

    @pytest.mark.parametrize(
        ("zeitpunkt", "erwartet"),
        [
            ("2026-09-14T19:59:40.000+0200", "gerade eben"),
            ("2026-09-14T19:15:00.000+0200", "vor 45 Min."),
            ("2026-09-14T14:00:00.000+0200", "vor 6 Std."),
            ("2026-09-13T12:00:00.000+0200", "vor 1 Tag"),
            ("2026-09-04T12:00:00.000+0200", "vor 10 Tagen"),
            ("2026-07-01T12:00:00.000+0200", "01.07.2026"),
            ("2026-09-15T08:00:00.000+0200", "15.09.2026 08:00"),
            ("unlesbar", "unlesbar"),
        ],
    )
    def test_relative_time(self, zeitpunkt: str, erwartet: str) -> None:
        from datetime import datetime, timedelta, timezone

        from jira_timesheet_qt.services.ticket_preview import relative_time

        jetzt = datetime(2026, 9, 14, 20, 0, tzinfo=timezone(timedelta(hours=2)))
        assert relative_time(zeitpunkt, jetzt) == erwartet

    def test_split_parent_und_prioritaet(self) -> None:
        from jira_timesheet_qt.services.ticket_preview import is_empty_priority, split_parent

        assert split_parent("ABC-12 Agiles Projekt") == ("ABC-12", "Agiles Projekt")
        assert split_parent("ohne Schluessel") == ("", "ohne Schluessel")
        assert is_empty_priority("None") and is_empty_priority(" ") and not is_empty_priority("Hoch")


class _Client:
    """Attrappe des JiraClient - merkt sich, was abgefragt wurde."""

    def __init__(self, updated: str = "U2", timespent: int = 9000) -> None:
        self.aufrufe: list[tuple[str, tuple[str, ...], bool]] = []
        self.feldlisten = 0
        self._updated = updated
        self._timespent = timespent

    async def get_issue(self, key: str, fields: Any, rendered: bool = False) -> dict[str, Any]:
        self.aufrufe.append((key, tuple(fields), rendered))
        return {
            "key": key,
            "fields": {
                "summary": "Frisch",
                "updated": self._updated,
                "timespent": self._timespent,
                "customfield_1": {"value": "prod"},
            },
            "renderedFields": {"description": "<p>neu</p>"},
        }

    async def get_fields(self) -> list[dict[str, Any]]:
        self.feldlisten += 1
        return [{"id": "customfield_1", "name": "Environments"}]

    async def get_attachment(self, url: str) -> tuple[bytes, str]:
        raise AssertionError(f"Kein Bild erwartet: {url}")


def _png(breite: int, hoehe: int) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage

    bild = QImage(breite, hoehe, QImage.Format.Format_RGB32)
    bild.fill(0x3366CC)
    puffer = QBuffer()
    puffer.open(QIODevice.OpenModeFlag.WriteOnly)
    # Zur Laufzeit will PySide6 hier einen str. Mit b"PNG" wie in den Stubs
    # scheitert der Aufruf mit ValueError - gemessen am 14.09.2026.
    bild.save(puffer, "PNG")  # type: ignore[call-overload]
    return bytes(puffer.data().data())


class _BilderClient(_Client):
    """Liefert eine Beschreibung mit einem eigenen, einem kaputten und einem fremden Bild."""

    EIGEN = f"{HOST}/rest/api/3/attachment/content/1"
    KAPUTT = f"{HOST}/rest/api/3/attachment/content/2"

    def __init__(self) -> None:
        super().__init__()
        self.bildabrufe: list[str] = []

    async def get_issue(self, key: str, fields: Any, rendered: bool = False) -> dict[str, Any]:
        daten = await super().get_issue(key, fields, rendered)
        daten["renderedFields"] = {
            "description": (
                f'<p><img src="{self.EIGEN}" width="900" style="x">'
                f'<img src="{self.KAPUTT}" alt="kaputt">'
                '<img src="https://fremd.example/x.png" alt="fremd"></p>'
            )
        }
        return daten

    async def get_attachment(self, url: str) -> tuple[bytes, str]:
        self.bildabrufe.append(url)
        if url == self.KAPUTT:
            raise RuntimeError("503")
        return _png(40, 20), "image/png"


class TestWorker:
    def _worker(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        client: _Client,
        cached: TicketPreviewData | None = None,
    ) -> tuple[Any, IssuePreviewCache]:
        from jira_timesheet_qt.ui import jira_worker

        monkeypatch.setattr(jira_worker, "JiraClient", lambda **_: client)
        cache = IssuePreviewCache(tmp_path, HOST)
        einstellungen = Settings(jira_host=HOST, preview_extra_fields=["Environments"])
        return jira_worker.TicketPreviewWorker(einstellungen, "ABC-1", cache, cached), cache

    def test_unveraenderter_stand_spart_den_vollen_abruf(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        client = _Client(updated="U1", timespent=9000)
        worker, _ = self._worker(monkeypatch, tmp_path, client, _daten(updated="U1", time_spent_seconds=9000))
        assert asyncio.run(worker._fetch()) is None
        assert client.aufrufe == [("ABC-1", ("updated", "timespent"), False)]

    def test_neue_buchung_laedt_neu_auch_ohne_geaenderten_stand(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Ob eine Buchung updated aendert, ist nicht belegt - die Zeit wird deshalb mitverglichen."""
        client = _Client(updated="U1", timespent=10800)
        worker, _ = self._worker(monkeypatch, tmp_path, client, _daten(updated="U1", time_spent_seconds=9000))
        daten = asyncio.run(worker._fetch())
        assert daten is not None
        assert daten.time_spent_seconds == 10800

    def test_geaenderter_stand_holt_neu_und_merkt_es_sich(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        client = _Client(updated="U2")
        worker, cache = self._worker(monkeypatch, tmp_path, client, _daten(updated="U1"))
        daten = asyncio.run(worker._fetch())
        assert daten is not None
        assert daten.extra == [("Environments", "prod")]
        assert client.aufrufe[-1][2] is True, "Der volle Abruf holt renderedFields"
        assert {"customfield_1", "timespent", "fixVersions"} <= set(client.aufrufe[-1][1])
        assert cache.load("ABC-1") == daten

    def test_bilder_kommen_in_den_cache_und_nur_vom_eigenen_host(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from jira_timesheet_qt.services.ticket_preview import image_folder

        client = _BilderClient()
        worker, cache = self._worker(monkeypatch, tmp_path, client)
        daten = asyncio.run(worker._fetch())
        assert daten is not None
        assert sorted(client.bildabrufe) == sorted([_BilderClient.EIGEN, _BilderClient.KAPUTT])
        assert list(daten.images) == [_BilderClient.EIGEN]
        name = daten.images[_BilderClient.EIGEN]
        ordner = image_folder(cache.directory, "ABC-1")
        assert ordner is not None and (ordner / name).is_file()
        assert f'<img src="{name}"' in daten.description_html
        assert "[Bild: kaputt]" in daten.description_html, "Ein gescheitertes Bild wird zum Hinweis"
        assert "[Bild: fremd]" in daten.description_html
        assert "fremd.example" not in daten.description_html
        assert "width" not in daten.description_html

    def test_feld_ids_werden_nur_einmal_ermittelt(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        client = _Client()
        worker, _ = self._worker(monkeypatch, tmp_path, client)
        asyncio.run(worker._fetch())
        asyncio.run(worker._fetch())
        assert client.feldlisten == 1


@pytest.fixture
def attrappe(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Ersetzt den Vorschau-Worker. Liefert die erzeugten Attrappen."""
    from jira_timesheet_qt.ui import main_window

    erzeugt: list[Any] = []

    class _Worker(QObject):
        finished_ok = Signal(object)
        unchanged = Signal(str)
        failed = Signal(str)
        log = Signal(str)
        finished = Signal()

        def __init__(
            self,
            settings: Settings,
            key: str,
            cache: IssuePreviewCache,
            cached: TicketPreviewData | None = None,
            parent: QObject | None = None,
        ) -> None:
            super().__init__(parent)
            self.key = key
            self.cached = cached
            erzeugt.append(self)

        def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
            return False

        def start(self) -> None:
            pass

        def wait(self, msecs: int = 0) -> bool:
            return True

    monkeypatch.setattr(main_window, "TicketPreviewWorker", _Worker)
    return erzeugt


def _fenster(vorschau: bool = True) -> Any:
    from jira_timesheet_qt.ui.main_window import MainWindow

    einstellungen = Settings(
        show_ticket_preview=vorschau, jira_host=HOST, email="max@example.com", jira_token="geheim"
    )
    return MainWindow(einstellungen, Mode.DARK)


class TestHauptfenster:
    def test_ausgeschaltet_gibt_es_keine_vorschau(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster(vorschau=False)
        assert fenster._preview.isHidden()
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        assert attrappe == []

    def test_auswahl_wird_entprellt(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._on_row_changed(QModelIndex(), QModelIndex())
        assert fenster._preview_timer.isActive()
        assert attrappe == [], "Erst nach der Wartezeit wird abgerufen"

    def test_ohne_cache_voller_abruf(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        assert [(w.key, w.cached) for w in attrappe] == [("ABC-1", None)]
        assert fenster._preview.current_data is None

    def test_mit_cache_sofort_da_und_nur_pruefen(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        gemerkt = _daten(updated="U1")
        fenster._preview_cache().save(gemerkt)
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        assert fenster._preview.current_data is not None
        assert attrappe[-1].cached == gemerkt
        fenster._update_preview(force=True)
        assert attrappe[-1].cached is None, "Der Refresh-Knopf uebergeht den gemerkten Stand"

    def test_ueberholtes_ergebnis_wird_verworfen(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        fenster._current_entry = _entry("ABC-2")
        fenster._update_preview()
        attrappe[0].finished_ok.emit(_daten("ABC-1"))
        assert fenster._preview.current_data is None
        attrappe[1].finished_ok.emit(_daten("ABC-2"))
        data = fenster._preview.current_data
        assert data is not None and data.key == "ABC-2"

    def test_screenshot_modus_ruft_nichts_ab(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._preview_cache().save(_daten())
        fenster._anonymize = True
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        assert attrappe == []
        assert fenster._preview.current_data is None, "Auch der Cache zeigt keine echten Inhalte"

    def test_manueller_eintrag_ohne_ticket(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._current_entry = _entry("")
        fenster._update_preview()
        assert attrappe == []

    def test_fehlschlag_laesst_den_gemerkten_stand_stehen(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        fenster._preview_cache().save(_daten(updated="U1"))
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        attrappe[-1].failed.emit("HTTP 503")
        assert fenster._preview.current_data is not None
        assert "fehlgeschlagen" in fenster._preview._stand.text()

    def test_neue_stunden_erscheinen_nach_dem_abruf(self, qapp: QApplication, attrappe: list[Any]) -> None:
        fenster = _fenster()
        gemerkt = _daten(time_spent_seconds=9000)
        fenster._preview_cache().save(gemerkt)
        fenster._current_entry = _entry("ABC-1")
        fenster._update_preview()
        assert fenster._preview.hours_texts()[0] == "2,50 h"
        attrappe[-1].finished_ok.emit(replace(gemerkt, time_spent_seconds=10800))
        assert fenster._preview.hours_texts()[0] == "3,00 h"
