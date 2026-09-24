"""Tests der Oberflaeche des Performance-Boosters - Reiter, Kacheln, Diagramme, Verdrahtung."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.performance import HintConfig, PerformanceReport, Period, build_report
from jira_timesheet_qt.services.team import Roster, TeamMember, to_storage
from jira_timesheet_qt.ui import main_window
from jira_timesheet_qt.ui.performance_charts import CourseChart, CycleChart, ProfileChart, SizeChart
from jira_timesheet_qt.ui.performance_view import COL, FILTER_ALL, SELF_LABEL, PerformanceView
from jira_timesheet_qt.ui.theme import Mode
from tests.test_performance import CATEGORIES, CONFIG, REWORK, _long_log, change, issue, ts

ACCOUNT = "712020:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _bericht(member: str = "Ich") -> PerformanceReport:
    """Ein Bericht mit einem langen, einem kleinen und einem normalen Ticket, dazu Vorperiode."""
    issues = [
        issue("REAL-1", done=ts(31), hours=40),
        issue("REAL-2", done=ts(10), hours=0.5),
        issue("REAL-3", done=ts(12), hours=0.25),
        issue("REAL-4", done=ts(9, month=7), created=ts(1, month=7), hours=6),
    ]
    histories = {
        "REAL-1": _long_log(3, 31),
        "REAL-2": REWORK,
        "REAL-3": [change(ts(11), "Offen", "In Arbeit"), change(ts(12), "In Arbeit", "Fertig")],
        "REAL-4": _long_log(6, 8, month=7),
    }
    return build_report(
        member=member,
        period=Period(dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
        prior_period=Period(dt.date(2026, 7, 1), dt.date(2026, 7, 31)),
        issues=issues,
        histories=histories,
        worklogs=[(dt.date(2026, 8, 4), 36000.0), (dt.date(2026, 7, 4), 18000.0)],
        config=CONFIG,
        categories=CATEGORIES,
        hint_config=HintConfig(),
        created=[dt.date(2026, 8, 5), dt.date(2026, 8, 20), dt.date(2026, 7, 2)],
        closed=(4, None),
    )


def _abweichende_punkte(widget: Any) -> int:
    """Zaehlt die Bildpunkte, die das Diagramm auf einen magentafarbenen Grund malt."""
    widget.resize(360, 180)
    bild = QPixmap(360, 180)
    bild.fill(Qt.GlobalColor.magenta)
    widget.render(bild)
    aufnahme = bild.toImage()
    grund = aufnahme.pixel(0, 0)
    return sum(1 for y in range(0, 180, 2) for x in range(0, 360, 2) if aufnahme.pixel(x, y) != grund)


class TestAnsicht:
    def test_eigener_eintrag_steht_vorn_und_auswahl_bleibt(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_members(["Anna", "Bert"])
        assert view._member_box.itemText(0) == SELF_LABEL
        assert view.current_member() == ""
        view.select_member("Bert")
        gemeldet: list[str] = []
        view.member_changed.connect(gemeldet.append)
        view.set_members(["Bert", "Carla"])
        assert view.current_member() == "Bert"
        assert gemeldet == [], "Unveraenderte Auswahl darf keinen Abruf ausloesen"
        view.set_members(["Carla"])
        assert view.current_member() == ""
        assert gemeldet == [""]

    def test_zeitraum_ist_exklusiv_und_meldet_sich(self, qapp: QApplication) -> None:
        view = PerformanceView()
        assert view.current_period() == "3M"
        gemeldet: list[str] = []
        view.period_changed.connect(gemeldet.append)
        view._period_buttons["6M"].click()
        assert gemeldet == ["6M"]
        assert [k for k, b in view._period_buttons.items() if b.isChecked()] == ["6M"]
        view.set_period("YTD")
        assert view.current_period() == "YTD"
        assert gemeldet == ["6M"], "set_period ist fuer den gemerkten Stand und bleibt stumm"

    def test_bericht_fuellt_kacheln_und_tabelle(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_bericht())
        assert view._tile_done.value.text() == "3"
        assert "+2" in view._tile_done.delta.text()
        assert view._tile_booked.value.text() == "10,0 h"
        assert view._tile_small.value.text() == "67 %"
        assert view._table.rowCount() == 3
        # Alle drei sind auffaellig: eines lang, zwei klein. Dann gilt die Abschlussfolge.
        nummern = [view._table.item(r, 0).text() for r in range(3)]  # type: ignore[union-attr]
        gruende = [view._table.item(r, COL["Auffällig"]).text() for r in range(3)]  # type: ignore[union-attr]
        assert nummern == ["REAL-2", "REAL-3", "REAL-1"]
        assert gruende == ["Viele kleine Tickets", "Viele kleine Tickets", "Lange Tickets"]
        assert view._tile_created.value.text() == "2"
        assert view._tile_points.value.text() == "-"
        assert "0 der 3 erledigten Tickets geschätzt" in view._period_label.text()
        # Gebucht mit zwei Nachkommastellen - 0,25 h darf nicht als 0,2 erscheinen.
        assert view._table.item(1, COL["Gebucht (h)"]).text() == "0,25"  # type: ignore[union-attr]
        for titel in ("Lange Tickets", "Viele kleine Tickets", "Durchlaufzeit steigt"):
            assert titel in view._hints.text()

    def test_auswahl_meldet_die_ticketnummer(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_bericht())
        gemeldet: list[Any] = []
        view.ticket_selected.connect(gemeldet.append)
        assert view.select_ticket("REAL-3")
        assert view.current_key() == "REAL-3"
        assert gemeldet[-1] == "REAL-3"
        assert not view.select_ticket("GIBT-ES-NICHT")


@pytest.mark.parametrize("klasse", [CourseChart, CycleChart, SizeChart, ProfileChart])
def test_diagramme_zeichnen_daten(qapp: QApplication, klasse: Any) -> None:
    leer = klasse(Mode.DARK)
    voll = klasse(Mode.DARK)
    voll.set_report(_bericht())
    ohne, mit = _abweichende_punkte(leer), _abweichende_punkte(voll)
    assert mit > 3 * max(1, ohne), f"{klasse.__name__}: {mit} gegen {ohne} Bildpunkte"


class FakePerfWorker(QObject):
    """Ersetzt den echten Faden. Merkt sich Person und Zeitraum."""

    progress = Signal(str)
    log = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    finished = Signal()

    erzeugt: list[FakePerfWorker] = []

    def __init__(
        self,
        settings: Settings,
        config: Any,
        member: TeamMember | None,
        period: str,
        cache_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.member = member
        self.period = period
        FakePerfWorker.erzeugt.append(self)

    def isRunning(self) -> bool:  # noqa: N802 - Qt-Schreibweise
        return True

    def start(self) -> None:
        pass

    def wait(self, msecs: int = 0) -> bool:
        return True


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> list[FakePerfWorker]:
    FakePerfWorker.erzeugt = []
    monkeypatch.setattr(main_window, "PerformanceWorker", FakePerfWorker)
    return FakePerfWorker.erzeugt


def _fenster(team: list[TeamMember] | None = None) -> Any:
    einstellungen = Settings(jira_host="https://jira.example.com", email="max@example.com", jira_token="geheim")
    einstellungen.team_members = to_storage(Roster(members=list(team or [])))
    return main_window.MainWindow(einstellungen, Mode.DARK)


class TestHauptfenster:
    def test_reiter_steht_ganz_rechts(self, qapp: QApplication) -> None:
        fenster = _fenster()
        views = main_window._VIEWS
        assert views[-1] == "Performance-Booster"
        assert fenster._stack.widget(main_window._PERF_VIEW) is fenster._performance
        assert fenster._tabs.tabText(main_window._PERF_VIEW) == "Performance-Booster"

    def test_erster_besuch_laedt_die_eigenen_tickets(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        assert len(fake) == 1
        assert fake[0].member is None and fake[0].period == "3M"
        # Zweiter Besuch laedt nicht erneut.
        fenster._tabs.setCurrentIndex(0)
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        assert len(fake) == 1

    def test_ueberholter_abruf_wird_verworfen(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        fenster._performance._period_buttons["1M"].click()
        assert [w.period for w in fake] == ["3M", "1M"]
        fake[0].finished_ok.emit(_bericht("alt"))
        assert fenster._performance.report() is None
        fake[1].finished_ok.emit(_bericht("neu"))
        report = fenster._performance.report()
        assert report is not None and report.member == "neu"

    def test_zeitraum_wird_gemerkt(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._performance._period_buttons["6M"].click()
        assert _fenster()._performance.current_period() == "6M"

    def test_person_aus_der_merkliste(self, qapp: QApplication, fake: list[Any]) -> None:
        anna = TeamMember(display_name="Anna", account_ids=(ACCOUNT,))
        fenster = _fenster([anna])
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        fenster._performance.select_member("Anna")
        assert fake[-1].member is not None and fake[-1].member.account_ids == (ACCOUNT,)

    def test_fehler_laesst_den_naechsten_besuch_neu_laden(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        fake[0].failed.emit("HTTP 500")
        assert fenster._performance._placeholder.text().endswith("HTTP 500")
        fenster._tabs.setCurrentIndex(0)
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        assert len(fake) == 2

    def test_screenshot_modus_zeigt_keine_echten_nummern(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        fake[0].finished_ok.emit(_bericht())
        fenster._toggle_anonymize()
        tabelle = fenster._performance._table
        texte = [tabelle.item(r, c).text() for r in range(tabelle.rowCount()) for c in range(tabelle.columnCount())]
        sichtbar = " ".join(texte) + fenster._performance._hints.text()
        assert "REAL-" not in sichtbar and "Titel REAL" not in sichtbar
        # Die Zahlen bleiben - sie sind die Aussage des Bildes.
        assert fenster._performance._tile_done.value.text() == "3"
        fenster._toggle_anonymize()
        assert "REAL-1" in [tabelle.item(r, 0).text() for r in range(tabelle.rowCount())]

    def test_vorschau_zieht_in_den_booster(self, qapp: QApplication, fake: list[Any]) -> None:
        fenster = _fenster()
        fenster._settings.show_ticket_preview = True
        fenster._stack.setCurrentIndex(main_window._PERF_VIEW)
        assert fenster._performance.preview_host().indexOf(fenster._preview) >= 0


def test_skala_ist_gerade_und_hat_luft() -> None:
    from jira_timesheet_qt.ui.performance_charts import _scale_top

    # Bei 1 stuende sonst zweimal "0" an der Skala, bei 2 liefe die Zahl in den Titel.
    assert [_scale_top(n) for n in (0, 1, 2, 3, 5, 10)] == [2.0, 2.0, 4.0, 4.0, 6.0, 12.0]


class TestLadenUndSortieren:
    def test_nummernspalte_sortiert_numerisch(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_bericht())
        view._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        report = _bericht()
        # Nummern mit unterschiedlicher Stellenzahl: textlich stuende 10 vor 9.
        neu = {"REAL-1": "ABC-5979", "REAL-2": "ABC-17741", "REAL-3": "ABC-17132"}
        report.all_tickets = [replace(t, key=neu[t.key]) for t in report.all_tickets]
        report.hints = []
        view.set_report(report)
        view._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        keys = [view._table.item(r, 0).text() for r in range(view._table.rowCount())]  # type: ignore[union-attr]
        assert keys == ["ABC-5979", "ABC-17132", "ABC-17741"]

    def test_hinweis_leert_alles_von_der_vorherigen_person(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_members(["Anna"])
        view.set_report(_bericht("Ich"))
        view.select_ticket("REAL-1")
        gemeldet: list[Any] = []
        view.ticket_selected.connect(gemeldet.append)
        view.select_member("Anna")
        view.show_message("Auswertung wird geladen ...")
        assert view.report() is None
        assert view._table.rowCount() == 0
        assert gemeldet[-1] is None, "Die Vorschau muss das alte Ticket loslassen"
        assert view._tile_done.value.text() == "-" and view._tile_done.delta.text() == ""
        assert view._tile_booked.value.text() == "-"
        assert view._placeholder.text().startswith("Anna:")
        assert view._hints.text() == ""

    def test_personenwechsel_im_fenster_leert_sofort(self, qapp: QApplication, fake: list[Any]) -> None:
        anna = TeamMember(display_name="Anna", account_ids=(ACCOUNT,))
        fenster = _fenster([anna])
        fenster._tabs.setCurrentIndex(main_window._PERF_VIEW)
        fake[0].finished_ok.emit(_bericht())
        assert fenster._performance._tile_done.value.text() == "3"
        fenster._performance.select_member("Anna")
        assert fenster._performance._tile_done.value.text() == "-"
        assert fenster._performance._placeholder.text().startswith("Anna:")


def _alle_tickets_bericht() -> PerformanceReport:
    """Ein Bericht mit allen vier Beteiligungen."""
    issues = [
        issue("REAL-1", done=ts(31), hours=40),
        issue("OPEN-1", status="In Arbeit", category="indeterminate", hours=2),
    ]
    created = [issue("NEW-1", status="Offen", category="new", created=ts(5)), issue("OLD-1", created=ts(5, month=7))]
    closed = [issue("FREMD-1", done=ts(20), hours=3), issue("REAL-1", done=ts(31), hours=40)]
    return build_report(
        member="Ich",
        period=Period(dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
        prior_period=Period(dt.date(2026, 7, 1), dt.date(2026, 7, 31)),
        issues=issues,
        histories={"REAL-1": _long_log(3, 31)},
        worklogs=[],
        config=CONFIG,
        categories=CATEGORIES,
        hint_config=HintConfig(),
        created=[dt.date(2026, 8, 5), dt.date(2026, 7, 5)],
        closed=(2, None),
        created_issues=created,
        closed_issues=closed,
    )


def _nummern(view: PerformanceView) -> list[str]:
    tabelle = view._table
    return sorted(tabelle.item(r, COL["Ticket"]).text() for r in range(tabelle.rowCount()))  # type: ignore[union-attr]


class TestAlleTickets:
    def test_alle_beteiligungen_stehen_in_der_liste(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        assert view.current_filter() == FILTER_ALL
        # OLD-1 wurde in der Vorperiode angelegt und gehoert nicht dazu.
        assert _nummern(view) == ["FREMD-1", "NEW-1", "OPEN-1", "REAL-1"]
        zeile = next(r for r in range(view._table.rowCount()) if view._table.item(r, 0).text() == "REAL-1")  # type: ignore[union-attr]
        assert view._table.item(zeile, COL["Beteiligung"]).text() == "Erledigt, Geschlossen"  # type: ignore[union-attr]
        assert view._filter_buttons["Alle"].text() == "Alle (4)"
        assert view._filter_buttons["Geschlossen"].text() == "Geschlossen (2)"

    @pytest.mark.parametrize(
        ("filter_name", "erwartet"),
        [
            ("Erledigt", ["REAL-1"]),
            ("Erstellt", ["NEW-1"]),
            ("Geschlossen", ["FREMD-1", "REAL-1"]),
            ("In Arbeit", ["OPEN-1"]),
        ],
    )
    def test_filter(self, qapp: QApplication, filter_name: str, erwartet: list[str]) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        view._filter_buttons[filter_name].click()
        assert _nummern(view) == erwartet

    def test_kachel_klick_filtert(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        view._tile_created.clicked.emit()
        assert view.current_filter() == "Erstellt" and _nummern(view) == ["NEW-1"]
        view._tile_done.clicked.emit()
        assert view.current_filter() == "Erledigt" and _nummern(view) == ["REAL-1"]

    def test_link_im_hinweis_waehlt_das_ticket_auch_ausserhalb_des_filters(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        assert '<a href="ticket:REAL-1">REAL-1</a>' in view._hints.text()
        view.set_filter("Erstellt")
        gemeldet: list[str] = []
        view.hint_ticket_clicked.connect(gemeldet.append)
        view._hints.linkActivated.emit("ticket:REAL-1")
        assert view.current_key() == "REAL-1"
        assert view.current_filter() == FILTER_ALL
        assert gemeldet == ["REAL-1"]

    def test_zeitraum_steht_gross_in_der_kopfzeile(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        assert view._range.text() == "01.08.2026 - 31.08.2026"
        assert view._prior_range.text() == "verglichen mit 01.07.2026 - 31.07.2026"
        # Der Name steht nicht mehr doppelt in der Zeile darunter.
        assert "Ich" not in view._period_label.text()

    def test_zeitraum_wechselt_sofort_beim_klick(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.services.performance import period_for

        view = PerformanceView()
        view._period_buttons["YTD"].click()
        start, _ = period_for("YTD", dt.date.today())
        assert view._range.text().startswith(f"{start.start:%d.%m.%Y}")


def test_screenshot_modus_ersetzt_auch_alle_tickets(qapp: QApplication) -> None:
    from jira_timesheet_qt.services.anonymizer import anonymize_performance

    kopie = anonymize_performance(_alle_tickets_bericht())
    sichtbar = " ".join(f"{t.key} {t.summary} {t.status}" for t in kopie.all_tickets)
    for echt in ("REAL-1", "FREMD-1", "NEW-1", "OPEN-1", "Titel", "In Arbeit", "Fertig", "Offen"):
        assert echt not in sichtbar, echt
    assert sorted(len(t.involvement) for t in kopie.all_tickets) == [1, 1, 1, 2]


class TestKacheln:
    def test_eigener_eintrag_heisst_ich(self, qapp: QApplication) -> None:
        view = PerformanceView()
        assert view._member_box.itemText(0) == "Ich"

    def test_kachel_alle_tickets_zaehlt_und_filtert(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        assert view._tile_all.value.text() == "4"
        view.set_filter("Erstellt")
        view._tile_all.clicked.emit()
        assert view.current_filter() == FILTER_ALL and len(_nummern(view)) == 4

    def test_aktiver_filter_markiert_seine_kachel(self, qapp: QApplication) -> None:
        view = PerformanceView()
        view.set_report(_alle_tickets_bericht())
        assert view._tile_all.property("active") == "true"
        view._filter_buttons["Erledigt"].click()
        assert view._tile_done.property("active") == "true"
        assert view._tile_all.property("active") == "false"
        # Kennzahl-Kacheln filtern nicht und werden nie markiert.
        assert view._tile_cycle.property("clickable") == "false"
        assert view._tile_cycle.property("active") == "false"

    def test_hover_und_markierung_stehen_im_stylesheet(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.ui.theme import build_qss

        qss = build_qss(Mode.LIGHT, "Segoe UI", "Consolas")
        assert '#PerfTile[clickable="true"]:hover' in qss
        assert '#PerfTile[active="true"]' in qss
