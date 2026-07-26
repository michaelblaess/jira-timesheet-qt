"""Hauptfenster: verdrahtet Kopfzeile, Seitenleiste, Liste und Detailbereich.

Aufbau bewusst ohne QMenuBar und ohne QTabWidget - beides verraet auf den
ersten Blick ein Standard-Toolkit. Der Ansichtswechsel laeuft ueber die
Seitenleiste und ein QStackedWidget, das keine Reiter zeichnet.
"""

from __future__ import annotations

import calendar
from datetime import date

from PySide6.QtCore import QModelIndex, QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt import __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.ui.about_dialog import AboutDialog
from jira_timesheet_qt.ui.detail_panel import DetailPanel
from jira_timesheet_qt.ui.header import Header
from jira_timesheet_qt.ui.jira_worker import WorklogWorker
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
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
        self._worker: WorklogWorker | None = None
        self._qsettings = QSettings("michaelblaess", "jira-timesheet-qt")

        # Nur der reine Name: QApplication traegt den Anzeigenamen selbst bei,
        # sonst steht er doppelt in der Titelleiste.
        self.setWindowTitle(f"Stundenzettel {__version__}")
        self.resize(1280, 780)
        self.setMinimumSize(940, 560)

        today = date.today()
        self._year = today.year
        self._month = today.month

        self._model = TimesheetModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(SORT_ROLE)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        self._build_ui()
        self._install_shortcuts()
        self._restore_geometry()
        self._update_period_labels()

    # --- Aufbau ---------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = Header()
        self._header.search_changed.connect(self._proxy.setFilterFixedString)
        self._header.theme_toggled.connect(self._toggle_theme)
        self._header.settings_requested.connect(self.open_settings)
        self._header.about_requested.connect(self.open_about)
        self._header.previous_month.connect(lambda: self._shift_month(-1))
        self._header.next_month.connect(lambda: self._shift_month(1))
        outer.addWidget(self._header)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.setChildrenCollapsible(False)

        self._sidebar = Sidebar(_VIEWS)
        self._sidebar.view_changed.connect(self._on_view_changed)
        body.addWidget(self._sidebar)

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self._build_empty_state())
        self._list_stack.addWidget(self._build_table())

        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_stack)
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

        self._status = QLabel("Bereit")
        self._status.setObjectName("StatusBar")
        self._status.setContentsMargins(18, 7, 18, 7)
        outer.addWidget(self._status)

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
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._table = table
        return table

    def _build_empty_state(self) -> QWidget:
        """Zustand ohne Daten - erklaert, was als Naechstes zu tun ist."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self._empty_title = QLabel("Noch keine Daten")
        self._empty_title.setObjectName("EmptyTitle")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_title)

        self._empty_text = QLabel("Hinterlege zuerst Deinen Jira-Zugang in den Einstellungen.")
        self._empty_text.setObjectName("EmptyText")
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_text)
        layout.addSpacing(6)

        self._empty_button = QPushButton("Einstellungen öffnen")
        self._empty_button.setProperty("variant", "primary")
        self._empty_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._empty_button.setFixedWidth(200)
        self._empty_button.clicked.connect(self._on_empty_button)
        layout.addWidget(self._empty_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

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
        QShortcut(QKeySequence.StandardKey.Refresh, self, self.load_month)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self, self.open_about)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    # --- Inhalte --------------------------------------------------------

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Uebernimmt einen Stundenzettel in die Anzeige."""
        self._model.set_timesheet(timesheet)
        self._sidebar.set_total(self._model.total_hours)
        self._detail.clear()

        has_rows = self._model.rowCount() > 0
        self._list_stack.setCurrentIndex(1 if has_rows else 0)
        if not has_rows:
            self._update_empty_state()

        self._update_period_labels()

    def _update_period_labels(self) -> None:
        """Setzt Ueberschrift und Zusatzzeile der Kopfzeile."""
        title = f"{Header.month_name(self._month)} {self._year}"
        count = self._model.rowCount()
        if count == 0:
            self._header.set_period(title, "Keine Einträge geladen")
            return
        entries = "Eintrag" if count == 1 else "Einträge"
        days = len({self._model.entry_at(row).date for row in range(count)})  # type: ignore[union-attr]
        self._header.set_period(title, f"{count} {entries} · {days} Arbeitstage")

    def _update_empty_state(self) -> None:
        """Passt den Leerzustand an: fehlt der Zugang oder nur die Daten?"""
        if self._settings_complete():
            self._empty_title.setText("Keine Einträge in diesem Zeitraum")
            self._empty_text.setText("Hole die Buchungen aus Jira oder wähle einen anderen Monat.")
            self._empty_button.setText("Aus Jira laden")
        else:
            self._empty_title.setText("Noch keine Daten")
            self._empty_text.setText("Hinterlege zuerst Deinen Jira-Zugang in den Einstellungen.")
            self._empty_button.setText("Einstellungen öffnen")

    def _settings_complete(self) -> bool:
        """True, wenn Host, Token und E-Mail gesetzt sind."""
        s = self._settings
        return bool(s.jira_host and s.jira_token and s.email)

    # --- Abruf ----------------------------------------------------------

    def load_month(self) -> None:
        """Holt die Buchungen des eingestellten Monats aus Jira."""
        if self._worker is not None and self._worker.isRunning():
            return
        if not self._settings_complete():
            self._set_status("Zugang unvollständig - bitte Host, E-Mail und Token hinterlegen.", "error")
            self.open_settings()
            return

        first = date(self._year, self._month, 1)
        last = date(self._year, self._month, calendar.monthrange(self._year, self._month)[1])

        self._set_status(f"Lade {Header.month_name(self._month)} {self._year} ...", "busy")
        worker = WorklogWorker(self._settings, first, last, self)
        worker.progress.connect(lambda text: self._set_status(text, "busy"))
        worker.finished_ok.connect(self._on_loaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_done)
        self._worker = worker
        worker.start()

    def _on_loaded(self, timesheet: Timesheet) -> None:
        self.set_timesheet(timesheet)
        hours = self._model.total_hours
        self._set_status(f"{self._model.rowCount()} Einträge · {hours:.2f} h".replace(".", ","))

    def _on_failed(self, message: str) -> None:
        self.set_timesheet(None)
        self._set_status(message, "error")

    def _on_worker_done(self) -> None:
        self._worker = None

    def _set_status(self, text: str, state: str = "") -> None:
        """Schreibt in die Statuszeile. state faerbt sie ueber das Stylesheet."""
        self._status.setText(text)
        self._status.setProperty("state", state)
        style = self._status.style()
        style.unpolish(self._status)
        style.polish(self._status)

    # --- Ereignisse -----------------------------------------------------

    def _on_empty_button(self) -> None:
        """Der Knopf im Leerzustand tut, was gerade ansteht."""
        if self._settings_complete():
            self.load_month()
        else:
            self.open_settings()

    def open_settings(self) -> None:
        """Oeffnet die Einstellungen und uebernimmt das Ergebnis."""
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != int(SettingsDialog.DialogCode.Accepted):
            return
        self._settings = dialog.result_settings()
        self._settings.save()
        self._update_empty_state()
        self._set_status("Einstellungen gespeichert")
        if self._settings.theme in ("dark", "light"):
            self._mode = Mode(self._settings.theme)
            self.theme_changed.emit(self._settings.theme)

    def open_about(self) -> None:
        """Zeigt den Info-Dialog."""
        AboutDialog(self).exec()

    def _shift_month(self, delta: int) -> None:
        """Blaettert um einen Monat vor oder zurueck."""
        month = self._month + delta
        year = self._year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self._month, self._year = month, year
        self._update_period_labels()
        if self._settings_complete():
            self.load_month()

    def _on_view_changed(self, position: int) -> None:
        self._stack.setCurrentIndex(position)

    def _on_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Haelt den Detailbereich im Gleichklang mit der Auswahl."""
        if not current.isValid():
            self._detail.clear()
            return
        entry = current.data(ENTRY_ROLE)
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
        self._settings.theme = self._mode.value
        self._settings.save()
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
            self.restoreGeometry(geometry)
        sizes = self._qsettings.value("window/splitter")
        if isinstance(sizes, list) and len(sizes) == 3:
            self._splitter.setSizes([int(value) for value in sizes])

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Merkt Fenstergroesse und Aufteilung, wartet auf den Arbeitsfaden."""
        self._qsettings.setValue("window/geometry", self.saveGeometry())
        self._qsettings.setValue("window/splitter", self._splitter.sizes())
        if self._worker is not None and self._worker.isRunning():
            # Ohne das kann Qt beim Beenden ueber einen laufenden Faden stolpern.
            self._worker.wait(3000)
        super().closeEvent(event)
