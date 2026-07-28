"""Baum-Modell fuer die nach Tag gruppierte Ansicht des Stundenzettels.

Zwei Ebenen: Tages-Gruppen als Elternzeilen (mit Tagessumme in der
Stunden-Spalte), die einzelnen Eintraege als Kinder. Ein QTreeView klappt die
Gruppen auf und zu. Sortieren/Filtern uebernimmt ein vorgeschaltetes
QSortFilterProxyModel (rekursiv, damit eine Gruppe erhalten bleibt, sobald ein
Kind den Suchbegriff enthaelt).

Die angezeigten Spalten kommen wie in der flachen Tabelle aus der Nutzer-
Konfiguration (siehe grid_columns), damit Tabelle und Baum identisch aussehen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont

from jira_timesheet_qt.models.export_column import ExportColumn, default_columns
from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.ui.grid_columns import (
    GridColumn,
    build_columns,
    display_value,
    group_display,
    group_sort,
    sort_value,
)
from jira_timesheet_qt.ui.timesheet_model import ENTRY_ROLE, SORT_ROLE, apply_manual_edit

AnyIndex = QModelIndex | QPersistentModelIndex


def _alignment(column: GridColumn) -> int:
    alignment = Qt.AlignmentFlag.AlignRight if column.numeric else Qt.AlignmentFlag.AlignLeft
    return int(alignment | Qt.AlignmentFlag.AlignVCenter)


@dataclass
class _Group:
    """Ein Tag mit seinen Eintraegen."""

    day: date
    entries: list[WorklogEntry]

    @property
    def total(self) -> float:
        return sum(entry.hours for entry in self.entries)


class _Node:
    """Knoten im Baum: Wurzel, Gruppe oder Eintrag."""

    __slots__ = ("kind", "row", "parent", "children", "group", "entry")

    def __init__(self, kind: str, row: int, parent: _Node | None) -> None:
        self.kind = kind  # "root" | "group" | "entry"
        self.row = row
        self.parent = parent
        self.children: list[_Node] = []
        self.group: _Group | None = None
        self.entry: WorklogEntry | None = None


class TimesheetTreeModel(QAbstractItemModel):
    """Stellt die Eintraege eines Stundenzettels nach Tag gruppiert dar."""

    # Meldet, dass ein manueller Eintrag inline geaendert wurde.
    manual_edited = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = _Node("root", 0, None)
        self._columns: list[GridColumn] = build_columns(default_columns())
        self._default_customer = ""
        # Farbe fuer manuell erfasste Zeilen, oder None wenn abgeschaltet.
        self._manual_color: QColor | None = None

    # --- Konfiguration -------------------------------------------------

    def set_columns(self, columns: list[ExportColumn], default_customer: str) -> None:
        """Setzt die sichtbaren Spalten und den Vorgabe-Kunden neu."""
        self.beginResetModel()
        self._columns = build_columns(columns)
        self._default_customer = default_customer
        self.endResetModel()

    def column_keys(self) -> list[str]:
        """Schluessel der aktuell angezeigten Spalten, in Reihenfolge."""
        return [column.key for column in self._columns]

    def stretch_column(self) -> int:
        """Index der Spalte, die die Restbreite fuellt (Beschreibung), sonst -1."""
        return next((i for i, c in enumerate(self._columns) if c.stretch), -1)

    def column_width(self, section: int) -> int:
        """Vorgabe-Breite einer Spalte."""
        return self._columns[section].width if 0 <= section < len(self._columns) else 100

    def set_manual_color(self, color: QColor | None) -> None:
        """Setzt die Einfaerbung manueller Eintraege (None = keine)."""
        self._manual_color = color
        # Voller Reset ist hier am einfachsten - der Baum ist klein, und die
        # Farbe aendert sich nur beim Speichern der Einstellungen.
        self.beginResetModel()
        self.endResetModel()

    # --- Befuellen -----------------------------------------------------

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Baut den Baum aus den Eintraegen eines Stundenzettels neu auf."""
        self.beginResetModel()
        root = _Node("root", 0, None)
        if timesheet is not None:
            by_day: dict[date, list[WorklogEntry]] = {}
            for entry in timesheet.all_entries:
                by_day.setdefault(entry.date, []).append(entry)
            for group_row, day in enumerate(sorted(by_day)):
                group_node = _Node("group", group_row, root)
                group_node.group = _Group(day, by_day[day])
                for entry_row, entry in enumerate(by_day[day]):
                    entry_node = _Node("entry", entry_row, group_node)
                    entry_node.entry = entry
                    group_node.children.append(entry_node)
                root.children.append(group_node)
        self._root = root
        self.endResetModel()

    def entry_at_index(self, index: AnyIndex) -> WorklogEntry | None:
        """Liefert den Eintrag hinter einer Zeile, oder None fuer Gruppen."""
        node = self._node(index)
        return node.entry if node.kind == "entry" else None

    def day_at_index(self, index: AnyIndex) -> date | None:
        """Liefert den Tag einer Zeile - vom Eintrag oder von der Gruppe."""
        node = self._node(index)
        if node.kind == "entry" and node.entry is not None:
            return node.entry.date
        if node.kind == "group" and node.group is not None:
            return node.group.day
        return None

    # --- Qt-Schnittstelle ----------------------------------------------

    def _node(self, index: AnyIndex) -> _Node:
        if index.isValid():
            pointer = index.internalPointer()
            if isinstance(pointer, _Node):
                return pointer
        return self._root

    def index(self, row: int, column: int, parent: AnyIndex = QModelIndex()) -> QModelIndex:  # noqa: N802,B008
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        children = self._node(parent).children
        if 0 <= row < len(children):
            return self.createIndex(row, column, children[row])
        return QModelIndex()

    # parent() ist in QObject/QAbstractItemModel ueberladen (ohne Argument vs.
    # mit Index) - ein Override kollidiert zwangslaeufig mit einer Signatur.
    def parent(self, child: AnyIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]  # noqa: B008
        if not child.isValid():
            return QModelIndex()
        node = self._node(child)
        parent = node.parent
        if parent is None or parent.kind == "root":
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def rowCount(self, parent: AnyIndex = QModelIndex()) -> int:  # noqa: N802,B008
        if parent.isValid() and parent.column() > 0:
            return 0
        return len(self._node(parent).children)

    def columnCount(self, parent: AnyIndex = QModelIndex()) -> int:  # noqa: N802,B008
        return len(self._columns)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is not Qt.Orientation.Horizontal or not 0 <= section < len(self._columns):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._columns[section].title
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(self._columns[section])
        return None

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.column() < len(self._columns):
            return None
        node = self._node(index)
        column = self._columns[index.column()]
        if node.kind == "group" and node.group is not None:
            return self._group_data(node.group, column, role)
        if node.kind == "entry" and node.entry is not None:
            day_total = node.parent.group.total if node.parent and node.parent.group else node.entry.hours
            return self._entry_data(node.entry, column, day_total, role)
        return None

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        """Nur manuelle Eintragszeilen sind in den editierbaren Spalten aenderbar."""
        flags = super().flags(index)
        if not index.isValid() or not 0 <= index.column() < len(self._columns):
            return flags
        entry = self.entry_at_index(index)
        if entry is not None and entry.manual and self._columns[index.column()].editable:
            return flags | Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(  # noqa: N802
        self,
        index: AnyIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Uebernimmt eine Inline-Aenderung an einem manuellen Eintrag."""
        if role != Qt.ItemDataRole.EditRole or not index.isValid() or not 0 <= index.column() < len(self._columns):
            return False
        entry = self.entry_at_index(index)
        if entry is None or not entry.manual:
            return False
        if not apply_manual_edit(entry, self._columns[index.column()].key, value):
            return False
        self.dataChanged.emit(index, index)
        self.manual_edited.emit(entry)
        return True

    # --- Zellinhalte ----------------------------------------------------

    def _group_data(self, group: _Group, column: GridColumn, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return group_display(column.key, group.day, len(group.entries), group.total)
        if role == SORT_ROLE:
            return group_sort(column.key, group.day, group.total)
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(column)
        return None

    def _entry_data(self, entry: WorklogEntry, column: GridColumn, day_total: float, role: int) -> Any:
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            # Datum, Tag und KW stehen schon in der Gruppenzeile darueber.
            if column.key in ("date", "weekday", "week"):
                return ""
            return display_value(entry, column.key, day_total, self._default_customer)
        if role == ENTRY_ROLE:
            return entry
        if role == SORT_ROLE:
            return sort_value(entry, column.key, day_total, self._default_customer)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(column)
        if role == Qt.ItemDataRole.ForegroundRole and entry.manual and self._manual_color is not None:
            return self._manual_color
        return None
