"""Hauptfenster: verdrahtet Kopfzeile, Seitenleiste, Liste und Detailbereich.

Aufbau bewusst ohne QMenuBar und ohne QTabWidget - beides verraet auf den
ersten Blick ein Standard-Toolkit. Der Ansichtswechsel laeuft ueber die
Seitenleiste und ein QStackedWidget, das keine Reiter zeichnet.
"""

from __future__ import annotations

import calendar
import contextlib
import webbrowser
from datetime import date

import qtawesome as qta
from PySide6.QtCore import QModelIndex, QPoint, QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableView,
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
from jira_timesheet_qt.ui.detail_panel import DetailPanel
from jira_timesheet_qt.ui.export_service import ExportService
from jira_timesheet_qt.ui.header import Header
from jira_timesheet_qt.ui.highlight_delegate import HighlightDelegate
from jira_timesheet_qt.ui.jira_worker import WorklogWorker
from jira_timesheet_qt.ui.log_dock import Level, LogDock
from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog
from jira_timesheet_qt.ui.menu import Command, CommandRegistry, MenuBuilder, MenuDefinition, missing_commands
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.sidebar import Sidebar
from jira_timesheet_qt.ui.summary_bar import SummaryBar
from jira_timesheet_qt.ui.theme import Mode, palette_for
from jira_timesheet_qt.ui.timesheet_model import COLUMNS, ENTRY_ROLE, SORT_ROLE, TimesheetModel
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel
from jira_timesheet_qt.ui.year_view import YearView

