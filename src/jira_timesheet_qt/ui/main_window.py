"""Hauptfenster: verdrahtet Menue, Toolbar, Reiter, Ansichten und Summenleiste.

Aufbau nahe an der TUI: eine Reiterleiste (Liste/Kalender/Jahr) ueber einem
QStackedWidget, Monatsnavigation und Suche in der Toolbar, darunter die
Ansicht in voller Breite, unten die Summenleiste. Die Details eines Eintrags
kommen als modaler Dialog (Doppelklick/Toolbar/Kontextmenue), nicht als fester
Bereich.
"""

from __future__ import annotations

import calendar
import contextlib
import webbrowser
from collections.abc import Callable
from datetime import date

import qtawesome as qta
from PySide6.QtCore import QModelIndex, QPoint, QSettings, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QTableView,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt import __app_name__, __version__
from jira_timesheet_qt.i18n import t
from jira_timesheet_qt.models.settings import Settings, normalize_color
from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.services.manual_entry_service import ManualEntryService
from jira_timesheet_qt.ui.about_dialog import AboutDialog
from jira_timesheet_qt.ui.calendar_view import CalendarView, DayCell
from jira_timesheet_qt.ui.detail_dialog import TicketDetailDialog
from jira_timesheet_qt.ui.export_service import ExportService
from jira_timesheet_qt.ui.highlight_delegate import HighlightDelegate
from jira_timesheet_qt.ui.icons import load_icon
from jira_timesheet_qt.ui.jira_worker import WorklogWorker
from jira_timesheet_qt.ui.log_dock import Level, LogDock
from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog
from jira_timesheet_qt.ui.menu import Command, CommandRegistry, MenuBuilder, MenuDefinition, missing_commands
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.summary_bar import SummaryBar
from jira_timesheet_qt.ui.theme import SCALES, Mode, palette_for, set_accent, set_scale
from jira_timesheet_qt.ui.timesheet_model import ENTRY_ROLE, SORT_ROLE, TimesheetModel
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel
from jira_timesheet_qt.ui.year_view import YearView

_VIEWS = ("Liste", "Kalender", "Jahr")

_MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _month_name(month: int) -> str:
    """Deutscher Monatsname zu einer Monatszahl von 1 bis 12."""
    return _MONTHS[month - 1] if 1 <= month <= len(_MONTHS) else ""


# Zustand der Statuszeile -> Ebene im Meldungsfenster.
_LEVELS = {"error": Level.ERROR, "busy": Level.INFO, "": Level.SUCCESS}


