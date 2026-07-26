"""Hauptfenster: verdrahtet Kopfzeile, Seitenleiste, Liste und Detailbereich.

Aufbau bewusst ohne QMenuBar und ohne QTabWidget - beides verraet auf den
ersten Blick ein Standard-Toolkit. Der Ansichtswechsel laeuft ueber die
Seitenleiste und ein QStackedWidget, das keine Reiter zeichnet.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt import __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.ui.detail_panel import DetailPanel
from jira_timesheet_qt.ui.header import Header
from jira_timesheet_qt.ui.sidebar import Sidebar
from jira_timesheet_qt.ui.theme import Mode
from jira_timesheet_qt.ui.timesheet_model import COLUMNS, ENTRY_ROLE, SORT_ROLE, TimesheetModel

_VIEWS = ("Liste", "Kalender", "Jahr")


class MainWindow(QMainWindow):
    """Fensterrahmen der Anwendung."""

    # Meldet den Wunsch nach einem anderen Erscheinungsbild ("dark"/"light").
    theme_changed = Signal(str)

    def __init__(self, settings: Settings, mode: Mode) -> None:
        super().__init__()
        self._settings = settings
        self._mode = mode
        self._qsettings = QSettings("michaelblaess", "jira-timesheet-qt")

        self.setWindowTitle(f"Stundenzettel {__version__}")
        self.resize(1280, 780)
        self.setMinimumSize(940, 560)

        self._model = TimesheetModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(SORT_ROLE)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Ueber alle Spalten suchen, nicht nur ueber die erste.
        self._proxy.setFilterKeyColumn(-1)

        self._build_ui()
        self._install_shortcuts()
        self._restore_geometry()

    # --- Aufbau ---------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = Header()
        self._header.search_changed.connect(self._proxy.setFilterFixedString)
        self._header.theme_toggled.connect(self._toggle_theme)
        outer.addWidget(self._header)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.setChildrenCollapsible(False)

        self._sidebar = Sidebar(_VIEWS)
        self._sidebar.view_changed.connect(self._on_view_changed)
        body.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_table())
        self._stack.addWidget(self._placeholder("Kalender", "Die Monatsansicht entsteht in Stufe 2."))
        self._stack.addWidget(self._placeholder("Jahr", "Die Jahresansicht entsteht in Stufe 2."))
        body.addWidget(self._stack)

        self._detail = DetailPanel()
        body.addWidget(self._detail)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([200, 780, 300])
        self._splitter = body
        outer.addWidget(body, 1)

        self.setCentralWidget(central)

    def _build_table(self) -> QTableView:
        """Baut die Liste der Eintraege."""
        table = QTableView()
        table.setModel(self._proxy)
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setFrameShape(QTableView.Shape.NoFrame)

        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsMovable(True)
        for index, column in enumerate(COLUMNS):
            table.setColumnWidth(index, column.width)
        # Die Beschreibung bekommt den verbleibenden Platz.
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._table = table
        return table

    def _placeholder(self, title: str, text: str) -> QWidget:
        """Leerzustand fuer noch nicht gebaute Ansichten."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("EmptyTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        body = QLabel(text)
        body.setObjectName("EmptyText")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body)
        return page

    def _install_shortcuts(self) -> None:
        """Standardtasten statt der Einzelbuchstaben aus der TUI."""
        QShortcut(QKeySequence.StandardKey.Find, self, self._header.focus_search)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    # --- Inhalte --------------------------------------------------------

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Uebernimmt einen Stundenzettel in die Anzeige."""
        self._model.set_timesheet(timesheet)
        self._sidebar.set_total(self._model.total_hours)
        self._detail.clear()

        period = self._model.period
        if timesheet is None or period is None:
            self._header.set_period("Kein Zeitraum", "Noch keine Daten geladen")
            return

        first, last = period
        if first.year == last.year and first.month == last.month:
            title = f"{Header.month_name(first.month)} {first.year}"
        else:
            title = f"{first.strftime('%d.%m.%Y')} bis {last.strftime('%d.%m.%Y')}"
        count = self._model.rowCount()
        entries = "Eintrag" if count == 1 else "Einträge"
        self._header.set_period(title, f"{count} {entries} · {timesheet.working_days} Arbeitstage")

    # --- Ereignisse -----------------------------------------------------

    def _on_view_changed(self, position: int) -> None:
        self._stack.setCurrentIndex(position)

    def _on_row_changed(self, current: object, _previous: object) -> None:
        """Haelt den Detailbereich im Gleichklang mit der Auswahl."""
        index = current if hasattr(current, "isValid") else None
        if index is None or not index.isValid():  # type: ignore[union-attr]
            self._detail.clear()
            return
        entry = index.data(ENTRY_ROLE)  # type: ignore[union-attr]
        if entry is None:
            self._detail.clear()
        else:
            self._detail.show_entry(entry)

    def _toggle_theme(self) -> None:
        """Schaltet zwischen hellem und dunklem Erscheinungsbild um.

        Das Stylesheet haengt an der QApplication, nicht am Fenster - deshalb
        nur melden. Angewandt wird es im Einstiegspunkt.
        """
        self._mode = Mode.LIGHT if self._mode is Mode.DARK else Mode.DARK
        self.theme_changed.emit(self._mode.value)

    @property
    def mode(self) -> Mode:
        """Aktuell gewaehltes Erscheinungsbild."""
        return self._mode

    # --- Fensterzustand -------------------------------------------------

    def _restore_geometry(self) -> None:
        """Stellt Fenstergroesse und Aufteilung der letzten Sitzung her."""
        geometry = self._qsettings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)  # type: ignore[arg-type]
        sizes = self._qsettings.value("window/splitter")
        if isinstance(sizes, list) and len(sizes) == 3:
            self._splitter.setSizes([int(value) for value in sizes])

    def closeEvent(self, event: object) -> None:  # noqa: N802
        """Merkt Fenstergroesse und Aufteilung fuer den naechsten Start."""
        self._qsettings.setValue("window/geometry", self.saveGeometry())
        self._qsettings.setValue("window/splitter", self._splitter.sizes())
        super().closeEvent(event)  # type: ignore[arg-type]
