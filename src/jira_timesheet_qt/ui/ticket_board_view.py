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
    QMenu,
    QSplitter,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.ticket_board import Board, Marker, Ticket

from .theme import Mode
from .ticket_board_model import SORT_ROLE, TICKET_ROLE, TicketBoardModel
from .ticket_charts import CHART_HEIGHT, ChartPanel

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

    # Traegt das Ticket-Objekt, nicht nur die Nummer: das Fenster soll die
    # Felder anzeigen koennen, ohne sie erneut abzurufen.
    detail_requested = Signal(object)
    report_requested = Signal(str)

    def __init__(
        self,
        title: str,
        *,
        with_charts: bool = False,
        mode: Mode = Mode.DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        # Die Auswertung zeigt den eigenen Durchsatz. Bei fremden Tickets
        # waere sie eine Zahl ueber jemand anderen - deshalb nur dort, wo
        # es die eigenen sind.
        self._with_charts = with_charts
        self._mode = mode
        self._board: Board | None = None
        # Die Analyse braucht Zugangsdaten. Ohne sie bleibt der Eintrag
        # sichtbar, aber ausgegraut - so bleibt das Menue an jeder Zeile
        # gleich aufgebaut.
        self._report_available = False
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

        # Waehrend des Abrufs steht hier ein Hinweis statt einer leeren
        # Tabelle. Ein Abruf kann eine Minute dauern, und eine weisse Flaeche
        # ohne jedes Lebenszeichen sieht aus wie ein Absturz.
        self._placeholder = QLabel("Noch nichts geladen.")
        self._placeholder.setObjectName("BoardPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._placeholder)
        self._pages.addWidget(self._tree)

        self._charts: ChartPanel | None = None
        if not self._with_charts:
            outer.addWidget(self._pages, 1)
            return

        # Liste oben, Auswertung unten, dazwischen ein greifbarer Trenner.
        # Die Hoehe bestimmt der Anwender - ein Einklappknopf waere daneben
        # ein zweites Bedienelement fuer dieselbe Sache.
        self._charts = ChartPanel(self._mode)
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setObjectName("BoardSplitter")
        self._splitter.setHandleWidth(7)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self._pages)
        self._splitter.addWidget(self._charts)
        # Die Liste bekommt beim Vergroessern des Fensters den Platz, die
        # Auswertung behaelt ihre Hoehe.
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([600, CHART_HEIGHT])
        outer.addWidget(self._splitter, 1)

    # --- Fuellen ---------------------------------------------------------

    @property
    def board(self) -> Board | None:
        """Das zuletzt uebernommene Ergebnis, oder None."""
        return self._board

    def set_board(self, board: Board | None) -> None:
        """Uebernimmt ein Ergebnis und baut die Anzeige neu auf."""
        self._board = board
        self._model.set_board(board)
        self._fill_status_filter(board)
        self._tree.expandAll()
        self._resize_columns()
        if board is not None and board.count == 0:
            self._show_placeholder("Keine Tickets gefunden.")
        else:
            self._pages.setCurrentWidget(self._tree)

    def set_statistics(self, stats: object) -> None:
        """Reicht die ausgewerteten Zahlen an die Diagramme weiter."""
        if self._charts is not None:
            self._charts.set_statistics(stats)  # type: ignore[arg-type]

    def splitter_state(self) -> bytes:
        """Zustand des Trenners fuer die dauerhafte Ablage."""
        if self._charts is None:
            return b""
        # .data() ist als bytes-artig typisiert - fuer die Ablage brauchen wir
        # echte bytes.
        return bytes(self._splitter.saveState().data())

    def restore_splitter_state(self, state: bytes) -> None:
        """Stellt einen gemerkten Trenner-Zustand wieder her."""
        if self._charts is not None and state:
            self._splitter.restoreState(state)

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        if self._charts is not None:
            self._charts.apply_mode(mode)

    def set_loading(self, text: str = "Tickets werden geladen ...") -> None:
        """Zeigt waehrend des Abrufs einen Hinweis statt einer leeren Tabelle.

        Args:
            text:
                Der anzuzeigende Hinweis.
        """
        # Ein bereits geladenes Ergebnis stehen lassen: beim Aktualisieren
        # ist die alte Liste besser als eine leere Flaeche.
        if self._board is None:
            self._show_placeholder(text)

    def set_failed(self, text: str) -> None:
        """Zeigt eine Fehlermeldung, wenn noch nichts geladen ist."""
        if self._board is None:
            self._show_placeholder(text)

    def _show_placeholder(self, text: str) -> None:
        """Blendet die Hinweisflaeche mit dem gegebenen Text ein."""
        self._placeholder.setText(text)
        self._pages.setCurrentWidget(self._placeholder)

    def set_search(self, text: str) -> None:
        """Uebernimmt den Suchbegriff der Werkzeugleiste.

        Die Ansicht hat bewusst KEIN eigenes Suchfeld: zwei Felder
        nebeneinander, die dasselbe tun, sind eine Fehlerquelle und kein
        Komfort.

        Args:
            text:
                Der Suchbegriff.
        """
        self._proxy.set_needle(text)
        if text:
            self._tree.expandAll()

    def set_report_available(self, available: bool) -> None:
        """Schaltet den Menuepunkt fuer die Ticket-Analyse frei."""
        self._report_available = available

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
        """Doppelklick: Details eines Tickets, Umklappen einer Gruppe."""
        ticket = self._ticket_at(index)
        if ticket is None:
            self._tree.setExpanded(index, not self._tree.isExpanded(index))
            return
        self.detail_requested.emit(ticket)

    def build_menu(self, ticket: Ticket | None) -> QMenu:
        """Baut das Rechtsklick-Menue zu einer Zeile.

        Bewusst getrennt vom Anzeigen: ein exec() laesst sich nicht pruefen,
        ein zurueckgegebenes Menue schon. Dieselbe Aufteilung nutzt das
        Hauptfenster fuer die Stundenliste.

        Args:
            ticket:
                Das Ticket der Zeile, oder None auf einer Gruppenzeile.

        Returns:
            Das fertige Menue. Eintraege ohne Ziel bleiben sichtbar, aber
            ausgegraut - so ist das Menue ueberall gleich aufgebaut.
        """
        menu = QMenu(self)

        detail = QAction("Details anzeigen", menu)
        detail.setEnabled(ticket is not None)
        detail.triggered.connect(lambda _=False, t=ticket: self._emit_detail(t))
        menu.addAction(detail)

        open_action = QAction("Ticket im Browser öffnen", menu)
        open_action.setEnabled(ticket is not None and bool(ticket.url))
        open_action.triggered.connect(lambda _=False, t=ticket: self._open(t))
        menu.addAction(open_action)

        report = QAction("Ticket-Analyse erstellen", menu)
        report.setEnabled(ticket is not None and bool(ticket.key) and self._report_available)
        report.triggered.connect(lambda _=False, t=ticket: self._emit_report(t))
        menu.addAction(report)

        menu.addSeparator()

        copy_action = QAction("Ticketnummer kopieren", menu)
        copy_action.setEnabled(ticket is not None)
        copy_action.triggered.connect(lambda _=False, t=ticket: self._copy_key(t))
        menu.addAction(copy_action)

        menu.addSeparator()

        expand = QAction("Alles aufklappen", menu)
        expand.triggered.connect(self._tree.expandAll)
        menu.addAction(expand)
        collapse = QAction("Alles zuklappen", menu)
        collapse.triggered.connect(self._tree.collapseAll)
        menu.addAction(collapse)
        return menu

    def _on_context_menu(self, position: QPoint) -> None:
        """Zeigt das Menue an der Mausposition.

        Args:
            position:
                Klickpunkt, bereits in Koordinaten des Anzeigebereichs.
        """
        menu = self.build_menu(self._ticket_at(self._tree.indexAt(position)))
        viewport = self._tree.viewport()
        if viewport is not None:
            menu.exec(viewport.mapToGlobal(position))

    def _emit_detail(self, ticket: Ticket | None) -> None:
        """Bittet das Fenster, die Einzelheiten anzuzeigen."""
        if ticket is not None:
            self.detail_requested.emit(ticket)

    def _emit_report(self, ticket: Ticket | None) -> None:
        """Bittet das Fenster, die Ticket-Analyse zu erzeugen."""
        if ticket is not None and ticket.key:
            self.report_requested.emit(ticket.key)

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
