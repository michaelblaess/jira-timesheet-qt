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
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.ticket_board import Board, Marker, Role, Ticket
from jira_timesheet_qt.ui.cell_delegate import CellDelegate
from jira_timesheet_qt.ui.person_menu import person_actions

from .theme import Mode
from .ticket_board_model import SORT_ROLE, TICKET_ROLE, TicketBoardModel
from .ticket_charts import CHART_HEIGHT, ChartPanel

AnyIndex = QModelIndex | QPersistentModelIndex

# Daten des Gast-Eintrags im Auswahlfeld "Team-Mitglied". Kein Name: ein Gast
# kann heissen wie jemand auf der Merkliste.
GUEST_DATA = "\x00gast"

# Marker, die Handlungsbedarf bedeuten. Der Filter "nur mit Handlungsbedarf"
# blendet alles andere aus.
ACTIONABLE = (
    Marker.PILE_OF_SHAME,
    Marker.HANDBACK,
    Marker.ACCEPTANCE,
    Marker.BLOCKED,
    Marker.HIGH_PRIORITY,
)


# Wert des Bearbeiterfilters fuer die Tickets ohne Bearbeiter. Ein leerer
# String kann das nicht ausdruecken - der steht schon fuer "alle".
NO_ASSIGNEE = "\x00ohne-bearbeiter"


