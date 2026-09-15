"""Die Kacheln der Monatsansicht.

Die reinen Regeln - Zeilen je Ticket, Zustand eines Tages, Balken, Hinweis -
laufen ohne Zeichnen und mit festem Stichtag. Was nur beim Zeichnen entsteht,
die Trefferflaechen der Ticketnummern, pruefen die Tests an einem gerenderten
Bild.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.ui.calendar_view import (
    CalendarView,
    DayCell,
    DayState,
    bar_fractions,
    day_state,
    split_rows,
    ticket_rows,
    tooltip_html,
)
from jira_timesheet_qt.ui.theme import Mode

# Montag. Fest, damit kein Test am heutigen Datum haengt.
STICHTAG = date(2026, 9, 14)


def _leerer_zettel(jahr: int, monat: int) -> Timesheet:
    """Ein geladener Monat ohne eine einzige Buchung - anders als None."""
    return Timesheet(developer="Max Mustermann", email="", date_from=date(jahr, monat, 1), date_to=date(jahr, monat, 28))


def _entry(
    ticket: str,
    hours: float,
    summary: str = "Arbeit",
    *,
    day: date = date(2026, 9, 10),
    manual: bool = False,
    customer: str = "",
) -> WorklogEntry:
    return WorklogEntry(
        date=day,
        ticket=ticket,
        summary=summary,
        author="Max Mustermann",
        budget="",
        hours=hours,
        manual=manual,
        customer=customer,
    )


class TestTicketZeilen:
    def test_buchungen_eines_tickets_werden_zusammengezaehlt(self) -> None:
        erste = _entry("ABC-1", 1.0)
        zeilen = ticket_rows([erste, _entry("ABC-2", 3.0), _entry("ABC-1", 2.5)])
        assert [(z.ticket, z.hours) for z in zeilen] == [("ABC-1", 3.5), ("ABC-2", 3.0)]
        assert zeilen[0].entry is erste, "Ein Klick oeffnet den ersten Eintrag des Tickets"

    def test_manuell_bleibt_erhalten_auch_wenn_nur_eine_buchung_manuell_ist(self) -> None:
        zeilen = ticket_rows([_entry("ABC-1", 1.0), _entry("ABC-1", 1.0, manual=True)])
        assert zeilen[0].manual is True

    def test_eintraege_ohne_ticket_bleiben_nach_beschreibung_getrennt(self) -> None:
        zeilen = ticket_rows([_entry("", 1.0, "Telefonat"), _entry("", 0.5, "Doku"), _entry("", 0.5, "Telefonat")])
        assert [(z.summary, z.hours) for z in zeilen] == [("Telefonat", 1.5), ("Doku", 0.5)]

    @pytest.mark.parametrize(
        ("anzahl", "platz", "sichtbar", "zusammengefasst"),
        [(5, 5, 5, 0), (6, 5, 4, 2), (3, 1, 0, 3), (3, 0, 0, 3)],
    )
    def test_ueberzaehlige_zeilen_werden_zusammengefasst(
        self, anzahl: int, platz: int, sichtbar: int, zusammengefasst: int
    ) -> None:
        zeilen = ticket_rows([_entry(f"ABC-{i}", 1.0 + i) for i in range(anzahl)])
        oben, rest = split_rows(zeilen, platz)
        assert (len(oben), len(rest)) == (sichtbar, zusammengefasst)
        assert oben + rest == zeilen, "Nichts darf verloren gehen"


class TestTageszustand:
    @pytest.mark.parametrize(
        ("zelle", "erwartet"),
        [
            (DayCell(date(2026, 9, 10), True, 6.0), DayState.BOOKED),
            (DayCell(date(2026, 9, 11), True), DayState.MISSING),
            (DayCell(STICHTAG, True), DayState.TODAY),
            (DayCell(date(2026, 9, 15), True), DayState.FUTURE),
            (DayCell(date(2026, 9, 15), True, 2.0), DayState.FUTURE),
            (DayCell(date(2026, 9, 12), True), DayState.FREE),
            (DayCell(date(2026, 9, 9), True, holiday="Testfeiertag"), DayState.FREE),
            (DayCell(date(2026, 8, 31), False), DayState.OUTSIDE),
        ],
    )
    def test_einordnung(self, zelle: DayCell, erwartet: DayState) -> None:
        assert day_state(zelle, STICHTAG) is erwartet

    def test_kommende_tage_fehlen_nicht(self, qapp: QApplication) -> None:
        """Bis 09/2026 war jeder kommende Arbeitstag rot umrandet."""
        view = CalendarView()
        view.set_month(2026, 9, _leerer_zettel(2026, 9), "SN", 8.0)
        fehlend = [c.day for c in view.missing_workdays(STICHTAG)]
        # 1.-4. und 7.-11. September, ohne Buchung und vor dem Stichtag.
        assert len(fehlend) == 9
        assert date(2026, 9, 11) in fehlend
        assert STICHTAG not in fehlend
        assert date(2026, 9, 15) not in fehlend


class TestLadezustand:
    """Solange die Buchungen fehlen, darf kein Tag als fehlend gelten.

    Bis 09/2026 blitzte beim Blaettern und beim Start jeder vergangene Tag rot
    mit "fehlt" auf, bis die Daten eintrafen.
    """

    def test_ohne_daten_ist_ein_leerer_tag_unbekannt(self) -> None:
        assert day_state(DayCell(date(2026, 9, 11), True), STICHTAG, known=False) is DayState.UNKNOWN

    def test_ohne_daten_fehlt_nichts(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 9, None, "SN", 8.0)
        assert view.missing_workdays(STICHTAG) == []

    def test_blaettern_nimmt_die_daten_des_alten_monats_nicht_mit(self, qapp: QApplication) -> None:
        from jira_timesheet_qt.models.settings import Settings
        from jira_timesheet_qt.ui.demo import demo_timesheet
        from jira_timesheet_qt.ui.main_window import MainWindow

        # Leere Einstellungen: _shift_month startet dann keinen Abruf.
        fenster = MainWindow(Settings(), Mode.DARK)
        fenster._year, fenster._month = 2026, 9
        fenster.set_timesheet(demo_timesheet())
        fenster._shift_month(-1)
        assert (fenster._year, fenster._month) == (2026, 8)
        assert fenster._calendar.missing_workdays(STICHTAG) == []


class TestFeiertag:
    def test_feiertag_hebt_sich_vom_wochenende_ab(self, qapp: QApplication) -> None:
        """Der 3. Oktober 2026 ist ein Samstag - ohne Toenung saehe er aus wie der Sonntag."""
        view = CalendarView(Mode.LIGHT)
        view.resize(1400, 800)
        view.set_month(2026, 10, _leerer_zettel(2026, 10), "SN", 8.0)
        bild = QPixmap(view.size())
        view.render(bild)
        aufnahme = bild.toImage()

        area, zelle_b, zelle_h, _ = view._geometry()

        def unten_mitte(tag: date) -> tuple[int, int]:
            index = next(i for i, c in enumerate(view.cells) if c.day == tag)
            x = area.x() + (index % 7) * zelle_b + zelle_b / 2
            y = area.y() + view.HEADER_HEIGHT + (index // 7) * zelle_h + zelle_h - 20
            return int(x), int(y)

        feiertag = aufnahme.pixelColor(*unten_mitte(date(2026, 10, 3))).name()
        sonntag = aufnahme.pixelColor(*unten_mitte(date(2026, 10, 4))).name()
        assert feiertag != sonntag, f"Feiertag {feiertag} gleicht dem Sonntag {sonntag}"


class TestBalken:
    @pytest.mark.parametrize(
        ("stunden", "soll", "erwartet"),
        [(4.0, 8.0, (0.5, 0.0)), (8.0, 8.0, (1.0, 0.0)), (10.0, 8.0, (0.8, 0.2)), (0.0, 8.0, (0.0, 0.0)), (3.0, 0.0, (0.0, 0.0))],
    )
    def test_anteile(self, stunden: float, soll: float, erwartet: tuple[float, float]) -> None:
        assert bar_fractions(stunden, soll) == pytest.approx(erwartet)

    def test_wochensoll_zaehlt_nur_arbeitstage_des_monats(self, qapp: QApplication) -> None:
        view = CalendarView()
        view.set_month(2026, 7, None, "SN", 8.0)
        soll_je_kw = dict(zip([kw for kw, _ in view.week_summaries()], view.week_targets(), strict=True))
        assert soll_je_kw[27] == pytest.approx(24.0), "1.-3. Juli, der Rest der Woche gehoert zum Juni"
        assert soll_je_kw[30] == pytest.approx(40.0)


class TestHinweis:
    def test_nennt_datum_soll_und_alle_eintraege(self) -> None:
        zelle = DayCell(
            date(2026, 9, 10),
            True,
            2.5,
            [_entry("ABC-1", 2.0, "Fehler beheben", customer="Vertrieb"), _entry("", 0.5, "Telefonat", manual=True)],
        )
        text = tooltip_html(zelle, 8.0)
        assert "Do, 10.09.2026" in text
        assert "2,50 h von 8,00 h" in text
        assert "Vertrieb" in text
        assert "Telefonat - manuell" in text

    def test_beschreibungen_werden_escaped(self) -> None:
        zelle = DayCell(date(2026, 9, 10), True, 1.0, [_entry("ABC-1", 1.0, "Tag <b>fett</b> & Co")])
        text = tooltip_html(zelle, 8.0)
        assert "&lt;b&gt;fett&lt;/b&gt; &amp; Co" in text
        assert "<b>fett</b>" not in text

    def test_ausserhalb_des_monats_gibt_es_keinen(self) -> None:
        assert tooltip_html(DayCell(date(2026, 8, 31), False), 8.0) == ""


class TestZeichnen:
    def _gezeichnet(self, breite: int, eintraege: list[WorklogEntry]) -> CalendarView:
        view = CalendarView(Mode.DARK)
        view.resize(breite, 700)
        view.set_month(2026, 9, None, "SN", 8.0)
        zelle = next(c for c in view.cells if c.day == date(2026, 9, 10))
        zelle.entries = eintraege
        zelle.hours = sum(e.hours for e in eintraege)
        view.render(QPixmap(view.size()))
        return view

    def test_breite_kachel_zeichnet_eine_zeile_je_ticket(self, qapp: QApplication) -> None:
        view = self._gezeichnet(1600, [_entry("ABC-1", 3.0), _entry("ABC-2", 2.0), _entry("ABC-3", 1.0)])
        treffer = [rect for rect, _ in view._ticket_hits]
        assert len(treffer) == 3
        assert len({round(r.x()) for r in treffer}) == 1, "Alle Nummern stehen am linken Rand der Kachel"
        assert len({round(r.y()) for r in treffer}) == 3, "Jede Nummer in einer eigenen Zeile"

    def test_zeilen_stehen_nach_stunden_sortiert(self, qapp: QApplication) -> None:
        view = self._gezeichnet(1600, [_entry("ABC-1", 1.0), _entry("ABC-2", 3.0)])
        von_oben = [entry.ticket for _, entry in sorted(view._ticket_hits, key=lambda hit: hit[0].y())]
        assert von_oben == ["ABC-2", "ABC-1"]

    def test_zu_viele_tickets_passen_nicht_alle_hinein(self, qapp: QApplication) -> None:
        view = self._gezeichnet(1600, [_entry(f"ABC-{100 + i}", 0.5) for i in range(30)])
        assert 0 < len(view._ticket_hits) < 30

    def test_schmale_kachel_faellt_auf_die_nummern_zurueck(self, qapp: QApplication) -> None:
        """Ohne Platz fuer Nummer und Stunden bleiben die Nummern klickbar."""
        view = self._gezeichnet(560, [_entry("ABC-12345", 3.0), _entry("ABC-12346", 2.0)])
        assert view._ticket_hits


def test_der_reiter_heisst_monat() -> None:
    from jira_timesheet_qt.ui.main_window import _MONTH_VIEW, _VIEWS

    assert _VIEWS[_MONTH_VIEW] == "Monat"
    assert "Kalender" not in _VIEWS
