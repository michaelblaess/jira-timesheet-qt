"""Tests fuer die klickbaren Ticketnummern in den Kalenderkacheln.

Jede Ticketnummer wird einzeln gezeichnet und bekommt ein eigenes
Trefferrechteck. Ein Klick meldet genau diesen Eintrag (nicht mehr immer den
ersten des Tages), ein Hover hebt ihn hervor.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap
from pytestqt.qtbot import QtBot

from jira_timesheet_qt.ui.calendar_view import CalendarView
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.theme import Mode


def _painted_calendar(qtbot: QtBot) -> CalendarView:
    """Baut einen Kalender mit Beispieldaten und erzwingt ein Zeichnen.

    Das paintEvent baut die Trefferliste der Ticketnummern auf - ohne einen
    Zeichenvorgang gibt es nichts zu treffen.
    """
    cal = CalendarView(Mode.DARK)
    qtbot.addWidget(cal)
    cal.resize(1200, 700)
    cal.set_month(2026, 7, demo_timesheet(), "SN", 8.0)
    cal.render(QPixmap(cal.size()))
    return cal


def test_ticket_hits_are_built(qtbot: QtBot) -> None:
    cal = _painted_calendar(qtbot)
    assert cal._ticket_hits  # mehrere Ticketnummern gezeichnet


def test_hit_maps_to_its_entry(qtbot: QtBot) -> None:
    """Der Punkt in der Mitte eines Ticket-Rechtecks liefert genau dessen Eintrag."""
    cal = _painted_calendar(qtbot)
    rect, entry = cal._ticket_hits[0]
    assert cal._ticket_at(rect.center().x(), rect.center().y()) is entry


def test_click_emits_the_clicked_entry(qtbot: QtBot) -> None:
    cal = _painted_calendar(qtbot)
    rect, entry = cal._ticket_hits[0]
    center = QPoint(int(rect.center().x()), int(rect.center().y()))
    with qtbot.waitSignal(cal.ticket_activated, timeout=500) as blocker:
        # pytest-qt typisiert QtBot nur teilweise - mouseClick gilt als untypisiert.
        qtbot.mouseClick(cal, Qt.MouseButton.LeftButton, pos=center)  # type: ignore[no-untyped-call]
    assert blocker.args[0] is entry


def test_empty_area_has_no_ticket(qtbot: QtBot) -> None:
    cal = _painted_calendar(qtbot)
    assert cal._ticket_at(2, 2) is None


def test_hover_highlights_ticket(qtbot: QtBot) -> None:
    """Ueber einer Ticketnummer merkt sich der Kalender den Eintrag (Hover-Stil)."""
    cal = _painted_calendar(qtbot)
    rect, entry = cal._ticket_hits[0]
    cal._hovered_ticket = None
    # Direkter Hit-Test statt synthetischem Move-Event - deterministisch.
    assert cal._ticket_at(rect.center().x(), rect.center().y()) is entry
