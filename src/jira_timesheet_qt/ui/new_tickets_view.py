"""Reiter "Neue Tickets": was die Team-Mitglieder zuletzt angelegt haben.

Die Ansicht ist duenn: sie haelt die geladene Liste und filtert sie lokal nach
Person und Zeitraum. Abruf und Aufbereitung liegen im Worker und im Kern.
"""

from __future__ import annotations

import datetime as dt
import webbrowser
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.new_tickets import (
    ALL_MEMBERS,
    DEFAULT_WINDOW,
    WINDOWS,
    created_label,
    visible_tickets,
    window_start,
)
from jira_timesheet_qt.services.ticket_board import Ticket, key_sort_value

from .cell_delegate import CellDelegate
from .person_menu import person_actions

# Beschriftung des Eintrags "alle Mitglieder" - steht immer zuerst.
ALL_LABEL = "Alle"

_COLUMNS = (
    "Ticket",
    "Titel",
    "Typ",
    "Priorität",
    "Status",
    "Erstellt von",
    "Erstellt",
    "Bearbeiter",
)
# Spaltennummern ueber den Namen - Tests und Code verdrahten keine Zahlen.
COL: dict[str, int] = {name: index for index, name in enumerate(_COLUMNS)}
_STRETCH = COL["Titel"]

# Sortierwert in einer eigenen Rolle, damit Zeitpunkte als Zeitpunkte sortieren.
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1

_WEEKDAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _weekday(day: dt.date) -> bool:
    """Mo-Fr - bis das Fenster den Feiertagskalender hereinreicht."""
    return day.weekday() < 5


