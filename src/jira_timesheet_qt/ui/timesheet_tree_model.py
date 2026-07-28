"""Baum-Modell fuer die nach Tag gruppierte Ansicht des Stundenzettels.

Zwei Ebenen: Tages-Gruppen als Elternzeilen (mit Tagessumme in der
Stunden-Spalte), die einzelnen Eintraege als Kinder. Ein QTreeView klappt die
Gruppen auf und zu. Sortieren/Filtern uebernimmt ein vorgeschaltetes
QSortFilterProxyModel (rekursiv, damit eine Gruppe erhalten bleibt, sobald ein
Kind den Suchbegriff enthaelt).

Spalten, Sortier-Rolle und Eintrags-Rolle kommen aus timesheet_model, damit
Tabelle und Baum identisch formatieren.
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

from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.ui.timesheet_model import (
    COLUMNS,
    EDITABLE_KEYS,
    ENTRY_ROLE,
    SORT_ROLE,
    Column,
    apply_manual_edit,
)

AnyIndex = QModelIndex | QPersistentModelIndex

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _fmt_hours(hours: float) -> str:
    """Stunden mit deutschem Dezimalkomma, zwei Nachkommastellen."""
    return f"{hours:.2f}".replace(".", ",")


def _alignment(column: Column) -> int:
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
        # Farbe fuer manuell erfasste Zeilen, oder None wenn abgeschaltet.
        self._manual_color: QColor | None = None

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
        return len(COLUMNS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is not Qt.Orientation.Horizontal or not 0 <= section < len(COLUMNS):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section].title
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(COLUMNS[section])
        return None

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        node = self._node(index)
        column = COLUMNS[index.column()]
        if node.kind == "group" and node.group is not None:
            return self._group_data(node.group, column, role)
        if node.kind == "entry" and node.entry is not None:
            return self._entry_data(node.entry, column, role)
        return None

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        """Nur manuelle Eintragszeilen sind in den editierbaren Spalten aenderbar."""
        flags = super().flags(index)
        if not index.isValid():
            return flags
        entry = self.entry_at_index(index)
        if entry is not None and entry.manual and COLUMNS[index.column()].key in EDITABLE_KEYS:
            return flags | Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(  # noqa: N802
        self,
        index: AnyIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Uebernimmt eine Inline-Aenderung an einem manuellen Eintrag."""
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        entry = self.entry_at_index(index)
        if entry is None or not entry.manual:
            return False
        if not apply_manual_edit(entry, COLUMNS[index.column()].key, value):
            return False
        self.dataChanged.emit(index, index)
        self.manual_edited.emit(entry)
        return True

    # --- Zellinhalte ----------------------------------------------------

    def _group_data(self, group: _Group, column: Column, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if column.key == "date":
                return group.day.strftime("%d.%m.%Y")
            if column.key == "weekday":
                return _WEEKDAYS[group.day.weekday()]
            if column.key == "summary":
                count = len(group.entries)
                return "1 Eintrag" if count == 1 else f"{count} Einträge"
            if column.key == "hours":
                return _fmt_hours(group.total)
            return ""
        if role == SORT_ROLE:
            if column.key == "date":
                return group.day
            if column.key == "hours":
                return group.total
            return ""
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(column)
        return None

    def _entry_data(self, entry: WorklogEntry, column: Column, role: int) -> Any:
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            # Datum und Tag stehen schon in der Gruppenzeile darueber.
            if column.key in ("date", "weekday"):
                return ""
            if column.key == "ticket":
                return entry.ticket
            if column.key == "summary":
                return entry.summary
            if column.key == "author":
                return entry.author
            if column.key == "hours":
                return _fmt_hours(entry.hours)
            return ""
        if role == ENTRY_ROLE:
            return entry
        if role == SORT_ROLE:
            if column.key == "hours":
                return entry.hours
            return self._entry_data(entry, column, Qt.ItemDataRole.DisplayRole).lower()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(column)
        if role == Qt.ItemDataRole.ForegroundRole and entry.manual and self._manual_color is not None:
            return self._manual_color
        return None
