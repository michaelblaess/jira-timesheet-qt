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
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QKeySequence, QShortcut, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
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
from jira_timesheet_qt.models.settings import ACCESS_FIELDS, Settings, normalize_color
from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry
from jira_timesheet_qt.services.anonymizer import (
    FAKE_HOST,
    anonymize_board,
    anonymize_timesheet,
    log_censor_map,
)
from jira_timesheet_qt.services.holiday_service import HolidayService
from jira_timesheet_qt.services.manual_entry_service import ManualEntryService
from jira_timesheet_qt.services.ticket_board import Board, Marker, Role
from jira_timesheet_qt.services.ticket_board import Ticket as BoardTicket
from jira_timesheet_qt.ui.about_dialog import AboutDialog
from jira_timesheet_qt.ui.calendar_view import CalendarView, DayCell
from jira_timesheet_qt.ui.cell_delegate import CellDelegate
from jira_timesheet_qt.ui.detail_dialog import TicketDetailDialog
from jira_timesheet_qt.ui.export_service import ExportService
from jira_timesheet_qt.ui.hero_background import HeroBackground
from jira_timesheet_qt.ui.icons import app_icon, load_icon
from jira_timesheet_qt.ui.jira_worker import WorklogWorker
from jira_timesheet_qt.ui.log_dock import Level, LogDock
from jira_timesheet_qt.ui.manual_entry_dialog import ManualEntryDialog
from jira_timesheet_qt.ui.menu import Command, CommandRegistry, MenuBuilder, MenuDefinition, missing_commands
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.summary_bar import SummaryBar, SummarySegment
from jira_timesheet_qt.ui.theme import SCALES, Mode, palette_for, set_accent, set_scale
from jira_timesheet_qt.ui.ticket_board_view import TicketBoardView
from jira_timesheet_qt.ui.ticket_board_worker import (
    MODE_ASSIGNED,
    MODE_RELEVANT,
    TicketBoardWorker,
    TicketStatsWorker,
    config_from,
)
from jira_timesheet_qt.ui.timesheet_model import ENTRY_ROLE, SORT_ROLE, TimesheetModel
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel
from jira_timesheet_qt.ui.toast import Toast
from jira_timesheet_qt.ui.year_view import YearView

_VIEWS = ("Liste", "Kalender", "Jahr", "Meine Tickets", "Relevante Tickets")

# Welche Stapelseite welche Ticket-Ansicht ist. Aus _VIEWS abgeleitet,
# damit eine neue Ansicht die Zuordnung nicht stillschweigend verschiebt.
_BOARD_MODES: dict[int, str] = {
    _VIEWS.index("Meine Tickets"): MODE_ASSIGNED,
    _VIEWS.index("Relevante Tickets"): MODE_RELEVANT,
}

# Farbe des Pile-of-Shame-Werts in der Statusleiste (Hex ohne #).
_SHAME_COLOR = "C0392B"

_MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _month_name(month: int) -> str:
    """Deutscher Monatsname zu einer Monatszahl von 1 bis 12."""
    return _MONTHS[month - 1] if 1 <= month <= len(_MONTHS) else ""