class _SortItem(QTableWidgetItem):
    """Tabellenzelle, die nach ihrem Sortierwert statt nach dem Text sortiert."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine, theirs = self.data(_SORT_ROLE), other.data(_SORT_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        try:
            return bool(mine < theirs)
        except TypeError:
            return super().__lt__(other)


class NewTicketsView(QWidget):
    """Liste der neuen Tickets mit Personen- und Zeitraumfilter."""

    # Neue Auswahl, Nummer oder None.
    ticket_selected = Signal(object)
    # Erneut aus Jira laden.
    refresh_requested = Signal()
    # Zeitraum gewechselt, mit Kuerzel - das Fenster merkt es sich.
    window_changed = Signal(str)
    # Angezeigte Anzahl hat sich geaendert (fuer den Reitertitel).
    count_changed = Signal(int)
    detail_requested = Signal(object)
    report_requested = Signal(str)
    # Personen aus dem Kontextmenue: accountId und Name.
    person_requested = Signal(str, str)
    team_add_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tickets: list[Ticket] | None = None
        self._by_key: dict[str, Ticket] = {}
        self._is_workday: Callable[[dt.date], bool] = _weekday
        self._today: Callable[[], dt.date] = dt.date.today
        self._anonymized = False
        self._report_available = True
        self._team_ids: frozenset[str] = frozenset()
        # Anzeige-Umformung (Screenshot-Modus). Gefiltert wird immer auf den
        # echten Daten, sonst passt kein erfundener Name zur Personenauswahl.
        self._display: Callable[[list[Ticket]], list[Ticket]] | None = None
        self._build_ui()

    # --- Aufbau ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("Team-Mitglied:"))
        self._member_box = QComboBox()
        self._member_box.setObjectName("NewMemberFilter")
        self._member_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._member_box.setMinimumContentsLength(18)
        self._member_box.addItem(ALL_LABEL, ALL_MEMBERS)
        self._member_box.currentIndexChanged.connect(lambda _index: self._refill())
        head.addWidget(self._member_box)

        head.addSpacing(12)
        self._window_group = QButtonGroup(self)
        self._window_group.setExclusive(True)
        self._window_buttons: dict[str, QToolButton] = {}
        for kind, days in WINDOWS.items():
            button = QToolButton()
            button.setObjectName("PerfPeriod")
            button.setText(kind)
            button.setCheckable(True)
            button.setToolTip(
                "Seit Beginn des letzten Arbeitstags" if days == 1 else f"Seit Beginn der letzten {days} Arbeitstage"
            )
            self._window_group.addButton(button)
            self._window_buttons[kind] = button
            head.addWidget(button)
        self._window_buttons[DEFAULT_WINDOW].setChecked(True)
        self._window_group.buttonClicked.connect(self._on_window_clicked)

        head.addSpacing(24)
        self._range = QLabel("")
        self._range.setObjectName("PerfRange")
        head.addWidget(self._range)
        head.addSpacing(12)
        self._count = QLabel("")
        self._count.setObjectName("PerfPriorRange")
        head.addWidget(self._count)

        head.addStretch(1)
        refresh = QPushButton("Aktualisieren")
        refresh.setToolTip("Neue Tickets erneut aus Jira laden")
        refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        head.addWidget(refresh)
        outer.addLayout(head)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setObjectName("NewTicketsTable")
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setItemDelegate(CellDelegate(self._table))
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_STRETCH, QHeaderView.ResizeMode.Stretch)
        self._table.currentCellChanged.connect(lambda *_args: self.ticket_selected.emit(self.current_key()))
        self._table.cellClicked.connect(self._on_click)
        self._table.cellDoubleClicked.connect(lambda row, _column: self._emit_detail(self._ticket_at(row)))

        self._placeholder = QLabel("Noch nichts geladen.")
        self._placeholder.setObjectName("BoardPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._placeholder)
        self._pages.addWidget(self._table)

        # Rechts haengt das Fenster die Ticket-Vorschau ein, wie in den Ticketlisten.
        self._side = QSplitter(Qt.Orientation.Horizontal)
        self._side.setChildrenCollapsible(False)
        self._side.addWidget(self._pages)
        outer.addWidget(self._side, 1)

        self._show_range()

    # --- Einstellungen von aussen ----------------------------------------

    def set_workday_check(self, is_workday: Callable[[dt.date], bool]) -> None:
        """Uebernimmt den Feiertagskalender - nach Ostermontag zaehlt 1T ab Donnerstag."""
        self._is_workday = is_workday
        self._show_range()
        self._refill()

    def set_clock(self, today: Callable[[], dt.date]) -> None:
        """Ersetzt die Uhr - fuer Tests."""
        self._today = today
        self._show_range()
        self._refill()

    def set_anonymized(self, anonymized: bool, display: Callable[[list[Ticket]], list[Ticket]] | None = None) -> None:
        """Schaltet den Screenshot-Modus.

        Args:
            anonymized:
                Sperrt den Absprung nach Jira.
            display:
                Formt die gefilterten Tickets fuer die Anzeige um, None = unveraendert.
        """
        self._anonymized = anonymized
        self._display = display if anonymized else None
        self._refill()

    def set_team_ids(self, ids: frozenset[str]) -> None:
        """Merkt die Kennungen der Merkliste fuer die Menuepunkte."""
        self._team_ids = ids

    def set_report_available(self, available: bool) -> None:
        """Ob die Ticket-Analyse im Kontextmenue angeboten wird."""
        self._report_available = available

    def set_members(self, names: list[str]) -> None:
        """Fuellt die Personenauswahl, "Alle" bleibt vorn.

        Die bisherige Auswahl bleibt erhalten, solange es sie noch gibt.
        """
        previous = self.current_member()
        self._member_box.blockSignals(True)
        self._member_box.clear()
        self._member_box.addItem(ALL_LABEL, ALL_MEMBERS)
        for name in names:
            self._member_box.addItem(name, name)
        self._member_box.setCurrentIndex(max(0, self._member_box.findData(previous)))
        self._member_box.blockSignals(False)
        self._refill()

    # --- Auswahl ---------------------------------------------------------

    def current_member(self) -> str:
        """Name aus der Merkliste, leer fuer alle."""
        return str(self._member_box.currentData() or ALL_MEMBERS)

    def select_member(self, name: str) -> None:
        """Waehlt eine Person, leer = alle."""
        index = self._member_box.findData(name)
        if index >= 0:
            self._member_box.setCurrentIndex(index)

    def current_window(self) -> str:
        """Das Kuerzel des gewaehlten Zeitraums."""
        button = self._window_group.checkedButton()
        return button.text() if button is not None else DEFAULT_WINDOW

    def set_window(self, kind: str) -> None:
        """Setzt den Zeitraum ohne Signal - fuer den gemerkten Stand beim Start."""
        button = self._window_buttons.get(kind)
        if button is not None:
            button.setChecked(True)
            self._show_range()
            self._refill()

    def since(self) -> dt.date:
        """Erster Tag des gewaehlten Zeitraums."""
        return window_start(self._today(), WINDOWS[self.current_window()], self._is_workday)

    def since_longest(self) -> dt.date:
        """Erster Tag des laengsten Zeitraums - so weit reicht der Abruf."""
        return window_start(self._today(), max(WINDOWS.values()), self._is_workday)

    def _on_window_clicked(self, button: QToolButton) -> None:
        self._show_range()
        self._refill()
        self.window_changed.emit(button.text())

    # --- Anzeige ---------------------------------------------------------

    def _show_range(self) -> None:
        """Schreibt den Beginn des Zeitraums gross in die Kopfzeile."""
        start = self.since()
        self._range.setText(f"seit {_WEEKDAY_NAMES[start.weekday()]}, {start:%d.%m.%Y}")

    def show_message(self, text: str) -> None:
        """Zeigt einen Hinweis statt der Liste und leert die geladenen Tickets."""
        self._tickets = None
        self._placeholder.setText(text)
        self._pages.setCurrentWidget(self._placeholder)
        self._refill()

    def tickets(self) -> list[Ticket] | None:
        """Die geladene Liste, None vor dem ersten Abruf."""
        return self._tickets

    def set_tickets(self, tickets: list[Ticket]) -> None:
        """Uebernimmt eine frisch geladene Liste."""
        self._tickets = list(tickets)
        self._pages.setCurrentWidget(self._table)
        self._refill()

    def visible(self) -> list[Ticket]:
        """Die Tickets, die Person und Zeitraum gerade zeigen."""
        if self._tickets is None:
            return []
        return visible_tickets(self._tickets, self.current_member(), self.since())

    def _refill(self) -> None:
        """Fuellt die Tabelle neu und haelt die Auswahl, wenn es geht."""
        previous = self.current_key()
        tickets = self.visible()
        if self._display is not None:
            tickets = self._display(tickets)
        self._by_key = {ticket.key: ticket for ticket in tickets}
        today = self._today()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(tickets))
        for row, ticket in enumerate(tickets):
            created = ticket.created.timestamp() if ticket.created is not None else 0.0
            cells: dict[str, tuple[str, object]] = {
                "Ticket": (ticket.key, key_sort_value(ticket.key)),
                "Titel": (ticket.summary, ticket.summary.casefold()),
                "Typ": (ticket.issue_type, ticket.issue_type.casefold()),
                "Priorität": (ticket.priority, ticket.priority_rank),
                "Status": (ticket.status, ticket.status.casefold()),
                "Erstellt von": (ticket.reporter, ticket.reporter.casefold()),
                "Erstellt": (created_label(ticket.created, today), created),
                "Bearbeiter": (ticket.assignee or "-", ticket.assignee.casefold()),
            }
            for name, (text, sort_value) in cells.items():
                item = _SortItem(text)
                item.setData(_SORT_ROLE, sort_value)
                self._table.setItem(row, COL[name], item)
        # Ohne Ruecksetzen des Indikators sortiert setSortingEnabled sofort nach
        # Spalte 0 und wirft "neueste zuerst" weg.
        self._table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        for column in range(self._table.columnCount()):
            if column != _STRETCH:
                header.resizeSection(column, header.sectionSize(column) + 16)
        header.setSectionResizeMode(_STRETCH, QHeaderView.ResizeMode.Stretch)

        if self._tickets is None:
            self._count.setText("")
        elif tickets:
            self._count.setText(f"{len(tickets)} neue Tickets" if len(tickets) != 1 else "1 neues Ticket")
        else:
            self._count.setText("keine neuen Tickets")
        if self._tickets is not None and not tickets:
            self._placeholder.setText("Keine neuen Tickets in diesem Zeitraum.")
            self._pages.setCurrentWidget(self._placeholder)
        elif self._tickets is not None:
            self._pages.setCurrentWidget(self._table)
        self.count_changed.emit(len(tickets) if self._tickets is not None else -1)
        # Nur melden, wenn eine Auswahl wirklich weggefallen ist. set_members laeuft
        # schon beim Aufbau des Fensters, bevor die Vorschau steht.
        if previous is not None and not self.select_ticket(previous):
            self.ticket_selected.emit(None)

    # --- Vorschau und Auswahl --------------------------------------------

    def preview_host(self) -> QSplitter:
        """Der waagerechte Trenner, in den das Fenster die Ticket-Vorschau haengt."""
        return self._side

    def current_key(self) -> str | None:
        """Nummer des gewaehlten Tickets, None ohne Auswahl."""
        row = self._table.currentRow()
        item = self._table.item(row, COL["Ticket"]) if row >= 0 else None
        return item.text() if item is not None else None

    def current_ticket(self) -> Ticket | None:
        """Das gewaehlte Ticket, None ohne Auswahl."""
        key = self.current_key()
        return self._by_key.get(key) if key is not None else None

    def select_ticket(self, key: str) -> bool:
        """Waehlt ein Ticket der Tabelle ueber seine Nummer."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL["Ticket"])
            if item is not None and item.text() == key:
                self._table.setCurrentCell(row, COL["Ticket"])
                return True
        return False

    def _ticket_at(self, row: int) -> Ticket | None:
        item = self._table.item(row, COL["Ticket"]) if row >= 0 else None
        return self._by_key.get(item.text()) if item is not None else None

    def _on_click(self, row: int, _column: int) -> None:
        """Strg-Klick oeffnet das Ticket im Browser, wie in den Ticketlisten."""
        if QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            self._open(self._ticket_at(row))

    # --- Kontextmenue ----------------------------------------------------

    def build_menu(self, ticket: Ticket | None) -> QMenu:
        """Baut das Rechtsklick-Menue zu einer Zeile, wie in den Ticketlisten."""
        menu = QMenu(self)
        detail = QAction("Details anzeigen", menu)
        detail.setEnabled(ticket is not None)
        detail.triggered.connect(lambda _=False, t=ticket: self._emit_detail(t))
        menu.addAction(detail)

        open_action = QAction("Ticket im Browser öffnen", menu)
        open_action.setEnabled(ticket is not None and bool(ticket.url) and not self._anonymized)
        open_action.triggered.connect(lambda _=False, t=ticket: self._open(t))
        menu.addAction(open_action)

        report = QAction("Ticket-Analyse erstellen", menu)
        report.setEnabled(ticket is not None and bool(ticket.key) and self._report_available and not self._anonymized)
        report.triggered.connect(lambda _=False, t=ticket: self._emit_report(t))
        menu.addAction(report)

        menu.addSeparator()
        for action in person_actions(
            menu, ticket, self._anonymized, self._team_ids, self.person_requested.emit, self.team_add_requested.emit
        ):
            menu.addAction(action)

        menu.addSeparator()
        copy_action = QAction("Ticketnummer kopieren", menu)
        copy_action.setEnabled(ticket is not None)
        copy_action.triggered.connect(lambda _=False, t=ticket: self._copy_key(t))
        menu.addAction(copy_action)
        return menu

    def _on_context_menu(self, position: QPoint) -> None:
        row = self._table.rowAt(position.y())
        self.build_menu(self._ticket_at(row)).exec(self._table.viewport().mapToGlobal(position))

    def _emit_detail(self, ticket: Ticket | None) -> None:
        if ticket is not None:
            self.detail_requested.emit(ticket)

    def _emit_report(self, ticket: Ticket | None) -> None:
        if ticket is not None and ticket.key:
            self.report_requested.emit(ticket.key)

    def _open(self, ticket: Ticket | None) -> None:
        """Oeffnet ein Ticket im Standard-Browser - nicht im Screenshot-Modus."""
        if ticket is not None and ticket.url and not self._anonymized:
            webbrowser.open(ticket.url)

    @staticmethod
    def _copy_key(ticket: Ticket | None) -> None:
        if ticket is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(ticket.key)