_VIEWS = ("Liste", "Kalender", "Jahr")

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

        # Einfaerbung manueller Eintraege aus den Einstellungen uebernehmen.
        self._apply_manual_color()

        self._build_ui()
        self._header.set_grouped(self._grouped)
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

        self._header = Header(self._mode)
        self._header.search_changed.connect(self._on_search_changed)
        self._header.theme_toggled.connect(self._toggle_theme)
        self._header.settings_requested.connect(self.open_settings)
        self._header.about_requested.connect(self.open_about)
        self._header.reload_requested.connect(self.reload_current)
        self._header.log_toggled.connect(self.toggle_log)
        self._header.manual_requested.connect(self.action_new_manual)
        self._header.group_toggled.connect(self._on_group_toggled)
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
        self._list_stack.addWidget(self._build_tree())

        self._calendar = CalendarView(self._mode)
        self._calendar.day_selected.connect(self._on_day_selected)

        self._year_view = YearView(self._mode)
        self._year_view.month_selected.connect(self._on_month_selected)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_stack)
        self._stack.addWidget(self._calendar)
        self._stack.addWidget(self._year_view)
        body.addWidget(self._stack)

        self._detail = DetailPanel()
        body.addWidget(self._detail)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([200, 780, 300])
        self._splitter = body
        outer.addWidget(body, 1)

        self._summary = SummaryBar()
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
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self._menu_definition = definition
        self._toolbar = toolbar

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
        """Wechselt die Ansicht (Sidebar-Markierung + Stack + Jahres-Load)."""
        self._sidebar.select_view(position)
        self._on_view_changed(position)

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
        for index, column in enumerate(COLUMNS):
            table.setColumnWidth(index, column.width)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)

        table.selectionModel().currentRowChanged.connect(self._on_row_changed)

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
        for index, column in enumerate(COLUMNS):
            tree.setColumnWidth(index, column.width)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        tree.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._tree = tree
        return tree

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
        QShortcut(QKeySequence.StandardKey.Find, self, self._header.focus_search)
        QShortcut(QKeySequence.StandardKey.Refresh, self, self.reload_current)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self, self.open_about)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+L"), self, self.toggle_log)
        QShortcut(QKeySequence("Ctrl+N"), self, self.action_new_manual)
        QShortcut(QKeySequence.StandardKey.Print, self, self.print_preview)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_excel)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, self.export_pdf)

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
        self._calendar.set_month(self._year, self._month, timesheet, self._settings.federal_state)
        self._update_year_view(timesheet)
        self._sidebar.set_total(self._model.total_hours)
        self._update_summary(timesheet)
        self._detail.clear()

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

    def _update_summary(self, timesheet: Timesheet | None) -> None:
        """Fuellt die Summenleiste; Soll aus den Arbeitstagen des Zeitraums."""
        if timesheet is None:
            self._summary.show_timesheet(None, self._settings, 0)
            return
        target_workdays = HolidayService(self._settings.federal_state).count_workdays(
            timesheet.date_from, timesheet.date_to
        )
        self._summary.show_timesheet(timesheet, self._settings, target_workdays)

    # --- Manuelle Zeiten -----------------------------------------------

    def _entry_menu(self, entry: WorklogEntry | None, day: date | None) -> QMenu:
        """Baut das Rechtsklick-Menue fuer eine Zeile (Eintrag oder Tag)."""
        menu = QMenu(self)

        if entry is not None and entry.ticket and self._settings.jira_host:
            open_action = menu.addAction("Ticket im Browser öffnen")
            open_action.triggered.connect(lambda _checked=False, e=entry: self._open_ticket(e))
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
        for entry in timesheet.all_entries:
            month = entry.date.month
            hours[month] = hours.get(month, 0.0) + entry.hours
            entries[month] = entries.get(month, 0) + 1
        self._year_hours = hours
        self._year_entries = entries
        self._year_loaded_for = self._year
        self._year_view.set_year(
            self._year, hours, entries, self._settings.hours_per_day, self._settings.federal_state
        )
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
        self._apply_manual_color()
        self._update_empty_state()
        self._set_status("Einstellungen gespeichert")
        if self._settings.theme in ("dark", "light"):
            self._mode = Mode(self._settings.theme)
            self._header.apply_mode(self._mode)
            self.theme_changed.emit(self._settings.theme)

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
        self._calendar.set_month(self._year, self._month, self._timesheet, self._settings.federal_state)
        if self._settings_complete():
            self.load_month()

    def _on_view_changed(self, position: int) -> None:
        self._stack.setCurrentIndex(position)
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
        self._year_view.set_year(
            self._year,
            self._year_hours,
            self._year_entries,
            self._settings.hours_per_day,
            self._settings.federal_state,
        )

    def _on_day_selected(self, cell: DayCell) -> None:
        """Klick auf eine Kachel zeigt den ersten Eintrag des Tages."""
        if cell.entries:
            self._detail.show_entry(cell.entries[0])
            self._set_status(f"{cell.day:%d.%m.%Y}: {len(cell.entries)} Einträge")
        else:
            self._detail.clear()
            reason = cell.holiday or ("Wochenende" if cell.is_weekend else "keine Buchung")
            self._set_status(f"{cell.day:%d.%m.%Y}: {reason}")

    def _on_month_selected(self, month: int) -> None:
        """Klick auf eine Monatskachel wechselt dorthin und laedt."""
        self._month = month
        self._update_period_labels()
        self._sidebar.select_view(0)
        self._stack.setCurrentIndex(0)
        if self._settings_complete():
            self.load_month()

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
        # Die Symbole liegen je Erscheinungsbild in eigenen Dateien vor.
        self._header.apply_mode(self._mode)
        self._calendar.apply_mode(self._mode)
        self._year_view.apply_mode(self._mode)
        self._recolor_menu_icons()
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
        state = self._qsettings.value("window/state")
        if state is not None:
            # Stellt auch die Sichtbarkeit des Meldungsfensters wieder her.
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Merkt Fenstergroesse und Aufteilung, wartet auf den Arbeitsfaden."""
        self._qsettings.setValue("window/geometry", self.saveGeometry())
        self._qsettings.setValue("window/splitter", self._splitter.sizes())
        self._qsettings.setValue("window/state", self.saveState())
        if self._worker is not None and self._worker.isRunning():
            # Ohne das kann Qt beim Beenden ueber einen laufenden Faden stolpern.
            self._worker.wait(3000)
        super().closeEvent(event)