def _top_tickets(entries: list[WorklogEntry], limit: int = 3) -> list[tuple[str, float, WorklogEntry]]:
    """Tickets mit den meisten Stunden, absteigend - je (Nummer, Stunden, Eintrag).

    Der Eintrag ist der erste Worklog dieses Tickets und dient dem Detail-Dialog
    (die Ticket-Kopfdaten - Beschreibung, Status, Typ - sind fuer alle Worklogs
    desselben Tickets gleich).
    """
    hours: dict[str, float] = {}
    first: dict[str, WorklogEntry] = {}
    for entry in entries:
        if entry.ticket:
            hours[entry.ticket] = hours.get(entry.ticket, 0.0) + entry.hours
            first.setdefault(entry.ticket, entry)
    ranked = sorted(hours.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [(ticket, total, first[ticket]) for ticket, total in ranked]


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
        # Laufende Nummer je Abruf. Ein QThread laesst sich nicht abbrechen -
        # ein ueberholter Faden laeuft also zu Ende, sein Ergebnis wird aber
        # anhand dieser Nummer verworfen.
        self._load_generation = 0
        # Alle noch laufenden Faeden, auch die ueberholten. Beim Schliessen muss
        # auf jeden davon gewartet werden, sonst zerstoert Qt einen laufenden
        # Faden mitsamt dem Fenster.
        self._running_workers: list[QThread] = []
        # Je Ticket-Ansicht eine eigene Abruf-Nummer: beide laden
        # unabhaengig voneinander, ein Ergebnis darf das andere nicht
        # entwerten.
        self._board_generation: dict[str, int] = {MODE_ASSIGNED: 0, MODE_RELEVANT: 0}
        # Beim ersten Wechsel in einen Ticket-Reiter wird automatisch
        # geladen - wie in der Jahresansicht. Danach nur noch auf Zuruf
        # ueber die Werkzeugleiste.
        self._board_loaded: dict[str, bool] = {MODE_ASSIGNED: False, MODE_RELEVANT: False}
        # Die echten Ergebnisse. Die Ansicht zeigt im Screenshot-Modus
        # eine Dummy-Kopie - die Rohdaten bleiben hier, damit sich der
        # Modus verlustfrei zurueckschalten laesst.
        self._real_boards: dict[str, Board | None] = {
            MODE_ASSIGNED: None,
            MODE_RELEVANT: None,
        }
        # Angezeigter Stundenzettel (bei aktiver Anonymisierung die Dummy-Kopie).
        self._timesheet: Timesheet | None = None
        # Echte Rohdaten - bleiben erhalten, damit die Anonymisierung reversibel
        # ist. Monat und (separat geladenes) Jahr getrennt gehalten.
        self._real_ts: Timesheet | None = None
        self._year_ts: Timesheet | None = None
        # Screenshot-Modus: ersetzt Tickets, Texte, Autoren und Zugangsdaten in
        # allen Ansichten durch Dummy-Werte. Echte Daten bleiben im Cache.
        self._anonymize = False
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
        # Top-Tickets je Monat (Nummer, Stunden, Eintrag) - fuellen die Jahreskacheln.
        self._year_top: dict[int, list[tuple[str, float, WorklogEntry]]] = {}
        # Fuer welches Jahr die Jahresansicht zuletzt vollstaendig geladen wurde.
        self._year_loaded_for: int | None = None
        # True, waehrend Spaltenbreiten programmatisch gesetzt werden - verhindert,
        # dass die eigene sectionResized-Reaktion sie faelschlich als Nutzerbreite
        # speichert.
        self._adjusting_columns = False

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
        # Gemerkter Auf-/Zuklapp-Zustand der gruppierten Ansicht - ueberlebt
        # Monatswechsel und das Speichern der Einstellungen (Modell-Reset).
        self._groups_collapsed = bool(self._qsettings.value("groups_collapsed", False, type=bool))

        # Inline-Aenderungen an manuellen Eintraegen persistieren.
        self._model.manual_edited.connect(self._persist_inline_edit)
        self._tree_model.manual_edited.connect(self._persist_inline_edit)

        # Spalten-Konfiguration aus den Einstellungen in die Modelle uebernehmen,
        # BEVOR die Ansichten gebaut werden - sonst zeigt der erste Aufbau die
        # Standard-Spalten statt der konfigurierten.
        self._model.set_columns(self._settings.export_columns, self._settings.default_customer)
        self._tree_model.set_columns(self._settings.export_columns, self._settings.default_customer)

        # Einfaerbung manueller Eintraege und die Soll-Ist-Ampel der Tagessummen
        # aus den Einstellungen uebernehmen.
        self._apply_manual_color()
        self._apply_day_total_colors()

        self._build_ui()
        # Erneut, jetzt existiert die Summenleiste - damit auch ihr Ist-Wert die
        # Soll-Ist-Ampel bekommt (der Aufruf vor dem Bau konnte sie nicht setzen).
        self._apply_day_total_colors()
        self._install_shortcuts()
        self._restore_geometry()
        self._update_period_labels()
        # Zuletzt, und nach restoreState: ein hide() vor dem ersten Anzeigen
        # des Fensters haelt nicht, sobald danach noch etwas ins Fenster
        # geschrieben wird - der Bildlauf hebt das Verstecken wieder auf.
        self._log.setVisible(self._settings.log_visible)

        # Fehlt der Zugang, aber eine Sicherung hat ihn: nach dem Anzeigen des
        # Fensters ANBIETEN (nicht still heilen) - deferred, damit der modale
        # Dialog erst nach dem ersten Zeichnen kommt.
        QTimer.singleShot(0, self._maybe_offer_restore)

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
        # Klick auf eine Ticketnummer in der Kachel oeffnet genau diesen Eintrag.
        self._calendar.ticket_activated.connect(self._show_detail)

        self._year_view = YearView(self._mode)
        self._year_view.month_selected.connect(self._on_month_selected)
        # Klick auf eine Top-Ticketnummer in einer Jahreskachel oeffnet den Eintrag.
        self._year_view.ticket_activated.connect(self._show_detail)

        self._assigned_board = TicketBoardView(
            "Meine Tickets", with_charts=True, mode=self._mode
        )
        self._assigned_board.detail_requested.connect(self._show_detail)
        self._assigned_board.report_requested.connect(self.open_ticket_report)
        self._relevant_board = TicketBoardView("Relevante Tickets")
        self._relevant_board.detail_requested.connect(self._show_detail)
        self._relevant_board.report_requested.connect(self.open_ticket_report)
        self._apply_board_settings()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._list_stack)
        self._stack.addWidget(self._calendar)
        self._stack.addWidget(self._year_view)
        self._stack.addWidget(self._assigned_board)
        self._stack.addWidget(self._relevant_board)
        outer.addWidget(self._stack, 1)

        self._summary = SummaryBar(self._mode)

        self.setCentralWidget(central)

        # Echte QStatusBar mit Panels: links die ansichtsabhaengige Summenleiste
        # (Fortschritt + Kennzahlen) ueber die volle Breite, rechts als dauerhaftes
        # Panel der Eintrags-/Stunden-Zaehler, ganz rechts der Groessengriff.
        self._status = QLabel("Bereit")
        self._status.setObjectName("StatusBar")
        self._status.setContentsMargins(12, 5, 12, 5)
        # Deutlich sichtbares Kennzeichen des Screenshot-Modus - nur eingeblendet,
        # solange anonymisiert wird.
        self._anon_badge = QLabel(t("subtitle.anonymized"))
        self._anon_badge.setObjectName("AnonBadge")
        self._anon_badge.setContentsMargins(10, 3, 10, 3)
        self._anon_badge.setVisible(False)
        # Unbestimmter Fortschrittsbalken: ein Abruf kann je nach Leitung
        # und Ticketzahl eine Minute dauern, und eine leere Maske ohne jedes
        # Lebenszeichen sieht aus wie ein Absturz. Bereich 0..0 heisst "laeuft,
        # Dauer unbekannt" - eine Prozentzahl waere hier erfunden.
        self._busy = QProgressBar()
        self._busy.setObjectName("BusyBar")
        self._busy.setRange(0, 0)
        self._busy.setTextVisible(False)
        self._busy.setFixedWidth(120)
        self._busy.setVisible(False)

        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(True)
        status_bar.addWidget(self._summary, 1)
        status_bar.addPermanentWidget(self._anon_badge)
        status_bar.addPermanentWidget(self._busy)
        status_bar.addPermanentWidget(self._status)
        self.setStatusBar(status_bar)

        # Schwebende Kurzmeldung (Toast) ueber den Ansichten, unten rechts.
        self._toast = Toast(central)

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

        # Erklaerender Tooltip fuer den Screenshot-Modus (Menue und Toolbar teilen
        # sich die eine QAction, der Builder setzt selbst keinen Tooltip).
        anon_action = self._commands.get("view.anonymize").action
        if anon_action is not None:
            anon_action.setToolTip(t("tooltip.anonymize"))

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
        add(Command("view.anonymize", run=self._toggle_anonymize,
                    is_checked=lambda: self._anonymize))
        add(Command("view.theme", run=self._toggle_theme))
        add(Command("export.excel", run=self.export_excel))
        add(Command("export.pdf", run=self.export_pdf))
        add(Command("export.print", run=self.print_preview))
        add(Command("tools.ticket_report", run=self.open_ticket_report))
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
        header.sectionResized.connect(
            lambda index, _old, new: self._on_section_resized(self._model, index, new)
        )
        # Auf Viewport-Groessenaenderung reagieren, um die Beschreibung zu fuellen.
        table.viewport().installEventFilter(self)

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)

        table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        table.doubleClicked.connect(self._on_row_activated)

        # Hebt den aktuellen Suchbegriff in den Zellen hervor.
        self._cell_delegate = CellDelegate(table)
        table.setItemDelegate(self._cell_delegate)

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
        tree.setItemDelegate(self._cell_delegate)

        header = tree.header()
        header.setHighlightSections(False)
        header.setSectionsMovable(True)
        self._apply_column_layout(tree, self._tree_model)
        header.sectionResized.connect(
            lambda index, _old, new: self._on_section_resized(self._tree_model, index, new)
        )
        tree.viewport().installEventFilter(self)

        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        tree.selectionModel().currentRowChanged.connect(self._on_row_changed)
        tree.doubleClicked.connect(self._on_row_activated)
        self._tree = tree
        return tree

    @staticmethod
    def _header_of(view: QTableView | QTreeView) -> QHeaderView:
        """Liefert den horizontalen Kopf einer Tabelle bzw. eines Baums."""
        return view.horizontalHeader() if isinstance(view, QTableView) else view.header()

    def _apply_column_layout(self, view: QTableView | QTreeView, model: TimesheetModel | TimesheetTreeModel) -> None:
        """Macht alle Spalten frei ziehbar und setzt ihre Breiten.

        Jede Spalte ist Interactive - also vom Nutzer ziehbar, auch die
        Beschreibung. Die letzte Spalte wird nicht zwangsgestreckt (das haette
        sie fixiert). Gespeicherte Nutzerbreiten (nach Spaltenschluessel) gehen
        den Vorgaben vor. Anschliessend fuellt die Beschreibungs-Spalte die freie
        Restbreite, bleibt dabei aber ziehbar.
        """
        header = self._header_of(view)
        header.setStretchLastSection(False)
        keys = model.column_keys()
        self._adjusting_columns = True
        try:
            for section in range(model.columnCount()):
                header.setSectionResizeMode(section, QHeaderView.ResizeMode.Interactive)
                saved = self._settings.column_widths.get(keys[section]) if section < len(keys) else None
                view.setColumnWidth(section, saved if saved and saved > 0 else model.column_width(section))
        finally:
            self._adjusting_columns = False
        self._fill_description(view, model)

    def _fill_description(self, view: QTableView | QTreeView, model: TimesheetModel | TimesheetTreeModel) -> None:
        """Gibt der Beschreibungs-Spalte die freie Restbreite der Ansicht.

        Nur solange der Nutzer die Beschreibung nicht selbst gezogen hat - eine
        gespeicherte Breite bleibt unangetastet. So sieht die Liste ohne leeren
        rechten Rand aus, ist aber trotzdem ueberall frei ziehbar.
        """
        stretch = model.stretch_column()
        if stretch < 0:
            return
        keys = model.column_keys()
        if stretch < len(keys) and self._settings.column_widths.get(keys[stretch]):
            return
        used = sum(view.columnWidth(s) for s in range(model.columnCount()) if s != stretch)
        available = view.viewport().width() - used
        if available <= model.column_width(stretch):
            return
        self._adjusting_columns = True
        try:
            view.setColumnWidth(stretch, available)
        finally:
            self._adjusting_columns = False

    def _on_section_resized(
        self, model: TimesheetModel | TimesheetTreeModel, index: int, width: int
    ) -> None:
        """Merkt eine vom Nutzer gezogene Spaltenbreite (nach Spaltenschluessel)."""
        if self._adjusting_columns or width <= 0:
            return
        keys = model.column_keys()
        if 0 <= index < len(keys):
            self._settings.column_widths[keys[index]] = width

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
        self._cell_delegate.set_needle(text)
        # Neu zeichnen, damit die Hervorhebung sofort erscheint bzw. verschwindet.
        self._table.viewport().update()
        self._tree.viewport().update()
        # Bei aktiver Suche die Gruppen aufklappen, damit Treffer sichtbar sind.
        if self._grouped and text:
            self._tree.expandAll()
        # Die Suche gilt fuer die gerade sichtbare Ansicht - auch fuer die
        # Ticket-Reiter. Beide werden gesetzt, damit der Filter beim
        # Reiterwechsel nicht ueberraschend verschwindet.
        self._assigned_board.set_search(text)
        self._relevant_board.set_search(text)

    def _build_empty_state(self) -> QWidget:
        """Zustand ohne Daten - formatfuellendes Hintergrundbild, Inhalt in einer Karte.

        Das Bild fuellt die gesamte Flaeche (cover, nie verzerrt), der erklaerende
        Text steht in einer lesbaren Karte darueber. Ist kein Bild hinterlegt,
        bleibt der Theme-Hintergrund und die Karte traegt das App-Icon.
        """
        images_dir = Path(__file__).resolve().parent.parent / "resources" / "images"
        hero_path = next(
            (images_dir / name for name in ("hero.jpg", "hero.png", "hero.jpeg") if (images_dir / name).is_file()),
            None,
        )
        page = HeroBackground(hero_path)

        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("EmptyCard")
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(44, 34, 44, 34)
        layout.setSpacing(10)

        # App-Icon nur ohne Hintergrundbild - das Bild traegt die Marke sonst selbst.
        if not page.has_image():
            icon = app_icon()
            if not icon.isNull():
                icon_label = QLabel()
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_label.setPixmap(icon.pixmap(72, 72))
                layout.addWidget(icon_label)

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

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
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

    def _apply_day_total_colors(self) -> None:
        """Setzt die Soll-Ist-Ampel der Tagessummen in beiden Listenmodellen.

        Ueber der Soll-Stundenzahl gruen, darunter rot. Ist die Faerbung
        abgeschaltet, faerbt None die Summen wieder normal ein.
        """
        over_hex = under_hex = None
        over: QColor | None = None
        under: QColor | None = None
        if self._settings.color_day_totals:
            over_hex = normalize_color(self._settings.day_over_color)
            under_hex = normalize_color(self._settings.day_under_color)
            over = QColor(f"#{over_hex}")
            under = QColor(f"#{under_hex}")
        target = self._settings.hours_per_day
        self._model.set_day_total_colors(over, under, target)
        self._tree_model.set_day_total_colors(over, under, target)
        # Dieselbe Ampel faerbt den Ist-Wert in der Summenleiste (Ist vs. Soll).
        if hasattr(self, "_summary"):
            self._summary.set_day_colors(over_hex, under_hex)

    def set_timesheet(self, timesheet: Timesheet | None) -> None:
        """Uebernimmt einen Stundenzettel in alle Ansichten.

        Die echten Daten werden festgehalten; angezeigt wird bei aktivem
        Screenshot-Modus die anonymisierte Kopie.
        """
        self._real_ts = timesheet
        timesheet = self._display_ts(timesheet)
        self._timesheet = timesheet
        self._model.set_timesheet(timesheet)
        self._tree_model.set_timesheet(timesheet)
        self._apply_group_state()
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
            self._apply_group_state()
        self._list_stack.setCurrentIndex(self._list_page(self._model.rowCount() > 0))

    def _apply_group_state(self) -> None:
        """Klappt die gruppierte Ansicht gemaess gemerktem Zustand auf oder zu."""
        if self._groups_collapsed:
            self._tree.collapseAll()
        else:
            self._tree.expandAll()

    def _toggle_group_state(self) -> None:
        """Kippt zwischen Alle-aufklappen und Alle-zuklappen und merkt sich das."""
        self._groups_collapsed = not self._groups_collapsed
        self._qsettings.setValue("groups_collapsed", self._groups_collapsed)
        self._apply_group_state()

    def _refresh_summary_bar(self) -> None:
        """Fuellt die Summenleiste passend zur aktiven Ansicht."""
        view = self._stack.currentIndex()
        mode = _BOARD_MODES.get(view)
        if mode is not None:
            self._summary_board(self._board_view(mode), mode)
        elif view == 1:
            self._summary_calendar()
        elif view == 2:
            self._summary_year()
        else:
            self._summary_list()

    def _summary_board(self, view: TicketBoardView, mode: str) -> None:
        """Ticket-Ansicht: die Zahlen, die eine Entscheidung tragen.

        Bewusst nicht die Summen der Stundenliste - Ist, Soll und Umsatz
        haben mit einer Ticketliste nichts zu tun und waren dort schlicht
        falsch.

        Args:
            view:
                Die anzuzeigende Ansicht.
            mode:
                Welche der beiden Ansichten es ist.
        """
        board = view.board
        if board is None:
            self._summary.clear()
            return

        def zahl(marker: Marker) -> int:
            return len(board.with_marker(marker))

        backlog = sum(g.count for g in board.groups if g.role is Role.BACKLOG)
        segments = [SummarySegment("Tickets", str(board.count))]

        shame = zahl(Marker.PILE_OF_SHAME)
        if mode == MODE_ASSIGNED:
            segments.append(
                SummarySegment(
                    "Pile of Shame",
                    str(shame),
                    # Nur einfaerben, wenn es etwas zu faerben gibt - eine
                    # rote Null ist ein Fehlalarm.
                    _SHAME_COLOR if shame else None,
                    "Status behauptet Aktivität, aber weder Änderung noch gebuchte Stunde.",
                )
            )
        segments += [
            SummarySegment("Rückgabe", str(zahl(Marker.HANDBACK)),
                           tooltip="Ausgeliefert, fremder Autor - gehört zurückgegeben."),
            SummarySegment("Nachhaken", str(zahl(Marker.ACCEPTANCE)),
                           tooltip="Wartet auf Freigabe durch jemand anderen."),
            SummarySegment("Backlog", str(backlog), tooltip="Bereit zum Ziehen."),
        ]

        oldest = max((t.idle_workdays for t in board.tickets), default=0.0)
        segments.append(
            SummarySegment("Älteste", f"{oldest:.0f} AT",
                           tooltip="Arbeitstage seit der letzten Änderung.")
        )
        if mode == MODE_RELEVANT and self._settings.board_window_days > 0:
            segments.append(
                SummarySegment("Fenster", f"{self._settings.board_window_days} Tage")
            )
        if board.unknown_status:
            # Sichtbar, aber knapp: die Namen stehen im Hinweis unter der Maus.
            segments.append(
                SummarySegment(
                    "ohne Zuordnung",
                    str(len(board.unknown_status)),
                    tooltip="Status ohne Rollenzuordnung: "
                    + ", ".join(board.unknown_status)
                    + "\nZuordnen unter Einstellungen -> Tickets.",
                )
            )
        self._summary.show_board(segments)

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
        """Jahr: Ist/Soll/Verbleibend/Prognose, manueller Anteil und Umsatz-Summen."""
        summary = self._year_view.summary
        manual = sum(self._year_manual.values())
        self._summary.show_year(
            summary.actual,
            summary.target,
            summary.forecast,
            manual=manual,
            hourly_rate=self._settings.hourly_rate,
            vat_rate=self._settings.vat_rate,
        )

    # --- Manuelle Zeiten -----------------------------------------------

    def _entry_menu(self, entry: WorklogEntry | None, day: date | None) -> QMenu:
        """Baut das Rechtsklick-Menue fuer eine Zeile (Eintrag oder Tag)."""
        menu = QMenu(self)

        if entry is not None:
            detail_action = menu.addAction(t("menu.details"))
            detail_action.triggered.connect(lambda _checked=False, e=entry: self._show_detail(e))

        if entry is not None and entry.ticket and self._settings.jira_host:
            open_action = menu.addAction(t("menu.open_ticket"))
            open_action.triggered.connect(lambda _checked=False, e=entry: self._open_ticket(e))

        if entry is not None and entry.ticket and self._settings.jira_host and self._settings.jira_token:
            report_action = menu.addAction(t("menu.ticket_report"))
            report_action.triggered.connect(
                lambda _checked=False, e=entry: self.open_ticket_report(e.ticket)
            )

        if entry is not None:
            menu.addSeparator()

        new_action = menu.addAction(t("menu.manual_new"))
        new_action.triggered.connect(lambda _checked=False, d=day: self.action_new_manual(d))

        if entry is not None and entry.manual and entry.manual_id > 0:
            edit_action = menu.addAction(t("menu.manual_edit"))
            edit_action.triggered.connect(lambda _checked=False, e=entry: self._edit_manual(e))
            delete_action = menu.addAction(t("menu.manual_delete"))
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
        menu = self._entry_menu(entry, day)
        menu.addSeparator()
        toggle = menu.addAction("Alle aufklappen" if self._groups_collapsed else "Alle zuklappen")
        toggle.triggered.connect(lambda _checked=False: self._toggle_group_state())
        menu.exec(self._tree.viewport().mapToGlobal(pos))

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
        host = self._display_host().rstrip("/")
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

    def _maybe_offer_restore(self) -> None:
        """Bietet an, einen verlorenen Zugang aus einer Sicherung zu holen.

        Nur wenn der Zugang tatsaechlich fehlt UND eine Sicherung ihn hat -
        beim echten Erststart (keine Sicherung) passiert nichts. Bewusst mit
        Rueckfrage statt stiller Wiederherstellung.
        """
        if self._settings_complete():
            return
        backup = Settings.latest_access_backup()
        if backup is None:
            return
        label, data = backup
        reply = QMessageBox.question(
            self,
            "Jira-Zugang wiederherstellen",
            f"Der gespeicherte Jira-Zugang fehlt. Aus der Sicherung ({label}) wiederherstellen?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for name in ACCESS_FIELDS:
            if name in data:
                setattr(self._settings, name, data[name])
        self._settings.save()
        self._update_empty_state()
        self.show_toast("Jira-Zugang wiederhergestellt")
        self._set_status(f"Zugang wiederhergestellt (Sicherung {label})")

    # --- Abruf ----------------------------------------------------------

    def load_month(self) -> None:
        """Holt die Buchungen des eingestellten Monats aus Jira."""
        if not self._settings_complete():
            self._set_status("Zugang unvollständig - bitte Host, E-Mail und Token hinterlegen.", "error")
            self.open_settings()
            return

        first = date(self._year, self._month, 1)
        last = date(self._year, self._month, calendar.monthrange(self._year, self._month)[1])
        self._start_worker(
            first,
            last,
            self._on_loaded,
            f"Lade {_month_name(self._month)} {self._year} ...",
        )

    # --- Ticket-Ansichten -----------------------------------------------

    def _apply_board_settings(self) -> None:
        """Meldet den Ticket-Ansichten, was die Zugangsdaten hergeben.

        Die Ticket-Analyse braucht Host und Token. Fehlen sie, bleibt der
        Menuepunkt sichtbar, aber ausgegraut - so ist das Menue an jeder
        Zeile gleich aufgebaut und der Anwender sieht, dass es die
        Funktion gibt.
        """
        available = bool(self._settings.jira_host and self._settings.jira_token)
        for view in (self._assigned_board, self._relevant_board):
            view.set_report_available(available)
            view.set_anonymized(self._anonymize)

    def _invalidate_boards(self) -> None:
        """Verwirft die geladenen Ticket-Ansichten nach einer Aenderung.

        Die Statuszuordnung kann sich geaendert haben - dann muss neu
        gruppiert werden, und das geht nur ueber einen frischen Abruf.
        Die gerade sichtbare Ansicht laedt sofort, die andere beim
        naechsten Besuch.
        """
        self._board_loaded = {MODE_ASSIGNED: False, MODE_RELEVANT: False}
        mode = _BOARD_MODES.get(self._stack.currentIndex())
        if mode is not None and self._settings_complete():
            self._load_board(mode)

    def _board_view(self, mode: str) -> TicketBoardView:
        """Liefert die Ansicht zu einem Abrufmodus."""
        return self._assigned_board if mode == MODE_ASSIGNED else self._relevant_board

    def _load_board(self, mode: str) -> None:
        """Startet den Abruf einer Ticket-Ansicht.

        Jede Ansicht fuehrt eine eigene Abruf-Nummer: beide laden unabhaengig
        voneinander, und das Ergebnis der einen darf das der anderen nicht
        entwerten. Ein ueberholter Faden laeuft zu Ende - ein QThread laesst
        sich nicht abbrechen -, sein Ergebnis wird aber verworfen.

        Args:
            mode:
                MODE_ASSIGNED oder MODE_RELEVANT.
        """
        if not self._settings_complete():
            self._set_status(
                "Zugangsdaten fehlen - bitte zuerst die Einstellungen ausfüllen.", "error"
            )
            return

        self._board_generation[mode] = self._board_generation.get(mode, 0) + 1
        generation = self._board_generation[mode]

        self._set_status("Tickets werden geladen ...", "busy")
        self._board_view(mode).set_loading()
        worker = TicketBoardWorker(self._settings, config_from(self._settings), mode, self)
        worker.progress.connect(
            lambda text, m=mode, g=generation: self._on_board_progress(text, m, g)
        )
        # Die JQL-Ausdruecke gehoeren ins Meldungsfenster: dort lassen sie sich
        # kopieren und nachvollziehen. In der Statuszeile schoben sie alles
        # andere weg.
        worker.log.connect(self._log.write)
        worker.finished_ok.connect(
            lambda board, m=mode, g=generation: self._on_board_loaded(board, m, g)
        )
        worker.failed.connect(
            lambda message, m=mode, g=generation: self._on_board_failed(message, m, g)
        )
        worker.finished.connect(worker.deleteLater)
        self._running_workers.append(worker)
        worker.start()

    def _load_statistics(self) -> None:
        """Holt die Zahlen fuer die Diagramme.

        Eine eigene Abfrage ueber die ganze Historie, im Anschluss an die
        Liste. Sie ist klein und schnell - das Ergebnis steht dauerhaft
        unter der Tabelle und muss zur gezeigten Lage passen.
        """
        if not self._settings_complete():
            return
        self._set_status("Auswertung wird geladen ...", "busy")
        worker = TicketStatsWorker(self._settings, self)
        worker.log.connect(self._log.write)
        worker.finished_ok.connect(self._on_statistics)
        worker.failed.connect(lambda message: self._set_status(message, "error"))
        worker.finished.connect(worker.deleteLater)
        self._running_workers.append(worker)
        worker.start()

    def _on_statistics(self, stats: object) -> None:
        """Uebernimmt die ausgewerteten Zahlen in die Diagramme."""
        self._running_workers = [w for w in self._running_workers if w.isRunning()]
        self._assigned_board.set_statistics(stats)
        self._set_status("Auswertung geladen")

    def _board_is_current(self, mode: str, generation: int) -> bool:
        """Prueft, ob ein Ergebnis noch zur juengsten Anforderung gehoert."""
        return generation == self._board_generation.get(mode, 0)

    def _on_board_progress(self, text: str, mode: str, generation: int) -> None:
        """Zwischenmeldung eines laufenden Abrufs."""
        if not self._board_is_current(mode, generation):
            return
        self._set_status(text, "busy")

    def _on_board_loaded(self, board: object, mode: str, generation: int) -> None:
        """Uebernimmt ein fertiges Ergebnis."""
        self._running_workers = [w for w in self._running_workers if w.isRunning()]
        if not self._board_is_current(mode, generation):
            return
        view = self._board_view(mode)
        if isinstance(board, Board):
            self._real_boards[mode] = board
            view.set_board(self._display_board(board))
            self._board_loaded[mode] = True
            self._refresh_summary_bar()
            self._set_status(f"{board.count} Tickets geladen")
            if mode == MODE_ASSIGNED:
                # Die Auswertung steht dauerhaft unter der Liste - sie muss
                # zur gerade geladenen Lage passen.
                self._load_statistics()
            if board.unknown_status:
                # Nicht zugeordnete Status duerfen nicht still in einem
                # Sammeltopf verschwinden - sonst merkt niemand, dass die
                # Konfiguration nachzuziehen ist.
                self._log.write(
                    "Status ohne Zuordnung: " + ", ".join(board.unknown_status),
                    Level.WARNING,
                )

    def _on_board_failed(self, message: str, mode: str, generation: int) -> None:
        """Meldet einen gescheiterten Abruf in der Ansicht und im Protokoll."""
        self._running_workers = [w for w in self._running_workers if w.isRunning()]
        if not self._board_is_current(mode, generation):
            return
        self._set_status(message, "error")
        self._board_view(mode).set_failed(message)
        self._log.write(message, Level.ERROR)

    def _start_worker(
        self,
        first: date,
        last: date,
        on_ok: Callable[[Timesheet, int], None],
        status: str,
    ) -> None:
        """Startet einen Abruf und entwertet einen eventuell laufenden.

        Frueher kehrte der Lader bei laufendem Faden wortlos zurueck: Ein
        Zeitraumwechsel mitten im Abruf wurde stillschweigend verschluckt, und
        das spaeter eintreffende Ergebnis landete in einer Ansicht, die
        laengst einen anderen Monat zeigte. Ein QThread laesst sich nicht
        abbrechen, deshalb laeuft der ueberholte Faden zu Ende - sein Ergebnis
        wird aber anhand der Abruf-Nummer verworfen.
        """
        self._load_generation += 1
        generation = self._load_generation

        self._set_status(status, "busy")
        worker = WorklogWorker(self._settings, first, last, self)
        worker.progress.connect(lambda text, g=generation: self._on_progress(text, g))
        # Ausfuehrliches (die JQL-Ausdruecke) nur ins Meldungsfenster.
        worker.log.connect(self._log.write)
        worker.finished_ok.connect(lambda ts, g=generation: on_ok(ts, g))
        worker.failed.connect(lambda msg, g=generation: self._on_failed(msg, g))
        worker.finished.connect(lambda g=generation: self._on_worker_done(g))
        # Ueberholte Faeden geben sich nach ihrem Ende selbst frei, sonst
        # sammeln sie sich als Kinder des Fensters an.
        worker.finished.connect(worker.deleteLater)
        self._running_workers.append(worker)
        self._worker = worker
        worker.start()

    def _is_current(self, generation: int | None) -> bool:
        """Gehoert eine Rueckmeldung noch zum juengsten Abruf?"""
        return generation is None or generation == self._load_generation

    def _on_progress(self, text: str, generation: int | None = None) -> None:
        """Fortschritt eines Abrufs - der eines ueberholten wird verworfen."""
        if not self._is_current(generation):
            return
        self._set_status(text, "busy")

    def _on_loaded(self, timesheet: Timesheet, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self.set_timesheet(timesheet)
        # Rechts in der Statusleiste steht der Verbindungszustand, nicht die
        # Summe - die Stunden zeigt schon die Kennzahlen-Leiste in der Mitte.
        self._set_status(f"Verbunden mit {self._host_label()}")

    def _on_failed(self, message: str, generation: int | None = None) -> None:
        if not self._is_current(generation):
            return
        self.set_timesheet(None)
        self._set_status(message, "error")

    def _display_host(self) -> str:
        """Der anzuzeigende Jira-Host - im Screenshot-Modus der Dummy-Host."""
        if self._anonymize:
            return FAKE_HOST
        return self._settings.jira_host

    def _host_label(self) -> str:
        """Der Jira-Host ohne Schema und Schraegstrich, fuer die Statusmeldung."""
        host = self._display_host().strip()
        for prefix in ("https://", "http://"):
            if host.startswith(prefix):
                host = host[len(prefix) :]
        return host.rstrip("/") or "Jira"

    # --- Anonymisierung (Screenshot-Modus) ------------------------------

    def _display_ts(self, timesheet: Timesheet | None) -> Timesheet | None:
        """Liefert im Screenshot-Modus die Dummy-Kopie, sonst die Rohdaten."""
        if timesheet is None or not self._anonymize:
            return timesheet
        return anonymize_timesheet(timesheet)

    def _display_board(self, board: Board | None) -> Board | None:
        """Liefert im Screenshot-Modus die Dummy-Kopie, sonst die Rohdaten."""
        if board is None or not self._anonymize:
            return board
        return anonymize_board(board)

    def _toggle_anonymize(self) -> None:
        """Schaltet den Screenshot-Modus (Dummy-Daten) an oder aus.

        Tickets, Ticket-Texte, Autoren und der Jira-Host werden in allen
        Ansichten und im Meldungsfenster durch Dummy-Werte ersetzt. Die echten
        Daten bleiben erhalten und kehren beim erneuten Umschalten zurueck.
        """
        self._anonymize = not self._anonymize
        self._anon_badge.setVisible(self._anonymize)
        # Meldungsfenster zensieren bzw. wieder Klartext zeigen.
        self._log.set_censor(
            log_censor_map(self._settings.email, self._settings.jira_host) if self._anonymize else {}
        )
        # Ansichten aus den echten Rohdaten neu aufbauen - jetzt (ent)anonymisiert.
        if self._real_ts is not None:
            self.set_timesheet(self._real_ts)
        if self._year_ts is not None and self._year_loaded_for == self._year:
            self._aggregate_year(self._display_ts(self._year_ts))
        # Die Ticket-Ansichten ebenfalls aus den echten Rohdaten neu aufbauen.
        for mode, real in self._real_boards.items():
            view = self._board_view(mode)
            view.set_anonymized(self._anonymize)
            if real is not None:
                view.set_board(self._display_board(real))
        self._refresh_summary_bar()
        # Verbindungszustand mit dem nun ggf. verschleierten Host neu schreiben.
        if self._real_ts is not None or self._year_ts is not None:
            self._set_status(f"Verbunden mit {self._host_label()}")
        self.show_toast(t("notify.anonymized" if self._anonymize else "notify.deanonymized"))
        self._commands.refresh("view.anonymize")

    def _on_worker_done(self, generation: int | None = None) -> None:
        """Ein Faden ist fertig - der juengste gibt den Platz frei."""
        self._running_workers = [w for w in self._running_workers if w.isRunning()]
        if not self._is_current(generation):
            return  # ein ueberholter Faden - der aktuelle laeuft weiter
        self._worker = None

    def load_year(self) -> None:
        """Holt alle zwoelf Monate des Jahres in einem einzigen Bereichs-Abruf."""
        if not self._settings_complete():
            self._set_status("Zugang unvollständig - bitte Host, E-Mail und Token hinterlegen.", "error")
            self.open_settings()
            return
        self._start_worker(
            date(self._year, 1, 1),
            date(self._year, 12, 31),
            self._on_year_loaded,
            f"Lade Jahr {self._year} ...",
        )

    def _on_year_loaded(self, timesheet: Timesheet, generation: int | None = None) -> None:
        """Aggregiert einen Jahres-Stundenzettel in die zwoelf Monatskacheln."""
        if not self._is_current(generation):
            return
        self._year_ts = timesheet
        self._aggregate_year(self._display_ts(timesheet))
        self._set_status(f"Verbunden mit {self._host_label()}")

    def _aggregate_year(self, timesheet: Timesheet | None) -> None:
        """Fuellt die Jahreskacheln aus einem (ggf. anonymisierten) Jahres-Zettel."""
        if timesheet is None:
            return
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
        by_month: dict[int, list[WorklogEntry]] = {}
        for entry in timesheet.all_entries:
            by_month.setdefault(entry.date.month, []).append(entry)
        top = {month: _top_tickets(es) for month, es in by_month.items()}
        self._year_hours = hours
        self._year_entries = entries
        self._year_booked = booked
        self._year_manual = manual
        self._year_top = top
        self._year_loaded_for = self._year
        self._year_view.set_year(
            self._year, hours, entries, self._settings.hours_per_day, self._settings.federal_state,
            booked_days_by_month=booked, manual_by_month=manual, top_tickets_by_month=top,
        )
        self._refresh_summary_bar()

    def reload_current(self) -> None:
        """Laedt die AKTIVE Ansicht neu.

        Der Befehl heisst "Aktualisieren" und muss deshalb das aktualisieren,
        was der Anwender gerade sieht - sonst laedt er den Monat neu, waehrend
        er auf eine Ticketliste schaut.
        """
        position = self._stack.currentIndex()
        mode = _BOARD_MODES.get(position)
        if mode is not None:
            self._load_board(mode)
            return
        if position == 2:
            self._year_loaded_for = None
            self.load_year()
            return
        self.load_month()

    def _set_status(self, text: str, state: str = "") -> None:
        """Schreibt in Statuszeile und Meldungsfenster.

        Die Statuszeile zeigt nur den letzten Stand, das Meldungsfenster den
        ganzen Verlauf - bei einem fehlgeschlagenen Abruf braucht man beides.

        Der Zustand "busy" blendet zugleich den Fortschrittsbalken ein. Das
        haengt bewusst hier und nicht an den einzelnen Ladepfaden: so bekommt
        JEDER Abruf - Monat, Jahr und die Ticket-Ansichten - dieselbe Anzeige,
        auch ein spaeter hinzukommender.

        Args:
            text:
                Der anzuzeigende Stand.
            state:
                "busy", "error" oder leer.
        """
        self._log.write(text, _LEVELS.get(state, Level.INFO))
        self._busy.setVisible(state == "busy")
        self._status.setText(text)
        self._status.setProperty("state", state)
        style = self._status.style()
        style.unpolish(self._status)
        style.polish(self._status)

    def log_message(self, text: str) -> None:
        """Schreibt eine Meldung ins Meldungsfenster, ohne die Statuszeile.

        Fuer ausfuehrliche Ausgaben aus Dialogen - etwa die JQL-Ausdruecke
        der Ticket-Analyse. Sie gehoeren in den Verlauf, aber nicht in
        eine einzeilige Anzeige.

        Args:
            text:
                Die Meldung.
        """
        self._log.write(text)

    def show_toast(self, text: str) -> None:
        """Zeigt eine kurze, selbst verschwindende Benachrichtigung unten rechts."""
        icon = qta.icon("mdi6.check-circle", color=palette_for(self._mode).green).pixmap(24, 24)
        self._toast.show_message(text, icon)

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
        self._apply_day_total_colors()
        self._apply_board_settings()
        # Der Modell-Reset beim Anwenden klappt den Baum zu - gemerkten Zustand
        # wiederherstellen, sonst steht die gruppierte Liste voellig eingeklappt.
        self._apply_group_state()
        self._update_empty_state()
        self._set_status("Einstellungen gespeichert")
        self.show_toast("Einstellungen gespeichert")
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

    def open_ticket_report(self, ticket: str = "") -> None:
        """Oeffnet die Ticket-Analyse.

        Der Dialog holt die Ticketdaten selbst und schreibt den Bericht als
        HTML-Datei - der Stundenzettel bleibt davon unberuehrt.

        Args:
            ticket:
                Vorbelegung des Eingabefelds. Aus dem Kontextmenue kommt hier
                das Ticket der angeklickten Zeile.
        """
        from jira_timesheet_qt.ui.ticket_analysis_dialog import TicketAnalysisDialog

        TicketAnalysisDialog(self._settings, self, ticket=ticket).exec()

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
        # Ticket-Reiter: beim ersten Besuch laden, danach nur auf Zuruf.
        mode = _BOARD_MODES.get(position)
        if mode is not None and not self._board_loaded[mode] and self._settings_complete():
            self._load_board(mode)

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
            self._year_top[self._month] = _top_tickets(timesheet.all_entries)
        self._year_view.set_year(
            self._year,
            self._year_hours,
            self._year_entries,
            self._settings.hours_per_day,
            self._settings.federal_state,
            booked_days_by_month=self._year_booked,
            manual_by_month=self._year_manual,
            top_tickets_by_month=self._year_top,
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

    def _show_detail(self, entry: WorklogEntry | BoardTicket) -> None:
        """Oeffnet den modalen Detail-Dialog.

        Nimmt einen Zeiteintrag aus der Stundenliste ODER ein Ticket aus
        den Ticket-Ansichten - der Dialog kennt beide Formen und zeigt je
        die passenden Felder.

        Args:
            entry:
                Der anzuzeigende Eintrag.
        """
        TicketDetailDialog(entry, self._display_host(), self).exec()

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
        splitter = self._qsettings.value("board/splitter")
        if splitter is not None:
            self._assigned_board.restore_splitter_state(bytes(splitter))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Laesst die Beschreibungs-Spalte mitwachsen, wenn ein Viewport waechst.

        Der Viewport-Resize (nicht der Fenster-Resize) traegt die tatsaechliche
        neue Breite - im Fenster-resizeEvent haette die View sie noch nicht. Beide
        Ansichten werden gefuellt: sie teilen sich die Geometrie, und ein
        Identitaetsvergleich mit viewport() ist unter PySide unzuverlaessig (jeder
        Aufruf liefert einen neuen Wrapper um dasselbe C++-Objekt).
        """
        if event.type() == QEvent.Type.Resize and hasattr(self, "_table"):
            self._fill_description(self._table, self._model)
            self._fill_description(self._tree, self._tree_model)
        # Ctrl+Mausrad zoomt wie im Browser - die Tabelle wuerde den Wheel sonst
        # zum Scrollen verbrauchen, deshalb hier abfangen und verschlucken.
        if self._wheel_zoom(event):
            return True
        return super().eventFilter(obj, event)

    def _wheel_zoom(self, event: QEvent) -> bool:
        """Zoomt bei Ctrl+Mausrad; True, wenn das Ereignis verbraucht wurde."""
        if not isinstance(event, QWheelEvent):
            return False
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        self._zoom(1 if event.angleDelta().y() > 0 else -1)
        return True

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Ctrl+Mausrad zoomt auch ueber Bereichen ohne eigenen Bildlauf."""
        if self._wheel_zoom(event):
            event.accept()
            return
        super().wheelEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Merkt Fenstergroesse, -zustand und Spaltenbreiten, wartet auf den Faden."""
        self._qsettings.setValue("window/geometry", self.saveGeometry())
        self._qsettings.setValue("window/state", self.saveState())
        self._qsettings.setValue("board/splitter", self._assigned_board.splitter_state())
        # Sichtbarkeit des Log-Docks festhalten - auch wenn es ueber sein eigenes
        # X geschlossen wurde (das laeuft nicht ueber toggle_log).
        self._settings.log_visible = self._log.isVisible()
        # Vom Nutzer gezogene Spaltenbreiten und den Log-Zustand dauerhaft sichern.
        self._settings.save()
        # Auf JEDEN laufenden Faden warten, auch auf ueberholte: Qt zerstoert
        # beim Schliessen alle Kinder des Fensters, und ein dabei noch
        # laufender QThread reisst das Programm mit.
        for worker in list(self._running_workers):
            if worker.isRunning():
                worker.wait(3000)
        super().closeEvent(event)
