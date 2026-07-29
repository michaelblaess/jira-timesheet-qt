"""Tabellenmodell fuer den Stundenzettel.

Trennt Daten von Darstellung: die View kennt nur dieses Modell, das Modell nur
die Domaenenobjekte aus models/timesheet.py. Sortieren und Filtern uebernimmt
ein vorgeschaltetes QSortFilterProxyModel - dafuer liefert das Modell zu jeder
Zelle einen sortierbaren Rohwert unter SORT_ROLE.

Welche Spalten in welcher Reihenfolge erscheinen, kommt aus der Nutzer-
Konfiguration (siehe grid_columns) - dieselbe, die auch den Export steuert.
"""

from __future__ import annotations

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

from jira_timesheet_qt.models.export_column import DESCRIPTION_KEY, ExportColumn, default_columns
from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.hours_parser import parse_hours
from jira_timesheet_qt.ui.grid_columns import (
    HOUR_KEYS,
    GridColumn,
    build_columns,
    display_value,
    is_day_total_cell,
    sort_value,
)


def apply_manual_edit(entry: WorklogEntry, key: str, value: object) -> bool:
    """Uebernimmt eine Inline-Aenderung in den Eintrag.

    Args:
        entry:
            Der zu aendernde (manuelle) Eintrag.
        key:
            Spaltenschluessel - "description" oder "hours".
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
    if key == DESCRIPTION_KEY:
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

# Qt reicht beide Indexarten durch - die Signatur muss beide annehmen.
AnyIndex = QModelIndex | QPersistentModelIndex


class TimesheetModel(QAbstractTableModel):
    """Stellt die Eintraege eines Stundenzettels als Tabelle bereit."""

    # Meldet, dass ein manueller Eintrag inline geaendert wurde (fuer die
    # Persistenz durch das Hauptfenster).
    manual_edited = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[WorklogEntry] = []
        self._day_totals: dict[date, float] = {}
        self._columns: list[GridColumn] = build_columns(default_columns())
        self._default_customer = ""
        # Farbe fuer manuell erfasste Zeilen, oder None wenn die Hervorhebung
        # abgeschaltet ist. Wird vom Hauptfenster aus den Einstellungen gesetzt.
        self._manual_color: QColor | None = None
        # Ampel-Farben der Tagessummen (ueber/unter Soll), None = abgeschaltet.
        self._day_over: QColor | None = None
        self._day_under: QColor | None = None
        self._day_target = 0.0

    # --- Konfiguration -------------------------------------------------

    def set_columns(self, columns: list[ExportColumn], default_customer: str) -> None:
        """Setzt die sichtbaren Spalten und den Vorgabe-Kunden neu.

        Die Spaltenzahl kann sich aendern, deshalb ein voller Reset.
        """
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
        self._emit_colors_changed()

    def set_day_total_colors(self, over: QColor | None, under: QColor | None, target: float) -> None:
        """Setzt die Ampel-Farben der Tagessummen (None = keine Faerbung)."""
        self._day_over = over
        self._day_under = under
        self._day_target = target
        self._emit_colors_changed()

    def _emit_colors_changed(self) -> None:
        """Meldet, dass sich die Vordergrundfarben aller Zeilen geaendert haben."""
        if self._entries:
            top = self.index(0, 0)
            bottom = self.index(len(self._entries) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.ForegroundRole])

    # --- Befuellen -----------------------------------------------------

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Ersetzt den Inhalt durch die Eintraege eines Stundenzettels."""
        self.beginResetModel()
        self._entries = list(timesheet.all_entries) if timesheet is not None else []
        self._day_totals = {}
        for entry in self._entries:
            self._day_totals[entry.date] = self._day_totals.get(entry.date, 0.0) + entry.hours
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
            return self._alignment(self._columns[section])
        return None

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        entry = self.entry_at(index.row())
        if entry is None or not 0 <= index.column() < len(self._columns):
            return None
        column = self._columns[index.column()]
        day_total = self._day_totals.get(entry.date, 0.0)

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return display_value(entry, column.key, day_total, self._default_customer)
        if role == SORT_ROLE:
            return sort_value(entry, column.key, day_total, self._default_customer)
        if role == ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(column)
        if role == Qt.ItemDataRole.ForegroundRole:
            # Die Tagessumme traegt die Soll-Ist-Ampel und geht der Markierung vor.
            if self._day_over is not None and is_day_total_cell(column.key, False):
                return self._day_over if day_total >= self._day_target else self._day_under
            # Die Markierung manueller Eintraege bleibt den Zahlenspalten fern.
            if entry.manual and self._manual_color is not None and column.key not in HOUR_KEYS:
                return self._manual_color
        return None

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        """Manuelle Eintraege sind in den editierbaren Spalten aenderbar."""
        flags = super().flags(index)
        if not index.isValid() or not 0 <= index.column() < len(self._columns):
            return flags
        entry = self.entry_at(index.row())
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
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        entry = self.entry_at(index.row())
        if entry is None or not entry.manual or not 0 <= index.column() < len(self._columns):
            return False
        if not apply_manual_edit(entry, self._columns[index.column()].key, value):
            return False
        # Eine geaenderte Stunde verschiebt auch die Tagessumme.
        self._day_totals[entry.date] = sum(e.hours for e in self._entries if e.date == entry.date)
        self.dataChanged.emit(index, index)
        self.manual_edited.emit(entry)
        return True

    # --- Zellinhalte ----------------------------------------------------

    @staticmethod
    def _alignment(column: GridColumn) -> int:
        alignment = Qt.AlignmentFlag.AlignRight if column.numeric else Qt.AlignmentFlag.AlignLeft
        return int(alignment | Qt.AlignmentFlag.AlignVCenter)

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
