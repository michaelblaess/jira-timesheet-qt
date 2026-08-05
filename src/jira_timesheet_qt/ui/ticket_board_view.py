"""Ansicht einer Ticket-Liste: Kopfleiste, Filter, Baum.

Die Daten kommen erst auf Zuruf. Das ist keine Frage der Laufzeit - die
Abfragen sind schnell - sondern der Kontrolle darueber, wann Last auf dem
Server entsteht.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.ticket_board import Board, Marker, Ticket

from .ticket_board_model import SORT_ROLE, TICKET_ROLE, TicketBoardModel

AnyIndex = QModelIndex | QPersistentModelIndex

# Marker, die Handlungsbedarf bedeuten. Der Filter "nur mit Handlungsbedarf"
# blendet alles andere aus.
ACTIONABLE = (
    Marker.PILE_OF_SHAME,
    Marker.HANDBACK,
    Marker.ACCEPTANCE,
    Marker.BLOCKED,
    Marker.HIGH_PRIORITY,
)


class TicketFilterProxy(QSortFilterProxyModel):
    """Filtert nach Suchtext, Status und Handlungsbedarf.

    Gruppenzeilen bestehen den Filter nie aus eigener Kraft - sie ueberleben
    ausschliesslich ueber die rekursive Pruefung, wenn ein Kind passt. Sonst
    stuenden leere Gruppen in der gefilterten Liste.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._needle = ""
        self._status = ""
        self._only_actionable = False
        self.setSortRole(SORT_ROLE)
        self.setRecursiveFilteringEnabled(True)

    def set_needle(self, text: str) -> None:
        """Setzt den Suchtext fuer Ticketnummer und Titel."""
        self._needle = text.strip().casefold()
        self.invalidate()

    def set_status(self, status: str) -> None:
        """Beschraenkt auf einen Status, leer = alle."""
        self._status = status
        self.invalidate()

    def set_only_actionable(self, only: bool) -> None:
        """Blendet Tickets ohne Handlungsbedarf aus."""
        self._only_actionable = only
        self.invalidate()

    def filterAcceptsRow(  # noqa: N802 - Qt-Schreibweise
        self, source_row: int, source_parent: AnyIndex
    ) -> bool:
        """Entscheidet ueber eine einzelne Zeile."""
        model = self.sourceModel()
        if not isinstance(model, TicketBoardModel):
            return True
        index = model.index(source_row, 0, source_parent)
        ticket = index.data(TICKET_ROLE)
        if not isinstance(ticket, Ticket):
            # Gruppenzeile: nur ueber die rekursive Pruefung sichtbar.
            return False
        if self._status and ticket.status != self._status:
            return False
        if self._only_actionable and not any(ticket.has(m) for m in ACTIONABLE):
            return False
        if self._needle:
            haystack = f"{ticket.key} {ticket.summary}".casefold()
            if self._needle not in haystack:
                return False
        return True