class MainWindow(QMainWindow):
    """Fensterrahmen der Anwendung."""

    # Meldet den Wunsch nach einem anderen Erscheinungsbild ("dark"/"light").
    theme_changed = Signal(str)

    def __init__(self, settings: Settings, mode: Mode) -> None:
        super().__init__()
        self._settings = settings
        self._mode = mode
        self._worker: WorklogWorker | None = None
        self._timesheet: Timesheet | None = None
        # Zuletzt in der Liste gewaehlter Eintrag - fuer den Details-Befehl aus
        # Toolbar/Menue (Doppelklick und Kontextmenue bringen ihren mit).
        self._current_entry: WorklogEntry | None = None
        self._qsettings = QSettings("michaelblaess", "jira-timesheet-qt")

        # Nur der reine Name: QApplication traegt den Anzeigenamen selbst bei,
        # sonst steht er doppelt in der Titelleiste.
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1280, 780)
        self.setMinimumSize(940, 560)

        today = date.today()
        self._year = today.year
        self._month = today.month
        # Summen je Monat, gefuellt sobald ein Monat geladen wurde.
        self._year_hours: dict[int, float] = {}
        self._year_entries: dict[int, int] = {}
        # Gebuchte Tage und manueller Anteil je Monat (fuer die Jahreskacheln).
        self._year_booked: dict[int, int] = {}
        self._year_manual: dict[int, float] = {}
        # Fuer welches Jahr die Jahresansicht zuletzt vollstaendig geladen wurde.
        self._year_loaded_for: int | None = None

        self._model = TimesheetModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(SORT_ROLE)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        # Nach Tag gruppierte Ansicht (umschaltbar). Rekursives Filtern haelt
        # eine Gruppe, sobald ein Eintrag den Suchbegriff enthaelt.
        self._tree_model = TimesheetTreeModel(self)
        self._tree_proxy = QSortFilterProxyModel(self)
        self._tree_proxy.setSourceModel(self._tree_model)
        self._tree_proxy.setSortRole(SORT_ROLE)
        self._tree_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tree_proxy.setFilterKeyColumn(-1)
        self._tree_proxy.setRecursiveFilteringEnabled(True)
        self._grouped = bool(self._qsettings.value("grouped", False, type=bool))

        # Inline-Aenderungen an manuellen Eintraegen persistieren.
        self._model.manual_edited.connect(self._persist_inline_edit)
        self._tree_model.manual_edited.connect(self._persist_inline_edit)

        # Spalten-Konfiguration aus den Einstellungen in die Modelle uebernehmen,
        # BEVOR die Ansichten gebaut werden - sonst zeigt der erste Aufbau die
        # Standard-Spalten statt der konfigurierten.
        self._model.set_columns(self._settings.export_columns, self._settings.default_customer)
        self._tree_model.set_columns(self._settings.export_columns, self._settings.default_customer)

        # Einfaerbung manueller Eintraege aus den Einstellungen uebernehmen.
        self._apply_manual_color()

        self._build_ui()
        self._install_shortcuts()
        self._restore_geometry()
        self._update_period_labels()
        # Zuletzt, und nach restoreState: ein hide() vor dem ersten Anzeigen
        # des Fensters haelt nicht, sobald danach noch etwas ins Fenster
        # geschrieben wird - der Bildlauf hebt das Verstecken wieder auf.
        self._log.setVisible(self._settings.log_visible)

    # --- Aufbau ---------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Ansichtswahl als Reiter (wie in der TUI) statt Seitenleiste.
        self._tabs = QTabBar()
        self._tabs.setObjectName("ViewTabs")
        self._tabs.setExpanding(False)
        self._tabs.setDrawBase(False)
        self._tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for name in _VIEWS:
            self._tabs.addTab(name)
        self._tabs.currentChanged.connect(self._on_view_changed)
        outer.addWidget(self._tabs)

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self._build_empty_state())
        self._list_stack.addWidget(self._build_table())
        self._list_stack.addWidget(self._build_tree())

        self._calendar = CalendarView(self._mode)
        self._calendar.day_selected.connect(self._on_day_selected)
        self._calendar.day_activated.connect(self._on_day_activated)

        self._year_view = YearView(self._mode)
        self._year_view.month_selected.connect(self._on_month_selected)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_stack)
        self._stack.addWidget(self._calendar)
        self._stack.addWidget(self._year_view)
        outer.addWidget(self._stack, 1)

        self._summary = SummaryBar(self._mode)
        outer.addWidget(self._summary)

        self.setCentralWidget(central)

        # Echte QStatusBar - traegt die Statuszeile UND den Groessengriff unten
        # rechts (setSizeGripEnabled). Das Label behaelt Objektname/Zustandsfarbe.
        self._status = QLabel("Bereit")
        self._status.setObjectName("StatusBar")
        self._status.setContentsMargins(18, 5, 12, 5)
        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(True)
        status_bar.addWidget(self._status, 1)
        self.setStatusBar(status_bar)

        self._log = LogDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log)
        self._log.resize(self._log.width(), 180)
        self._log.write("Bereit")

        self._install_menu()

    # --- Datengetriebenes Menue -----------------------------------------

    def _install_menu(self) -> None:
        """Baut die Menueleiste aus der JSON-Definition (datengetrieben).

        Struktur kommt aus resources/menu.json, Verhalten aus der Registry -
        verbunden nur ueber die Command-ID. Dieselbe Definition koennte ueber
        die 'toolbar'-Surface auch eine QToolBar erzeugen (siehe MenuBuilder).
        """
        from importlib import resources

        self._commands = CommandRegistry()
        self._register_commands(self._commands)

        raw = (resources.files("jira_timesheet_qt") / "resources" / "menu.json").read_text(
            encoding="utf-8"
        )
        definition = MenuDefinition.model_validate_json(raw)

        missing = missing_commands(definition, self._commands.ids())
        if missing:
            self._log.write(f"Menue verweist auf unbekannte Commands: {sorted(missing)}", Level.ERROR)

        builder = MenuBuilder(self._commands, owner=self, tr=t, icon_loader=self._menu_icon)
        self.setMenuBar(builder.build_menubar(definition.menubar, self))

        # Dieselbe Definition, zweite Oberflaeche: die 'toolbar'-Surface.
        toolbar = builder.build_toolbar(definition.menubar, self)
        toolbar.setObjectName("MainToolBar")  # fuer saveState/restoreState
        toolbar.setMovable(False)
        self._build_toolbar_extras(toolbar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self._menu_definition = definition
        self._toolbar = toolbar

    def _build_toolbar_extras(self, toolbar: QToolBar) -> None:
        """Ergaenzt die Toolbar um Monatsnavigation (mittig) und Suche (rechts).

        Zwei dehnbare Zwischenraeume schieben die Monatsnavigation in die Mitte,
        das Suchfeld sitzt danach am rechten Rand.
        """
        toolbar.addWidget(self._stretch())

        self._prev_button = self._nav_button("chevron-left", "Vorheriger Monat", lambda: self._shift_month(-1))
        toolbar.addWidget(self._prev_button)

        self._month_label = QLabel("Kein Zeitraum")
        self._month_label.setObjectName("ToolbarMonth")
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_label.setMinimumWidth(150)
        toolbar.addWidget(self._month_label)

        self._next_button = self._nav_button("chevron-right", "Nächster Monat", lambda: self._shift_month(1))
        toolbar.addWidget(self._next_button)

        toolbar.addWidget(self._stretch())

        self._search = QLineEdit()
        self._search.setObjectName("ToolbarSearch")
        self._search.setPlaceholderText("Suchen ...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._search)

    @staticmethod
    def _stretch() -> QWidget:
        """Dehnbarer Zwischenraum fuer die Toolbar."""
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return spacer

    def _nav_button(self, icon: str, tooltip: str, slot: Callable[[], None]) -> QPushButton:
        """Baut einen Pfeilknopf fuer die Monatsnavigation - als echter Knopf."""
        button = QPushButton()
        button.setObjectName("MonthNavButton")
        button.setIcon(load_icon(icon, self._mode))
        button.setIconSize(QSize(16, 16))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def _focus_search(self) -> None:
        """Setzt den Eingabefokus ins Suchfeld der Toolbar."""
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def _recolor_toolbar_extras(self) -> None:
        """Faerbt die Monatspfeile nach einem Themenwechsel neu ein."""
        self._prev_button.setIcon(load_icon("chevron-left", self._mode))
        self._next_button.setIcon(load_icon("chevron-right", self._mode))

    def _register_commands(self, registry: CommandRegistry) -> None:
        """Registriert das Verhalten hinter den Command-IDs der Menue-Definition."""
        add = registry.register
        add(Command("file.reload", run=self.reload_current))
        add(Command("file.manual_new", run=self.action_new_manual))
        add(Command("file.quit", run=self.close))
        add(Command("view.list", run=lambda: self._go_to_view(0),
                    is_checked=lambda: self._stack.currentIndex() == 0))
        add(Command("view.calendar", run=lambda: self._go_to_view(1),
                    is_checked=lambda: self._stack.currentIndex() == 1))
        add(Command("view.year", run=lambda: self._go_to_view(2),
                    is_checked=lambda: self._stack.currentIndex() == 2))
        add(Command("view.detail", run=self._show_detail_current))
        add(Command("view.group", run=lambda: self._on_group_toggled(not self._grouped),
                    is_checked=lambda: self._grouped))
        add(Command("view.log", run=self.toggle_log,
                    is_checked=lambda: self._log.isVisible()))
        add(Command("view.theme", run=self._toggle_theme))
        add(Command("export.excel", run=self.export_excel))
        add(Command("export.pdf", run=self.export_pdf))
        add(Command("export.print", run=self.print_preview))
        add(Command("settings.open", run=self.open_settings))
        add(Command("help.about", run=self.open_about))

    def _go_to_view(self, position: int) -> None:
        """Wechselt die Ansicht ueber den Reiter (loest _on_view_changed aus)."""
        self._tabs.setCurrentIndex(position)

    def _menu_icon(self, token: str) -> QIcon:
        """Laedt ein mdi6-Icon fuer das Menue in der Strichfarbe des Themes."""
        with contextlib.suppress(Exception):
            icon = qta.icon(token, color=palette_for(self._mode).text_secondary)
            if isinstance(icon, QIcon):
                return icon
        return QIcon()

    def _recolor_menu_icons(self) -> None:
        """Faerbt die Menue-/Toolbar-Icons nach einem Theme-Wechsel neu ein."""
        for node in self._menu_definition.menubar.walk():
            if node.icon and node.command:
                action = self._commands.get(node.command).action
                if action is not None:
                    action.setIcon(self._menu_icon(node.icon))

    def _build_table(self) -> QTableView:
        """Baut die Liste der Eintraege."""
        table = QTableView()
        table.setModel(self._proxy)
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setFrameShape(QTableView.Shape.NoFrame)

        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsMovable(True)
        self._apply_column_layout(table, self._model)

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)

        table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        table.doubleClicked.connect(self._on_row_activated)

        # Hebt den aktuellen Suchbegriff in den Zellen hervor.
        self._highlight = HighlightDelegate(table)
        table.setItemDelegate(self._highlight)

        self._table = table
        return table

    def _build_tree(self) -> QTreeView:
        """Baut die nach Tag gruppierte Ansicht (auf-/zuklappbar)."""
        tree = QTreeView()
        tree.setModel(self._tree_proxy)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        tree.setAlternatingRowColors(True)
        tree.setUniformRowHeights(True)
        tree.setRootIsDecorated(True)
        tree.setSortingEnabled(False)
        tree.setWordWrap(False)
        tree.setFrameShape(QTreeView.Shape.NoFrame)
        # Derselbe Delegate wie die flache Liste - hebt den Suchbegriff hervor.
        tree.setItemDelegate(self._highlight)

        header = tree.header()
        header.setHighlightSections(False)
        header.setSectionsMovable(True)
        self._apply_column_layout(tree, self._tree_model)

        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        tree.selectionModel().currentRowChanged.connect(self._on_row_changed)
        tree.doubleClicked.connect(self._on_row_activated)
        self._tree = tree
        return tree

    def _apply_column_layout(self, view: QTableView | QTreeView, model: TimesheetModel | TimesheetTreeModel) -> None:
        """Setzt Spaltenbreiten und die Streck-Spalte (Beschreibung) einer Ansicht.

        Die Spalten kommen aus dem Modell (Nutzer-Konfiguration). Die
        Beschreibungs-Spalte fuellt die Restbreite, alle anderen behalten ihre
        Vorgabe-Breite. Ist keine Beschreibung sichtbar, wird die letzte Spalte
        gestreckt, damit rechts kein leerer Rand bleibt.
        """
        header = view.horizontalHeader() if isinstance(view, QTableView) else view.header()
        count = model.columnCount()
        stretch = model.stretch_column()
        if stretch < 0:
            stretch = count - 1
        for section in range(count):
            if section == stretch:
                header.setSectionResizeMode(section, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(section, QHeaderView.ResizeMode.Interactive)
                view.setColumnWidth(section, model.column_width(section))

    def _apply_column_settings(self) -> None:
        """Uebernimmt die Spalten-Konfiguration aus den Einstellungen in beide Ansichten."""
        self._model.set_columns(self._settings.export_columns, self._settings.default_customer)
        self._tree_model.set_columns(self._settings.export_columns, self._settings.default_customer)
        self._apply_column_layout(self._table, self._model)
        self._apply_column_layout(self._tree, self._tree_model)

    def _on_search_changed(self, text: str) -> None:
        """Filtert beide Ansichten und hebt den Suchbegriff in den Zellen hervor."""
        self._proxy.setFilterFixedString(text)
        self._tree_proxy.setFilterFixedString(text)
        self._highlight.set_needle(text)
        # Neu zeichnen, damit die Hervorhebung sofort erscheint bzw. verschwindet.
        self._table.viewport().update()
        self._tree.viewport().update()
        # Bei aktiver Suche die Gruppen aufklappen, damit Treffer sichtbar sind.
        if self._grouped and text:
            self._tree.expandAll()

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
        QShortcut(QKeySequence.StandardKey.Find, self, self._focus_search)
        QShortcut(QKeySequence.StandardKey.Refresh, self, self.reload_current)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self, self.open_about)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+L"), self, self.toggle_log)
        QShortcut(QKeySequence("Ctrl+N"), self, self.action_new_manual)
        QShortcut(QKeySequence.StandardKey.Print, self, self.print_preview)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_excel)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, self.export_pdf)
        # Zoom wie im Browser: Ctrl++ / Ctrl+- / Ctrl+0.
        QShortcut(QKeySequence.StandardKey.ZoomIn, self, lambda: self._zoom(1))
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self._zoom(1))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self, lambda: self._zoom(-1))
        QShortcut(QKeySequence("Ctrl+0"), self, self._zoom_reset)

    # --- Inhalte --------------------------------------------------------

    def _apply_manual_color(self) -> None:
        """Setzt die Einfaerbung manueller Eintraege in beiden Listenmodellen.

        Die Farbe kommt aus den Einstellungen; ist die Hervorhebung
        abgeschaltet, faerbt None die Zeilen wieder normal ein.
        """
        color: QColor | None = None
        if self._settings.mark_manual_entries:
            color = QColor(f"#{normalize_color(self._settings.manual_entry_color)}")
        self._model.set_manual_color(color)
        self._tree_model.set_manual_color(color)

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Uebernimmt einen Stundenzettel in alle Ansichten."""
        self._timesheet = timesheet
        self._model.set_timesheet(timesheet)
        self._tree_model.set_timesheet(timesheet)
        self._tree.expandAll()
        self._calendar.set_month(
            self._year, self._month, timesheet, self._settings.federal_state, self._settings.hours_per_day
        )
        self._update_year_view(timesheet)
        self._refresh_summary_bar()
        self._current_entry = None

        has_rows = self._model.rowCount() > 0
        self._list_stack.setCurrentIndex(self._list_page(has_rows))
        if not has_rows:
            self._update_empty_state()

        self._update_period_labels()

    def _list_page(self, has_rows: bool) -> int:
        """Waehlt die Seite des Listen-Stacks: leer (0), flach (1) oder gruppiert (2)."""
        if not has_rows:
            return 0
        return 2 if self._grouped else 1

    def _on_group_toggled(self, grouped: bool) -> None:
        """Schaltet zwischen flacher und nach Tag gruppierter Ansicht um."""
        self._grouped = grouped
        self._qsettings.setValue("grouped", grouped)
        if grouped:
            self._tree.expandAll()
        self._list_stack.setCurrentIndex(self._list_page(self._model.rowCount() > 0))

    def _refresh_summary_bar(self) -> None:
        """Fuellt die Summenleiste passend zur aktiven Ansicht."""
        view = self._stack.currentIndex()
        if view == 1:
            self._summary_calendar()
        elif view == 2:
            self._summary_year()
        else:
            self._summary_list()

    def _summary_list(self) -> None:
        """Liste: volle Summenleiste, Fortschritt Ist gegen Soll des Zeitraums."""
        if self._timesheet is None:
            self._summary.clear()
            return
        target_workdays = HolidayService(self._settings.federal_state).count_workdays(
            self._timesheet.date_from, self._timesheet.date_to
        )
        self._summary.show_list(self._timesheet, self._settings, target_workdays)

    def _summary_calendar(self) -> None:
        """Kalender: gebuchte Arbeitstage und Ist/Soll des Monats."""
        cells = self._calendar.cells
        workdays = [cell for cell in cells if cell.in_month and cell.is_workday]
        booked = [cell for cell in workdays if cell.hours > 0]
        total_hours = sum(cell.hours for cell in cells if cell.in_month)
        target_hours = len(workdays) * self._settings.hours_per_day
        self._summary.show_calendar(
            len(booked), len(workdays), total_hours, target_hours, len(workdays) - len(booked)
        )

    def _summary_year(self) -> None:
        """Jahr: Ist/Soll/Prognose der Jahresansicht."""
        summary = self._year_view.summary
        self._summary.show_year(self._year, summary.actual, summary.target, summary.forecast)

    # --- Manuelle Zeiten -----------------------------------------------

    def _entry_menu(self, entry: WorklogEntry | None, day: date | None) -> QMenu:
        """Baut das Rechtsklick-Menue fuer eine Zeile (Eintrag oder Tag)."""
        menu = QMenu(self)

        if entry is not None:
            detail_action = menu.addAction("Details anzeigen")
            detail_action.triggered.connect(lambda _checked=False, e=entry: self._show_detail(e))

        if entry is not None and entry.ticket and self._settings.jira_host:
            open_action = menu.addAction("Ticket im Browser öffnen")
            open_action.triggered.connect(lambda _checked=False, e=entry: self._open_ticket(e))

        if entry is not None:
            menu.addSeparator()

        new_action = menu.addAction("Manuelle Zeit erfassen")
        new_action.triggered.connect(lambda _checked=False, d=day: self.action_new_manual(d))

        if entry is not None and entry.manual and entry.manual_id > 0:
            edit_action = menu.addAction("Manuellen Eintrag bearbeiten")
            edit_action.triggered.connect(lambda _checked=False, e=entry: self._edit_manual(e))
            delete_action = menu.addAction("Manuellen Eintrag löschen")
            delete_action.triggered.connect(lambda _checked=False, e=entry: self._delete_manual(e))

        return menu

    def _on_table_context_menu(self, pos: QPoint) -> None:
        """Rechtsklick-Menue der flachen Liste an der Mausposition."""
        entry = self._entry_at_pos(pos)
        day = entry.date if entry is not None else None
        self._entry_menu(entry, day).exec(self._table.viewport().mapToGlobal(pos))

    def _on_tree_context_menu(self, pos: QPoint) -> None:
        """Rechtsklick-Menue der gruppierten Ansicht (auch auf Gruppenzeilen)."""
        source = self._tree_proxy.mapToSource(self._tree.indexAt(pos))
        entry = self._tree_model.entry_at_index(source)
        day = self._tree_model.day_at_index(source)
        self._entry_menu(entry, day).exec(self._tree.viewport().mapToGlobal(pos))

    def _entry_at_pos(self, pos: QPoint) -> WorklogEntry | None:
        """Liefert den Eintrag unter der Mausposition (oder None)."""
        index = self._table.indexAt(pos)
        if not index.isValid():
            return None
        source = self._proxy.mapToSource(index)
        return self._model.entry_at(source.row())

    def action_new_manual(self, default_date: date | None = None) -> None:
        """Oeffnet den Dialog fuer einen neuen manuellen Eintrag."""
        start = default_date if isinstance(default_date, date) else self._default_manual_date()
        dialog = ManualEntryDialog(
            customers=self._customer_options(),
            default_customer=self._settings.default_customer,
            default_date=start,
            parent=self,
        )
        if dialog.exec() != int(ManualEntryDialog.DialogCode.Accepted):
            return
        entry = dialog.result_entry()
        if entry is None:
            return
        with ManualEntryService() as service:
            saved = service.add(entry)
        if saved > 0:
            self._set_status("Manueller Eintrag gespeichert.")
            self._reload_after_manual()

    def _edit_manual(self, entry: WorklogEntry) -> None:
        """Oeffnet den Dialog zum Bearbeiten eines manuellen Eintrags."""
        with ManualEntryService() as service:
            current = service.get(entry.manual_id)
        if current is None:
            self._set_status("Manueller Eintrag nicht gefunden.", "error")
            return
        dialog = ManualEntryDialog(
            customers=self._customer_options(),
            default_customer=self._settings.default_customer,
            entry=current,
            parent=self,
        )
        if dialog.exec() != int(ManualEntryDialog.DialogCode.Accepted):
            return
        updated = dialog.result_entry()
        if updated is None:
            return
        with ManualEntryService() as service:
            service.update(updated)
        self._set_status("Manueller Eintrag geändert.")
        self._reload_after_manual()

    def _delete_manual(self, entry: WorklogEntry) -> None:
        """Loescht einen manuellen Eintrag nach Rueckfrage."""
        answer = QMessageBox.question(
            self,
            "Löschen",
            f"Manuellen Eintrag vom {entry.date:%d.%m.%Y} ({entry.hours:.2f} h) löschen?".replace(".", ",", 1),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with ManualEntryService() as service:
            service.delete(entry.manual_id)
        self._set_status("Manueller Eintrag gelöscht.")
        self._reload_after_manual()

    def _reload_after_manual(self) -> None:
        """Laedt den Monat neu, damit die manuellen Zeiten neu eingemischt werden."""
        self.load_month()

    def _persist_inline_edit(self, entry: WorklogEntry) -> None:
        """Speichert eine Inline-Aenderung an einem manuellen Eintrag.

        Der Eintrag im Speicher ist bereits geaendert; hier wird der zugehoerige
        Datensatz aktualisiert und die Ansicht aus dem geaenderten Stundenzettel
        neu aufgebaut (Tagessummen, Gruppen und Summenleiste ziehen nach). Ein
        erneuter Jira-Abruf ist dafuer nicht noetig.
        """
        if not entry.manual or entry.manual_id <= 0:
            return
        with ManualEntryService() as service:
            current = service.get(entry.manual_id)
            if current is None:
                self._set_status("Manueller Eintrag nicht gefunden.", "error")
                return
            current.summary = entry.summary
            current.hours = entry.hours
            service.update(current)
        self._set_status("Manueller Eintrag geändert.")
        if self._timesheet is not None:
            self.set_timesheet(self._timesheet)

    def _default_manual_date(self) -> date:
        """Vorbelegtes Datum: heute im aktuellen Monat, sonst der Monatserste."""
        today = date.today()
        if today.year == self._year and today.month == self._month:
            return today
        return date(self._year, self._month, 1)

    def _customer_options(self) -> list[str]:
        """Kundenliste fuer den Dialog: Einstellungen + bereits benutzte."""
        options = list(self._settings.customers)
        default = self._settings.default_customer
        if default and default not in options:
            options.insert(0, default)
        with ManualEntryService() as service:
            for name in service.distinct_customers():
                if name not in options:
                    options.append(name)
        return options

    def _open_ticket(self, entry: WorklogEntry) -> None:
        """Oeffnet das Ticket im Standardbrowser."""
        host = self._settings.jira_host.rstrip("/")
        if host and entry.ticket:
            webbrowser.open(f"{host}/browse/{entry.ticket}")

    def _update_period_labels(self) -> None:
        """Setzt den Monatstitel in der Toolbar."""
        self._month_label.setText(f"{_month_name(self._month)} {self._year}")

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

        self._set_status(f"Lade {_month_name(self._month)} {self._year} ...", "busy")
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

    def load_year(self) -> None:
        """Holt alle zwoelf Monate des Jahres in einem einzigen Bereichs-Abruf."""
        if self._worker is not None and self._worker.isRunning():
            return
        if not self._settings_complete():
            self._set_status("Zugang unvollständig - bitte Host, E-Mail und Token hinterlegen.", "error")
            self.open_settings()
            return
        self._set_status(f"Lade Jahr {self._year} ...", "busy")
        worker = WorklogWorker(self._settings, date(self._year, 1, 1), date(self._year, 12, 31), self)
        worker.progress.connect(lambda text: self._set_status(text, "busy"))
        worker.finished_ok.connect(self._on_year_loaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_done)
        self._worker = worker
        worker.start()

    def _on_year_loaded(self, timesheet: Timesheet) -> None:
        """Aggregiert einen Jahres-Stundenzettel in die zwoelf Monatskacheln."""
        hours: dict[int, float] = {}
        entries: dict[int, int] = {}
        manual: dict[int, float] = {}
        days: dict[int, set[date]] = {}
        for entry in timesheet.all_entries:
            month = entry.date.month
            hours[month] = hours.get(month, 0.0) + entry.hours
            entries[month] = entries.get(month, 0) + 1
            if entry.manual:
                manual[month] = manual.get(month, 0.0) + entry.hours
            days.setdefault(month, set()).add(entry.date)
        booked = {month: len(dates) for month, dates in days.items()}
        self._year_hours = hours
        self._year_entries = entries
        self._year_booked = booked
        self._year_manual = manual
        self._year_loaded_for = self._year
        self._year_view.set_year(
            self._year, hours, entries, self._settings.hours_per_day, self._settings.federal_state,
            booked_days_by_month=booked, manual_by_month=manual,
        )
        self._refresh_summary_bar()
        count = sum(entries.values())
        total = f"{sum(hours.values()):.2f}".replace(".", ",")
        self._set_status(f"Jahr {self._year}: {count} Einträge · {total} h")

    def reload_current(self) -> None:
        """Laedt neu - je nach aktiver Ansicht den Monat oder das ganze Jahr."""
        if self._stack.currentIndex() == 2:
            self._year_loaded_for = None
            self.load_year()
        else:
            self.load_month()

    def _set_status(self, text: str, state: str = "") -> None:
        """Schreibt in Statuszeile und Meldungsfenster.

        Die Statuszeile zeigt nur den letzten Stand, das Meldungsfenster den
        ganzen Verlauf - bei einem fehlgeschlagenen Abruf braucht man beides.
        """
        self._log.write(text, _LEVELS.get(state, Level.INFO))
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
        self._apply_column_settings()
        self._apply_manual_color()
        self._update_empty_state()
        self._set_status("Einstellungen gespeichert")
        # Akzentfarbe und (bei fester Wahl) Erscheinungsbild uebernehmen und die
        # Oberflaeche neu einfaerben - der app-weite Palette-/QSS-Neuaufbau laeuft
        # ueber theme_changed im Einstiegspunkt.
        set_accent(self._settings.accent)
        set_scale(self._settings.ui_scale)
        if self._settings.theme in ("dark", "light"):
            self._mode = Mode(self._settings.theme)
        self._reapply_theme()

    # --- Export ---------------------------------------------------------

    def export_excel(self) -> None:
        """Schreibt den aktuellen Stundenzettel als Arbeitsmappe."""
        self._export("excel")

    def export_pdf(self) -> None:
        """Schreibt den aktuellen Stundenzettel als PDF."""
        self._export("pdf")

    def _export(self, kind: str) -> None:
        """Gemeinsamer Weg fuer beide Dateiformate."""
        if self._timesheet is None:
            self._set_status("Erst Daten laden, dann exportieren.", "error")
            return
        service = ExportService(self._settings)
        try:
            result = (
                service.export_excel(self._timesheet, self)
                if kind == "excel"
                else service.export_pdf(self._timesheet, self)
            )
        except Exception as exc:  # noqa: BLE001 - der Grund gehoert in die Anzeige
            self._set_status(f"Export fehlgeschlagen: {exc}", "error")
            return
        if result.cancelled:
            return
        self._set_status(f"Gespeichert: {result.path}")
        service.open_file(result.path)

    def print_preview(self) -> None:
        """Zeigt die Druckvorschau."""
        if self._timesheet is None:
            self._set_status("Erst Daten laden, dann drucken.", "error")
            return
        ExportService(self._settings).show_print_preview(self._timesheet, self)

    def toggle_log(self) -> None:
        """Blendet das Meldungsfenster ein oder aus und merkt sich das."""
        visible = not self._log.isVisible()
        self._log.setVisible(visible)
        self._settings.log_visible = visible
        self._settings.save()

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
        self._calendar.set_month(
            self._year, self._month, self._timesheet, self._settings.federal_state, self._settings.hours_per_day
        )
        if self._settings_complete():
            self.load_month()

    def _on_view_changed(self, position: int) -> None:
        self._stack.setCurrentIndex(position)
        self._refresh_summary_bar()
        # Beim ersten Wechsel in die Jahresansicht (oder nach Jahreswechsel) alle
        # zwoelf Monate in einem Bereichs-Abruf laden.
        if position == 2 and self._settings_complete() and self._year_loaded_for != self._year:
            self.load_year()

    def _update_year_view(self, timesheet: Timesheet | None) -> None:
        """Traegt die Summen des geladenen Zeitraums in die Jahresansicht.

        Geladen ist immer nur ein Monat - die uebrigen Kacheln bleiben leer,
        bis der Anwender sie besucht hat.
        """
        if timesheet is not None and timesheet.all_entries:
            self._year_hours[self._month] = timesheet.total_hours
            self._year_entries[self._month] = len(timesheet.all_entries)
            self._year_booked[self._month] = len({e.date for e in timesheet.all_entries})
            self._year_manual[self._month] = sum(e.hours for e in timesheet.all_entries if e.manual)
        self._year_view.set_year(
            self._year,
            self._year_hours,
            self._year_entries,
            self._settings.hours_per_day,
            self._settings.federal_state,
            booked_days_by_month=self._year_booked,
            manual_by_month=self._year_manual,
        )

    def _on_day_selected(self, cell: DayCell) -> None:
        """Klick auf eine Kachel meldet den Tag; Doppelklick zeigt die Details."""
        if cell.entries:
            self._current_entry = cell.entries[0]
            self._set_status(f"{cell.day:%d.%m.%Y}: {len(cell.entries)} Einträge")
        else:
            self._current_entry = None
            reason = cell.holiday or ("Wochenende" if cell.is_weekend else "keine Buchung")
            self._set_status(f"{cell.day:%d.%m.%Y}: {reason}")

    def _on_day_activated(self, cell: DayCell) -> None:
        """Doppelklick auf eine Kachel oeffnet die Details des ersten Eintrags."""
        if cell.entries:
            self._show_detail(cell.entries[0])

    def _on_month_selected(self, month: int) -> None:
        """Klick auf eine Monatskachel wechselt dorthin und laedt."""
        self._month = month
        self._update_period_labels()
        self._tabs.setCurrentIndex(0)
        self._stack.setCurrentIndex(0)
        if self._settings_complete():
            self.load_month()

    def _on_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Merkt sich den gewaehlten Eintrag fuer den Details-Befehl."""
        self._current_entry = current.data(ENTRY_ROLE) if current.isValid() else None

    def _on_row_activated(self, index: QModelIndex) -> None:
        """Doppelklick auf eine Zeile oeffnet die Details.

        Editierbare Zellen (Beschreibung/Stunden manueller Eintraege) bleiben
        ausgenommen - dort startet der Doppelklick die Inline-Bearbeitung.
        """
        if not index.isValid() or index.flags() & Qt.ItemFlag.ItemIsEditable:
            return
        entry = index.data(ENTRY_ROLE)
        if entry is not None:
            self._show_detail(entry)

    def _show_detail(self, entry: WorklogEntry) -> None:
        """Oeffnet den modalen Detail-Dialog fuer einen Eintrag."""
        TicketDetailDialog(entry, self._settings.jira_host, self).exec()

    def _show_detail_current(self) -> None:
        """Details-Befehl aus Toolbar/Menue: zeigt den gewaehlten Eintrag."""
        if self._current_entry is not None:
            self._show_detail(self._current_entry)
        else:
            self._set_status("Kein Eintrag gewählt.")

    def _toggle_theme(self) -> None:
        """Schaltet zwischen hellem und dunklem Erscheinungsbild um.

        Das Stylesheet haengt an der QApplication, nicht am Fenster - deshalb
        nur melden. Angewandt wird es im Einstiegspunkt.
        """
        self._mode = Mode.LIGHT if self._mode is Mode.DARK else Mode.DARK
        self._settings.theme = self._mode.value
        self._settings.save()
        self._reapply_theme()

    def _zoom(self, direction: int) -> None:
        """Schaltet den Oberflaechen-Zoom eine Stufe hoch (1) oder runter (-1)."""
        try:
            index = SCALES.index(self._settings.ui_scale)
        except ValueError:
            index = SCALES.index(100)
        new_index = max(0, min(len(SCALES) - 1, index + direction))
        self._set_zoom(SCALES[new_index])

    def _zoom_reset(self) -> None:
        """Setzt den Zoom auf 100 %."""
        self._set_zoom(100)

    def _set_zoom(self, percent: int) -> None:
        """Uebernimmt eine Zoomstufe, speichert sie und baut das Theme neu auf."""
        if percent == self._settings.ui_scale:
            return
        self._settings.ui_scale = percent
        self._settings.save()
        set_scale(percent)
        self._reapply_theme()
        self._set_status(f"Zoom {percent} %")

    def _reapply_theme(self) -> None:
        """Faerbt alle selbstgezeichneten Flaechen neu und stoesst den app-weiten
        Palette-/QSS-Neuaufbau an (Erscheinungsbild ODER Akzentfarbe geaendert).

        Die Symbole liegen je Erscheinungsbild in eigenen Dateien vor, die
        selbstgezeichneten Ansichten lesen die Farben beim naechsten Zeichnen.
        """
        self._recolor_toolbar_extras()
        self._calendar.apply_mode(self._mode)
        self._year_view.apply_mode(self._mode)
        self._summary.apply_mode(self._mode)
        self._recolor_menu_icons()
        self.theme_changed.emit(self._mode.value)

    @property
    def mode(self) -> Mode:
        """Aktuell gewaehltes Erscheinungsbild."""
        return self._mode

    # --- Fensterzustand -------------------------------------------------

    def _restore_geometry(self) -> None:
        """Stellt Fenstergroesse und -zustand der letzten Sitzung her."""
        geometry = self._qsettings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self._qsettings.value("window/state")
        if state is not None:
            # Stellt auch die Sichtbarkeit des Meldungsfensters wieder her.
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Merkt Fenstergroesse und -zustand, wartet auf den Arbeitsfaden."""
        self._qsettings.setValue("window/geometry", self.saveGeometry())
        self._qsettings.setValue("window/state", self.saveState())
        if self._worker is not None and self._worker.isRunning():
            # Ohne das kann Qt beim Beenden ueber einen laufenden Faden stolpern.
            self._worker.wait(3000)
        super().closeEvent(event)
