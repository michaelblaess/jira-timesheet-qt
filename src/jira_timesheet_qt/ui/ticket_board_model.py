"""Baum-Modell der Ticket-Ansichten: Gruppen als Eltern, Tickets als Kinder.

Qt bringt kein Gruppierungs-Grid mit - der Baum ist Handarbeit, aber
ueberschaubar, weil es genau zwei Ebenen sind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from jira_timesheet_qt.services.ticket_board import Board, Group, Marker, Role, Ticket

# Qt reicht je nach Aufrufweg den einen oder den anderen Indextyp herein.
AnyIndex = QModelIndex | QPersistentModelIndex

# Eigene Rollen: das Ticket-Objekt und der Sortierwert je Spalte.
TICKET_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2

# Ueberschriften der Gruppen. Bewusst als Handlungsanweisung formuliert -
# "Rueckläufer" allein sagt nicht, was zu tun ist.
GROUP_TITLES: dict[Role, str] = {
    Role.ACTIVE: "Ich bin dran",
    Role.ACCEPTANCE: "Andere sind dran - nachhaken",
    Role.BACKLOG: "Backlog - zum Ziehen",
    Role.HANDBACK: "Rückläufer - zurückgeben, nicht bearbeiten",
    Role.CLOSING: "Abschluss offen",
    Role.UNKNOWN: "Status nicht zugeordnet",
}

# Kurzzeichen der Marker fuer die Spalte. Kurz, damit die Spalte schmal
# bleibt - die ausfuehrliche Erklaerung liefert der Hinweis unter der Maus.
MARKER_LABELS: dict[Marker, str] = {
    Marker.PILE_OF_SHAME: "Pile of Shame",
    Marker.HANDBACK: "Rückgabe",
    Marker.STALE: "verwaist",
    Marker.HIGH_PRIORITY: "Priorität",
    Marker.ACCEPTANCE: "nachhaken",
    Marker.BLOCKED: "blockiert",
}

MARKER_HINTS: dict[Marker, str] = {
    Marker.PILE_OF_SHAME: (
        "Der Status behauptet Aktivität, aber es gibt seit der Schwelle weder "
        "eine Änderung noch eine gebuchte Stunde."
    ),
    Marker.HANDBACK: "Ausgeliefert, fremder Autor - gehört zurückgegeben, nicht bearbeitet.",
    Marker.STALE: "Seit sehr langer Zeit unverändert.",
    Marker.HIGH_PRIORITY: "Priorität in der oberen Gruppe der Rangfolge.",
    Marker.ACCEPTANCE: "Wartet auf Freigabe durch jemand anderen.",
    Marker.BLOCKED: "Ein Vorgänger ist noch offen.",
}

COLUMNS: tuple[str, ...] = (
    "Ticket",
    "Status",
    "Priorität",
    "Art",
    "Liegezeit",
    "Merkmale",
    "Titel",
)


@dataclass
class _Node:
    """Ein Knoten des Baums. Gruppen haben Kinder, Tickets nicht."""

    row: int = 0
    group: Group | None = None
    ticket: Ticket | None = None
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)


class TicketBoardModel(QAbstractItemModel):
    """Stellt ein Board als zweistufigen Baum dar."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = _Node()
        self._board: Board | None = None

    # --- Fuellen ---------------------------------------------------------

    def set_board(self, board: Board | None) -> None:
        """Uebernimmt ein neues Board und baut den Baum neu auf."""
        self.beginResetModel()
        self._board = board
        self._root = _Node()
        if board is not None:
            for group_row, group in enumerate(board.groups):
                node = _Node(row=group_row, group=group, parent=self._root)
                for ticket_row, ticket in enumerate(group.tickets):
                    node.children.append(
                        _Node(row=ticket_row, ticket=ticket, parent=node)
                    )
                self._root.children.append(node)
        self.endResetModel()

    def ticket_at(self, index: AnyIndex) -> Ticket | None:
        """Liefert das Ticket einer Zeile, oder None bei einer Gruppenzeile."""
        if not index.isValid():
            return None
        node = index.internalPointer()
        return node.ticket if isinstance(node, _Node) else None

    # --- Baumgeruest -----------------------------------------------------

    def index(self, row: int, column: int, parent: AnyIndex = QModelIndex()) -> QModelIndex:  # noqa: B008
        """Erzeugt den Index einer Zeile unterhalb von parent."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = self._node_of(parent)
        if row >= len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    # QObject.parent() ist ueberladen (ohne Argument vs. mit Index) - ein
    # Override kollidiert zwangslaeufig mit einer der beiden Signaturen.
    def parent(self, index: AnyIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]  # noqa: B008
        """Liefert den Elternindex einer Zeile."""
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if not isinstance(node, _Node) or node.parent is None:
            return QModelIndex()
        parent = node.parent
        if parent is self._root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def rowCount(self, parent: AnyIndex = QModelIndex()) -> int:  # noqa: N802,B008
        """Anzahl der Zeilen unterhalb von parent."""
        # Qt-Konvention: Kinder haengen ausschliesslich an Spalte 0.
        if parent.isValid() and parent.column() > 0:
            return 0
        return len(self._node_of(parent).children)

    def columnCount(self, parent: AnyIndex = QModelIndex()) -> int:  # noqa: N802,B008
        """Anzahl der Spalten."""
        return len(COLUMNS)

    def _node_of(self, index: AnyIndex) -> _Node:
        """Knoten zu einem Index, Wurzel bei einem ungueltigen Index."""
        if index.isValid():
            node = index.internalPointer()
            if isinstance(node, _Node):
                return node
        return self._root

    # --- Inhalt ----------------------------------------------------------

    def headerData(  # noqa: N802 - Qt-Schreibweise
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Spaltenueberschriften."""
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section] if 0 <= section < len(COLUMNS) else ""
        return None

    def data(  # noqa: C901 - eine Rolle je Zweig, Aufteilen wuerde es zerreissen
        self,
        index: AnyIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Liefert den Inhalt einer Zelle."""
        if not index.isValid():
            return None
        node = index.internalPointer()
        if not isinstance(node, _Node):
            return None

        if node.group is not None:
            return self._group_data(node.group, index.column(), role)
        if node.ticket is not None:
            return self._ticket_data(node.ticket, index.column(), role)
        return None

    def _group_data(self, group: Group, column: int, role: int) -> Any:
        """Inhalt einer Gruppenzeile."""
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return f"{GROUP_TITLES.get(group.role, group.role.value)}  ({group.count})"
            return ""
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            return font
        if role == SORT_ROLE:
            # Gruppen behalten ihre Reihenfolge, egal wonach sortiert wird -
            # sonst springt beim Sortieren die ganze Gliederung.
            return group.role.value
        return None

    def _ticket_data(self, ticket: Ticket, column: int, role: int) -> Any:
        """Inhalt einer Ticketzeile."""
        if role == TICKET_ROLE:
            return ticket
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(ticket, column)
        if role == SORT_ROLE:
            return self._sort_key(ticket, column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 4:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and ticket.has(Marker.PILE_OF_SHAME):
            return QColor("#c0392b")
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(ticket)
        return None

    @staticmethod
    def _display(ticket: Ticket, column: int) -> str:
        """Anzeigetext einer Zelle."""
        if column == 0:
            return ticket.key
        if column == 1:
            return ticket.status
        if column == 2:
            return ticket.priority
        if column == 3:
            return ticket.issue_type
        if column == 4:
            return f"{ticket.idle_workdays:.0f} At"
        if column == 5:
            return ", ".join(MARKER_LABELS.get(m, m.value) for m in ticket.markers)
        if column == 6:
            return ticket.summary
        return ""

    @staticmethod
    def _sort_key(ticket: Ticket, column: int) -> Any:
        """Sortierwert einer Zelle - immer der Rohwert, nie die Anzeige.

        Eine Liegezeit als "5 At" sortiert als Zeichenkette falsch, und eine
        Prioritaet erst recht: "Kritisch" stuende hinter "Low".
        """
        if column == 2:
            return ticket.priority_rank
        if column == 3:
            return (not ticket.is_bug, ticket.issue_type)
        if column == 4:
            return ticket.idle_workdays
        if column == 5:
            return -len(ticket.markers)
        if column == 6:
            return ticket.summary.casefold()
        if column == 1:
            return ticket.status.casefold()
        return ticket.key

    @staticmethod
    def _tooltip(ticket: Ticket) -> str:
        """Erklaerender Hinweis unter der Maus."""
        lines = [f"{ticket.key} - {ticket.summary}", ""]
        lines.append(f"Status: {ticket.status}")
        lines.append(f"Autor: {ticket.reporter or '-'}")
        lines.append(
            f"Liegezeit: {ticket.idle_workdays:.0f} Arbeitstage "
            f"({ticket.idle_days} Kalendertage)"
        )
        if ticket.has_worklogs is not None:
            if ticket.booking_workdays is None:
                lines.append("Buchungen: keine")
            else:
                lines.append(f"Letzte Buchung: vor {ticket.booking_workdays:.0f} Arbeitstagen")
        for marker in ticket.markers:
            lines.append("")
            lines.append(f"{MARKER_LABELS.get(marker, marker.value)}: {MARKER_HINTS.get(marker, '')}")
        return "\n".join(lines)