class TicketBoardView(QWidget):
    """Eine der beiden Ticket-Ansichten."""

    reload_requested = Signal()
    detail_requested = Signal(str)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._board: Board | None = None
        self._model = TicketBoardModel(self)
        self._proxy = TicketFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._build_ui()

    # --- Aufbau ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)

        self._reload = QPushButton("Laden")
        self._reload.setObjectName("BoardReload")
        self._reload.clicked.connect(self.reload_requested.emit)
        head.addWidget(self._reload)

        head.addWidget(QLabel("Status:"))
        self._status_box = QComboBox()
        self._status_box.setObjectName("BoardStatusFilter")
        self._status_box.addItem("alle", "")
        self._status_box.currentIndexChanged.connect(self._on_status_changed)
        head.addWidget(self._status_box)

        self._actionable = QCheckBox("nur mit Handlungsbedarf")
        self._actionable.toggled.connect(self._proxy.set_only_actionable)
        head.addWidget(self._actionable)

        head.addStretch(1)

        self._search = QLineEdit()
        self._search.setObjectName("BoardSearch")
        self._search.setPlaceholderText("Ticketnummer oder Titel ...")
        self._search.setClearButtonEnabled(True)
        self._search.setMaximumWidth(280)
        self._search.textChanged.connect(self._proxy.set_needle)
        head.addWidget(self._search)

        outer.addLayout(head)

        self._tree = QTreeView()
        self._tree.setObjectName("BoardTree")
        self._tree.setModel(self._proxy)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setSortingEnabled(True)
        # Kopfzeilen-Klick sortiert, aber erst auf Zuruf. Ohne diese Zeile
        # sortiert Qt sofort nach Spalte 0 und wirft damit die Reihenfolge
        # weg, die der Kern bewusst gesetzt hat (im Backlog etwa Fehler
        # zuerst, sonst das Aelteste oben).
        self._tree.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.clicked.connect(self._on_click)
        outer.addWidget(self._tree, 1)

        self._status_line = QLabel("Noch nichts geladen.")
        self._status_line.setObjectName("BoardStatus")
        outer.addWidget(self._status_line)

    # --- Fuellen ---------------------------------------------------------

    def set_board(self, board: Board | None) -> None:
        """Uebernimmt ein Ergebnis und baut die Anzeige neu auf."""
        self._board = board
        self._model.set_board(board)
        self._fill_status_filter(board)
        self._tree.expandAll()
        self._resize_columns()
        self._reload.setText("Aktualisieren")
        self._update_status_line()

    def set_busy(self, busy: bool, text: str = "") -> None:
        """Sperrt den Ladeknopf waehrend eines laufenden Abrufs."""
        self._reload.setEnabled(not busy)
        if text:
            self._status_line.setText(text)
        elif not busy:
            self._update_status_line()

    def set_message(self, text: str) -> None:
        """Zeigt eine Meldung in der Fusszeile der Ansicht."""
        self._status_line.setText(text)

    def _fill_status_filter(self, board: Board | None) -> None:
        """Fuellt die Statusauswahl aus den tatsaechlich vorkommenden Werten.

        Aus den vorkommenden, nicht aus einer festen Liste: eine Instanz kann
        beliebig viele Status fuehren, und eine Auswahl voller Eintraege ohne
        Treffer hilft niemandem.
        """
        previous = self._status_box.currentData()
        self._status_box.blockSignals(True)
        self._status_box.clear()
        self._status_box.addItem("alle", "")
        if board is not None:
            for status in sorted({t.status for t in board.tickets if t.status}):
                self._status_box.addItem(status, status)
        position = self._status_box.findData(previous)
        self._status_box.setCurrentIndex(max(0, position))
        self._status_box.blockSignals(False)
        self._proxy.set_status(str(self._status_box.currentData() or ""))

    def _resize_columns(self) -> None:
        """Passt die Spaltenbreiten an, Titel bekommt den Rest."""
        header = self._tree.header()
        for column in range(self._model.columnCount() - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self._tree.resizeColumnToContents(column)
        header.setStretchLastSection(True)

    def _update_status_line(self) -> None:
        """Schreibt die Kennzahlen unter die Liste."""
        board = self._board
        if board is None:
            self._status_line.setText("Noch nichts geladen.")
            return
        shame = len(board.with_marker(Marker.PILE_OF_SHAME))
        parts = [f"{board.count} Tickets", f"{shame} im Pile of Shame"]
        if board.unknown_status:
            parts.append("nicht zugeordnet: " + ", ".join(board.unknown_status))
        self._status_line.setText(" · ".join(parts))

    # --- Bedienung -------------------------------------------------------

    def _on_status_changed(self) -> None:
        self._proxy.set_status(str(self._status_box.currentData() or ""))

    def _ticket_at(self, index: AnyIndex) -> Ticket | None:
        """Ticket einer Zeile der ANGEZEIGTEN Liste.

        Der Index muss ueber das Proxy auf die Quelle gedreht werden - sonst
        trifft man bei sortierter oder gefilterter Liste die falsche Zeile.
        """
        if not index.isValid():
            return None
        ticket = self._proxy.mapToSource(index).data(TICKET_ROLE)
        return ticket if isinstance(ticket, Ticket) else None

    def _on_click(self, index: QModelIndex) -> None:
        """Strg-Klick oeffnet das Ticket im Browser."""
        if QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            self._open(self._ticket_at(index))

    def _on_double_click(self, index: QModelIndex) -> None:
        """Doppelklick auf eine Gruppenzeile klappt sie zu oder auf."""
        if self._ticket_at(index) is None:
            self._tree.setExpanded(index, not self._tree.isExpanded(index))

    def _on_context_menu(self, position: QPoint) -> None:
        """Baut das Kontextmenue zur geklickten Zeile.

        Args:
            position:
                Klickpunkt, bereits in Koordinaten des Anzeigebereichs.
        """
        index = self._tree.indexAt(position)
        ticket = self._ticket_at(index)
        menu = QMenu(self)

        open_action = QAction("Im Browser öffnen", menu)
        open_action.setEnabled(ticket is not None and bool(ticket.url))
        open_action.triggered.connect(lambda _=False, t=ticket: self._open(t))
        menu.addAction(open_action)

        copy_action = QAction("Ticketnummer kopieren", menu)
        copy_action.setEnabled(ticket is not None)
        copy_action.triggered.connect(lambda _=False, t=ticket: self._copy_key(t))
        menu.addAction(copy_action)

        menu.addSeparator()
        expand = QAction("Alles aufklappen", menu)
        expand.triggered.connect(self._tree.expandAll)
        menu.addAction(expand)
        collapse = QAction("Alles einklappen", menu)
        collapse.triggered.connect(self._tree.collapseAll)
        menu.addAction(collapse)

        viewport = self._tree.viewport()
        if viewport is not None:
            menu.exec(viewport.mapToGlobal(position))

    @staticmethod
    def _open(ticket: Ticket | None) -> None:
        """Oeffnet ein Ticket im Standard-Browser."""
        if ticket is not None and ticket.url:
            webbrowser.open(ticket.url)

    @staticmethod
    def _copy_key(ticket: Ticket | None) -> None:
        """Legt die Ticketnummer in die Zwischenablage."""
        if ticket is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(ticket.key)
