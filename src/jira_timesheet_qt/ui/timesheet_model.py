"""Tabellenmodell fuer den Stundenzettel.

Trennt Daten von Darstellung: die View kennt nur dieses Modell, das Modell nur
die Domaenenobjekte aus models/timesheet.py. Sortieren und Filtern uebernimmt
ein vorgeschaltetes QSortFilterProxyModel - dafuer liefert das Modell zu jeder
Zelle einen sortierbaren Rohwert unter SORT_ROLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor

from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.hours_parser import parse_hours

# Spalten, die bei manuellen Eintraegen direkt in der Tabelle editierbar sind.
# Datum/Kunde bleiben dem vollen Erfassungsdialog vorbehalten (Datum wuerde den
# Eintrag zwischen Tagen/Gruppen verschieben).
EDITABLE_KEYS = ("summary", "hours")


def apply_manual_edit(entry: WorklogEntry, key: str, value: object) -> bool:
    """Uebernimmt eine Inline-Aenderung in den Eintrag.

    Args:
        entry:
            Der zu aendernde (manuelle) Eintrag.
        key:
            Spaltenschluessel - "summary" oder "hours".
        value:
            Der neue Wert aus dem Editor (Text).

    Returns:
        True bei gueltiger Uebernahme, False wenn der Wert ungueltig ist
        (leere Beschreibung, nicht parsbare oder nicht-positive Stunden).
    """
    if key == "hours":
        parsed = parse_hours(str(value))
        if parsed is None:
            return False
        entry.hours = parsed
        return True
    if key == "summary":
        text = str(value).strip()
        if not text:
            return False
        entry.summary = text
        return True
    return False

# Rohwert einer Zelle zum Sortieren - die Anzeige ist lokalisiert und taugt
# dafuer nicht ("23.07.2026" sortiert als Zeichenkette falsch).
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
# Der Eintrag hinter einer Zeile, fuer den Detailbereich.
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 2


@dataclass(frozen=True)
class Column:
    """Beschreibung einer Tabellenspalte."""

    key: str
    title: str
    width: int
    numeric: bool = False


# Qt reicht beide Indexarten durch - die Signatur muss beide annehmen.
AnyIndex = QModelIndex | QPersistentModelIndex

COLUMNS: tuple[Column, ...] = (
    Column("date", "Datum", 110),
    Column("weekday", "Tag", 60),
    Column("ticket", "Vorgang", 130),
    Column("summary", "Beschreibung", 420),
    Column("author", "Autor", 130),
    Column("hours", "Stunden", 90, numeric=True),
)

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


class TimesheetModel(QAbstractTableModel):
    """Stellt die Eintraege eines Stundenzettels als Tabelle bereit."""

    # Meldet, dass ein manueller Eintrag inline geaendert wurde (fuer die
    # Persistenz durch das Hauptfenster).
    manual_edited = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[WorklogEntry] = []
        # Farbe fuer manuell erfasste Zeilen, oder None wenn die Hervorhebung
        # abgeschaltet ist. Wird vom Hauptfenster aus den Einstellungen gesetzt.
        self._manual_color: QColor | None = None

    def set_manual_color(self, color: QColor | None) -> None:
        """Setzt die Einfaerbung manueller Eintraege (None = keine)."""
        self._manual_color = color
        if self._entries:
            top = self.index(0, 0)
            bottom = self.index(len(self._entries) - 1, len(COLUMNS) - 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.ForegroundRole])

    # --- Befuellen -----------------------------------------------------

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Ersetzt den Inhalt durch die Eintraege eines Stundenzettels."""
        self.beginResetModel()
        self._entries = list(timesheet.all_entries) if timesheet is not None else []
        self.endResetModel()

    def entry_at(self, row: int) -> WorklogEntry | None:
        """Liefert den Eintrag einer Zeile, oder None ausserhalb des Bereichs."""
        return self._entries[row] if 0 <= row < len(self._entries) else None

    # --- Qt-Schnittstelle ----------------------------------------------

    def rowCount(self, parent: AnyIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent: AnyIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is not Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(COLUMNS):
            return COLUMNS[section].title
        if role == Qt.ItemDataRole.TextAlignmentRole and 0 <= section < len(COLUMNS):
            return self._alignment(COLUMNS[section])
        return None

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        entry = self.entry_at(index.row())
        if entry is None:
            return None
        column = COLUMNS[index.column()]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._display(entry, column)
        if role == SORT_ROLE:
            return self._sort_value(entry, column)
        if role == ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(column)
        if role == Qt.ItemDataRole.ForegroundRole and entry.manual and self._manual_color is not None:
            return self._manual_color
        return None

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        """Manuelle Eintraege sind in den editierbaren Spalten aenderbar."""
        flags = super().flags(index)
        if not index.isValid():
            return flags
        entry = self.entry_at(index.row())
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
        entry = self.entry_at(index.row())
        if entry is None or not entry.manual:
            return False
        if not apply_manual_edit(entry, COLUMNS[index.column()].key, value):
            return False
        self.dataChanged.emit(index, index)
        self.manual_edited.emit(entry)
        return True

    # --- Zellinhalte ----------------------------------------------------

    @staticmethod
    def _alignment(column: Column) -> int:
        alignment = Qt.AlignmentFlag.AlignRight if column.numeric else Qt.AlignmentFlag.AlignLeft
        return int(alignment | Qt.AlignmentFlag.AlignVCenter)

    def _display(self, entry: WorklogEntry, column: Column) -> str:
        """Formatiert eine Zelle fuer die Anzeige (deutsche Schreibweise)."""
        if column.key == "date":
            return entry.date.strftime("%d.%m.%Y")
        if column.key == "weekday":
            return _WEEKDAYS[entry.date.weekday()]
        if column.key == "ticket":
            return entry.ticket
        if column.key == "summary":
            return entry.summary
        if column.key == "author":
            return entry.author
        if column.key == "hours":
            # Deutsches Dezimalkomma, zwei Nachkommastellen.
            return f"{entry.hours:.2f}".replace(".", ",")
        return ""

    def _sort_value(self, entry: WorklogEntry, column: Column) -> object:
        """Liefert den Rohwert einer Zelle - danach wird sortiert."""
        if column.key == "date":
            return entry.date
        if column.key == "weekday":
            return entry.date.weekday()
        if column.key == "hours":
            return entry.hours
        return self._display(entry, column).lower()

    # --- Kennzahlen -----------------------------------------------------

    @property
    def total_hours(self) -> float:
        """Summe aller Stunden im Modell."""
        return sum(entry.hours for entry in self._entries)

    @property
    def period(self) -> tuple[date, date] | None:
        """Erster und letzter Tag mit Eintraegen, oder None wenn leer."""
        if not self._entries:
            return None
        dates = [entry.date for entry in self._entries]
        return min(dates), max(dates)