class TicketFilterProxy(QSortFilterProxyModel):
    """Filtert nach Suchtext, Status, Bearbeiter und Handlungsbedarf.

    Gruppenzeilen bestehen den Filter nie aus eigener Kraft - sie ueberleben
    ausschliesslich ueber die rekursive Pruefung, wenn ein Kind passt. Sonst
    stuenden leere Gruppen in der gefilterten Liste.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._needle = ""
        self._status = ""
        self._assignee = ""
        self._only_actionable = False
        self.setSortRole(SORT_ROLE)
        self.setRecursiveFilteringEnabled(True)

    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex) -> bool:  # noqa: N802 - Qt-Schreibweise
        """Vergleicht die Sortierwerte in Python.

        Das Modell liefert fuer Nummer, Typ und Bearbeiter Tupel. Qts eigener
        Vergleich kennt fuer ein Python-Tupel keine Ordnung und liess die
        Zeilen deshalb stehen, wo sie waren - aufgefallen an ABC-5979 hinter
        ABC-17741 (23.09.2026).
        """
        mine, theirs = left.data(SORT_ROLE), right.data(SORT_ROLE)
        try:
            return bool(mine < theirs)
        except TypeError:
            return super().lessThan(left, right)

    def set_needle(self, text: str) -> None:
        """Setzt den Suchtext fuer Ticketnummer und Titel."""
        self._needle = text.strip().casefold()
        self.invalidate()

    def set_status(self, status: str) -> None:
        """Beschraenkt auf einen Status, leer = alle."""
        self._status = status
        self.invalidate()

    def set_assignee(self, assignee: str) -> None:
        """Beschraenkt auf einen Bearbeiter.

        Args:
            assignee: Der Anzeigename, leer fuer alle, `NO_ASSIGNEE` fuer die
                Tickets, die niemandem zugewiesen sind.
        """
        self._assignee = assignee
        self.invalidate()

    def set_only_actionable(self, only: bool) -> None:
        """Blendet Tickets ohne Handlungsbedarf aus."""
        self._only_actionable = only
        self.invalidate()

    def _assignee_matches(self, ticket: Ticket) -> bool:
        """Prueft ein Ticket gegen den Bearbeiterfilter.

        Args:
            ticket: Das zu pruefende Ticket.

        Returns:
            True, wenn das Ticket sichtbar bleiben soll.
        """
        if not self._assignee:
            return True
        if self._assignee == NO_ASSIGNEE:
            return not ticket.assignee
        return ticket.assignee == self._assignee

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
        if not self._assignee_matches(ticket):
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

    # Meldet, dass eine andere Person gewaehlt wurde. Der Abruf gehoert nicht
    # in die Ansicht - sie sagt nur, WEN sie sehen will.
    member_changed = Signal(str)

    # Bittet das Fenster, die Tickets einer Person in "Mein Team" zu zeigen:
    # accountId und Anzeigename.
    person_requested = Signal(str, str)

    # Die voruebergehend gezeigte Person soll auf die Merkliste.
    guest_add_requested = Signal()

    # Eine Person aus dem Kontextmenue soll auf die Merkliste: accountId und Name.
    team_add_requested = Signal(str, str)

    # Die Auswahl hat gewechselt: das Ticket der Zeile, oder None auf einer
    # Gruppenzeile und ohne Auswahl. Fuer die Ticket-Vorschau.
    ticket_selected = Signal(object)

    def __init__(
        self,
        title: str,
        *,
        with_charts: bool = False,
        mode: Mode = Mode.DARK,
        with_members: bool = False,
        with_assignees: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Baut die Ansicht.

        Args:
            title:
                Ueberschrift der Ansicht.
            with_charts:
                Ob die Auswertung angezeigt wird. Sie rechnet ueber die
                eigenen Tickets (history_jql). Kennzahlen je Team-Mitglied
                liefert der Reiter Performance-Booster.
            mode:
                Helles oder dunkles Erscheinungsbild.
            with_members:
                Ob das Auswahlfeld fuer die Person entsteht. Es entsteht
                IMMER, wenn die Ansicht es braucht - auch bei leerer
                Merkliste. Ein Feld, das erst mit dem ersten Eintrag
                auftaucht, ist der Grund, warum in der Textual-Fassung
                gespeicherte Personen im Reiter nicht ankamen.
            with_assignees:
                Ob das Auswahlfeld fuer den Bearbeiter entsteht. Nur dort
                sinnvoll, wo Tickets mehrerer Personen zusammenstehen: in
                "Meine Tickets" ist der Bearbeiter immer derselbe, und in
                "Mein Team" waehlt schon das Feld darueber die Person aus.
            parent:
                Das Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._title = title
        self._with_members = with_members
        self._with_assignees = with_assignees
        self._members: list[str] = []
        # Name der voruebergehend gezeigten Person, leer ohne Gast.
        self._guest = ""
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
        # Im Screenshot-Modus sind die Ticketnummern erfunden. Ein Sprung
        # in den Browser oder eine Analyse liefe damit ins Leere.
        self._anonymized = False
        # Kennungen der Merkliste - wer darin steht, bekommt kein "hinzufuegen".
        self._team_ids: frozenset[str] = frozenset()
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

        if self._with_members:
            head.addWidget(QLabel("Team-Mitglied:"))
            self._member_box = QComboBox()
            self._member_box.setObjectName("BoardMemberFilter")
            self._member_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self._member_box.setMinimumContentsLength(18)
            self._member_box.currentIndexChanged.connect(self._on_member_changed)
            head.addWidget(self._member_box)
            # Nur sichtbar, solange ein Gast gewaehlt ist.
            self._add_guest = QPushButton("Zur Merkliste hinzufügen")
            self._add_guest.setObjectName("BoardAddGuest")
            self._add_guest.setToolTip('Die Person dauerhaft in die Merkliste von "Mein Team" aufnehmen')
            self._add_guest.clicked.connect(lambda _checked=False: self.guest_add_requested.emit())
            self._add_guest.setVisible(False)
            head.addWidget(self._add_guest)

        head.addWidget(QLabel("Status:"))
        self._status_box = QComboBox()
        self._status_box.setObjectName("BoardStatusFilter")
        # Statusnamen sind lang ("Freigabe Produktivsetzung"). Ohne das waechst
        # das Feld nicht mit und zeigt nur noch "IN A ...".
        self._status_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._status_box.setMinimumContentsLength(18)
        self._status_box.addItem("alle", "")
        self._status_box.currentIndexChanged.connect(self._on_status_changed)
        head.addWidget(self._status_box)

        if self._with_assignees:
            # Hinter dem Status: beide waehlen aus demselben Bestand aus, und
            # der Status ist der haeufiger benutzte von beiden.
            head.addWidget(QLabel("Bearbeiter:"))
            self._assignee_box = QComboBox()
            self._assignee_box.setObjectName("BoardAssigneeFilter")
            # Namen im Format "Nachname, Vorname" werden lang. Ohne das zeigt
            # das Feld nur noch den Anfang, wie beim Status daneben.
            self._assignee_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self._assignee_box.setMinimumContentsLength(18)
            self._assignee_box.addItem("alle", "")
            self._assignee_box.currentIndexChanged.connect(self._on_assignee_changed)
            head.addWidget(self._assignee_box)

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
        # Derselbe Delegate wie in der Liste, hier ohne Suchbegriff - er sorgt
        # allein fuer den Innenabstand. Ohne ihn stoesst die rechtsbuendige
        # Liegezeit unmittelbar an die Merkmale der Nachbarspalte.
        self._tree.setItemDelegate(CellDelegate(self._tree))
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.clicked.connect(self._on_click)
        selection = self._tree.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_current_changed)

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

        # Rechts daneben haengt das Fenster die Ticket-Vorschau ein. Es gibt
        # nur eine Vorschau, sie zieht mit dem Reiter um - der Platz dafuer
        # entsteht aber hier, damit die Ansicht selbst das Stapel-Element bleibt.
        self._side = QSplitter(Qt.Orientation.Horizontal)
        self._side.setObjectName("BoardPreviewSplitter")
        self._side.setChildrenCollapsible(False)
        outer.addWidget(self._side, 1)

        self._charts: ChartPanel | None = None
        if not self._with_charts:
            self._side.addWidget(self._pages)
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
        # Liste und Auswertung zusammen links, die Vorschau daneben ueber die volle Hoehe.
        self._side.addWidget(self._splitter)

    # --- Fuellen ---------------------------------------------------------

    @property
    def board(self) -> Board | None:
        """Das zuletzt uebernommene Ergebnis, oder None."""
        return self._board

    def set_board(self, board: Board | None) -> None:
        """Uebernimmt ein Ergebnis und baut die Anzeige neu auf.

        Das gewaehlte Ticket bleibt gewaehlt, solange es im neuen Ergebnis
        steht. Ist es verschwunden, meldet die Ansicht "keine Auswahl" - der
        Modell-Neuaufbau selbst sendet dafuer kein Signal, und die Vorschau
        zeigte sonst weiter das alte Ticket.
        """
        previous = self.current_ticket()
        self._board = board
        self._model.set_board(board)
        self._fill_status_filter(board)
        self._fill_assignee_filter(board)
        self._tree.expandAll()
        self._collapse_done()
        self._resize_columns()
        if board is not None and board.count == 0:
            self._show_placeholder("Keine Tickets gefunden.")
        else:
            self._pages.setCurrentWidget(self._tree)
        if previous is not None and not self.select_ticket(previous.key):
            self.ticket_selected.emit(None)

    def preview_host(self) -> QSplitter:
        """Der waagerechte Trenner, in den das Fenster die Ticket-Vorschau haengt."""
        return self._side

    def current_ticket(self) -> Ticket | None:
        """Das gewaehlte Ticket, oder None auf einer Gruppenzeile und ohne Auswahl."""
        return self._ticket_at(self._tree.currentIndex())

    def select_ticket(self, key: str) -> bool:
        """Waehlt ein Ticket der angezeigten Liste ueber seine Nummer.

        Returns:
            False, wenn es nicht angezeigt wird - auch wenn ein Filter es ausblendet.
        """
        for group_row in range(self._proxy.rowCount()):
            group = self._proxy.index(group_row, 0)
            for row in range(self._proxy.rowCount(group)):
                index = self._proxy.index(row, 0, group)
                ticket = self._ticket_at(index)
                if ticket is not None and ticket.key == key:
                    self._tree.setCurrentIndex(index)
                    return True
        return False

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Meldet das Ticket der neuen Zeile."""
        self.ticket_selected.emit(self._ticket_at(current))

    def _collapse_done(self) -> None:
        """Klappt die Gruppe "Abgeschlossen" zu.

        Dort ist nichts mehr zu tun. Aufgeklappt schiebt sie - je nach
        Instanz die groesste Gruppe - alles darueber aus dem Bild, und der
        erste Blick faellt auf Erledigtes statt auf Offenes.
        """
        board = self._board
        if board is None:
            return
        for row, group in enumerate(board.groups):
            if group.role is Role.DONE:
                self._tree.setExpanded(self._proxy.index(row, 0, QModelIndex()), False)

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

    def show_hint(self, text: str) -> None:
        """Ersetzt den Inhalt durch einen Hinweis.

        Anders als ``set_loading`` und ``set_failed`` verdraengt das auch ein
        bereits geladenes Ergebnis. Gedacht fuer den Fall, dass die Ansicht
        gar nichts zeigen KANN - etwa die Fremdsicht ohne gewaehlte Person,
        wo die alte Liste unter einem falschen Namen staende.

        Args:
            text:
                Der Hinweis.
        """
        self._board = None
        self._model.set_board(None)
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

    def set_members(self, names: list[str]) -> None:
        """Uebernimmt die Merkliste in das Auswahlfeld.

        Args:
            names:
                Die Anzeigenamen aus den Einstellungen, bereits sortiert.
        """
        if not self._with_members:
            return
        guest_was_selected = self.guest_selected()
        previous = self.current_member()
        self._members = list(names)
        self._member_box.blockSignals(True)
        self._member_box.clear()
        for name in self._members:
            self._member_box.addItem(name, name)
        if self._guest:
            # Hinten und kursiv, mit Zusatz: der Gast soll nicht wie ein
            # Eintrag der Merkliste aussehen.
            self._member_box.addItem(f"{self._guest} (nicht auf der Merkliste)", GUEST_DATA)
            font = self._member_box.font()
            font.setItalic(True)
            self._member_box.setItemData(self._member_box.count() - 1, font, Qt.ItemDataRole.FontRole)
        if guest_was_selected and self._guest:
            self._member_box.setCurrentIndex(self._member_box.count() - 1)
        elif previous in self._members:
            self._member_box.setCurrentIndex(self._members.index(previous))
        self._member_box.blockSignals(False)
        self._member_box.setEnabled(self._member_box.count() > 0)
        self._add_guest.setVisible(self.guest_selected())

    def current_member(self) -> str:
        """Der Name der gewaehlten Person aus der Merkliste, leer ohne Auswahl oder bei einem Gast."""
        if not self._with_members:
            return ""
        data = self._member_box.currentData()
        return str(data) if data and data != GUEST_DATA else ""

    def guest_selected(self) -> bool:
        """Ob gerade die voruebergehend gezeigte Person gewaehlt ist."""
        return self._with_members and bool(self._guest) and self._member_box.currentData() == GUEST_DATA

    def guest_name(self) -> str:
        """Name des Gasts, leer ohne Gast."""
        return self._guest

    def show_guest(self, name: str) -> None:
        """Nimmt eine Person voruebergehend in die Auswahl auf und waehlt sie, ohne Signal.

        Ohne Signal, weil das Fenster den Abruf selbst anstoesst - sonst liefe er doppelt.
        """
        if not self._with_members:
            return
        self._guest = name
        self.set_members(self._members)
        self._member_box.blockSignals(True)
        self._member_box.setCurrentIndex(self._member_box.findData(GUEST_DATA))
        self._member_box.blockSignals(False)
        self._add_guest.setVisible(True)

    def clear_guest(self) -> None:
        """Entfernt den Gast aus der Auswahl."""
        if not self._with_members or not self._guest:
            return
        self._guest = ""
        self.set_members(self._members)

    def select_member(self, name: str) -> bool:
        """Waehlt eine Person der Merkliste, ohne Signal.

        Returns:
            False, wenn der Name nicht in der Auswahl steht.
        """
        if not self._with_members or name not in self._members:
            return False
        self._member_box.blockSignals(True)
        self._member_box.setCurrentIndex(self._members.index(name))
        self._member_box.blockSignals(False)
        self._add_guest.setVisible(False)
        return True

    def _on_member_changed(self, _index: int) -> None:
        """Meldet die neue Person nach oben."""
        self._add_guest.setVisible(self.guest_selected())
        name = self.current_member()
        if name:
            self.member_changed.emit(name)
        elif self.guest_selected():
            self.member_changed.emit(self._guest)

    def set_report_available(self, available: bool) -> None:
        """Schaltet den Menuepunkt fuer die Ticket-Analyse frei."""
        self._report_available = available

    def set_anonymized(self, anonymized: bool) -> None:
        """Merkt den Screenshot-Modus fuer die Menuepunkte."""
        self._anonymized = anonymized

    def set_team_ids(self, ids: frozenset[str]) -> None:
        """Merkt die Kennungen der Merkliste fuer die Menuepunkte."""
        self._team_ids = ids

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

    def _fill_assignee_filter(self, board: Board | None) -> None:
        """Fuellt die Bearbeiterauswahl aus den tatsaechlich vorkommenden Namen.

        Wie beim Status kommen die Namen aus dem Ergebnis. Dazu ein Eintrag
        fuer die Tickets ohne Bearbeiter - genau die sind in "Meine
        Aktivitaeten" oft das Interessante, und ueber das Suchfeld sind sie
        gar nicht zu treffen. Der Eintrag erscheint nur, wenn es solche
        Tickets gibt: ein Filter, der garantiert nichts findet, hilft niemandem.

        Args:
            board: Das uebernommene Ergebnis, oder None.
        """
        if not self._with_assignees:
            return
        previous = self._assignee_box.currentData()
        self._assignee_box.blockSignals(True)
        self._assignee_box.clear()
        self._assignee_box.addItem("alle", "")
        if board is not None:
            for name in sorted({t.assignee for t in board.tickets if t.assignee}):
                self._assignee_box.addItem(name, name)
            if any(not t.assignee for t in board.tickets):
                self._assignee_box.addItem("ohne Bearbeiter", NO_ASSIGNEE)
        position = self._assignee_box.findData(previous)
        self._assignee_box.setCurrentIndex(max(0, position))
        self._assignee_box.blockSignals(False)
        self._proxy.set_assignee(str(self._assignee_box.currentData() or ""))

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

    def _on_assignee_changed(self) -> None:
        self._proxy.set_assignee(str(self._assignee_box.currentData() or ""))

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
        open_action.setEnabled(ticket is not None and bool(ticket.url) and not self._anonymized)
        open_action.triggered.connect(lambda _=False, t=ticket: self._open(t))
        menu.addAction(open_action)

        report = QAction("Ticket-Analyse erstellen", menu)
        report.setEnabled(ticket is not None and bool(ticket.key) and self._report_available and not self._anonymized)
        report.triggered.connect(lambda _=False, t=ticket: self._emit_report(t))
        menu.addAction(report)

        menu.addSeparator()

        for action in self._person_actions(menu, ticket):
            menu.addAction(action)

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

    def _person_actions(self, menu: QMenu, ticket: Ticket | None) -> list[QAction]:
        """Eintraege "Tickets von ... anzeigen" fuer Bearbeiter und Autor.

        Je Person ein Eintrag, dieselbe Person nur einmal. Ohne Person mit
        brauchbarer Kennung bleibt ein ausgegrauter Eintrag stehen - so ist das
        Menue an jeder Zeile gleich aufgebaut. Im Screenshot-Modus gesperrt:
        die Namen sind dort erfunden.

        Args:
            menu:
                Das Menue, dem die Eintraege gehoeren.
            ticket:
                Das Ticket der Zeile, oder None auf einer Gruppenzeile.

        Returns:
            Die Eintraege in der Reihenfolge Bearbeiter, Autor.
        """
        return person_actions(
            menu,
            ticket,
            self._anonymized,
            self._team_ids,
            self.person_requested.emit,
            self.team_add_requested.emit,
        )

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
