"""Reiter "Performance-Booster": Kennzahlen, Verlauf und Hinweise je Person.

Die Ansicht ist duenn: sie zeigt einen fertigen PerformanceReport und meldet
Auswahl und Zeitraum ueber Signale. Abruf und Rechnen liegen im Worker und
im Kern.
"""

from __future__ import annotations

import datetime as dt
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.performance import (
    DEFAULT_PERIOD,
    INVOLVE_CREATED,
    INVOLVE_DONE,
    INVOLVEMENTS,
    PERIODS,
    SELF_NAME,
    Figures,
    PerformanceReport,
    Period,
    PeriodTicket,
    period_for,
)
from jira_timesheet_qt.services.ticket_board import key_sort_value

from .cell_delegate import CellDelegate
from .performance_charts import CourseChart, CycleChart, ProfileChart, SizeChart
from .theme import Mode, palette_for

# Beschriftung des eigenen Eintrags. Steht immer zuerst: der Hauptzweck ist
# die Selbstbeobachtung.
SELF_LABEL = SELF_NAME

# Filter ueber der Tabelle: alle Beteiligungen oder eine davon.
FILTER_ALL = "Alle"
FILTERS: tuple[str, ...] = (FILTER_ALL, *INVOLVEMENTS)

_COLUMNS = (
    "Ticket",
    "Titel",
    "Typ",
    "Status",
    "Beteiligung",
    "Erledigt",
    "Aktiv (AT)",
    "Gebucht (h)",
    "SP",
    "AT je SP",
    "Auffällig",
)
# Spaltennummern ueber den Namen - Tests und Code verdrahten keine Zahlen.
COL: dict[str, int] = {name: index for index, name in enumerate(_COLUMNS)}
_NUMERIC = (COL["Aktiv (AT)"], COL["Gebucht (h)"], COL["SP"], COL["AT je SP"])
_STRETCH = COL["Titel"]

# Sortierwert in einer eigenen Rolle, damit Zahlen als Zahlen sortieren.
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1

# Schema der Links in den Hinweisen.
_TICKET_LINK = "ticket:"


def _number(value: float, digits: int = 1) -> str:
    """Zahl mit deutschem Dezimalkomma."""
    return f"{value:.{digits}f}".replace(".", ",")


def _signed(value: float, digits: int = 1) -> str:
    """Zahl mit Vorzeichen und deutschem Dezimalkomma."""
    text = _number(abs(value), digits)
    return f"+{text}" if value > 0 else (f"-{text}" if value < 0 else text)


class _SortItem(QTableWidgetItem):
    """Tabellenzelle, die nach ihrem Sortierwert statt nach dem Text sortiert."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine, theirs = self.data(_SORT_ROLE), other.data(_SORT_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        try:
            return bool(mine < theirs)
        except TypeError:
            return super().__lt__(other)


class _Tile(QFrame):
    """Eine Kennzahl mit Veraenderung gegenueber der Vorperiode."""

    # Nur bei Kacheln, die eine Menge von Tickets zaehlen: filtert die Tabelle.
    clicked = Signal()

    def __init__(self, title: str, tooltip: str, clickable: bool = False) -> None:
        super().__init__()
        self.setObjectName("PerfTile")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._clickable = clickable
        # Die Eigenschaften steuern Hover und Markierung im Stylesheet.
        self.setProperty("clickable", "true" if clickable else "false")
        self.setProperty("active", "false")
        if clickable:
            tooltip = f"{tooltip}\nKlick: Tabelle darauf filtern."
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        # Groesse und Gewicht kommen aus dem Stylesheet: die globale Regel
        # fuer font-size wuerde ein setFont ueberschreiben, und nur so zoomt
        # die Kachel mit.
        self.title = QLabel(title)
        self.title.setObjectName("PerfTileTitle")
        self.value = QLabel("-")
        self.value.setObjectName("PerfTileValue")
        self.delta = QLabel("")
        self.delta.setObjectName("PerfTileDelta")
        for label in (self.title, self.value, self.delta):
            label.setToolTip(tooltip)
            layout.addWidget(label)

    def set_values(self, value: str, delta: str, tone: str) -> None:
        """Setzt Wert und Veraenderung. tone ist eine Farbe oder leer."""
        self.value.setText(value)
        self.delta.setText(delta)
        self.delta.setStyleSheet(f"color: {tone};" if tone else "")

    def set_active(self, active: bool) -> None:
        """Markiert die Kachel, deren Filter gerade unten gilt."""
        value = "true" if active else "false"
        if self.property("active") == value:
            return
        self.setProperty("active", value)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Meldet den Klick einer filternden Kachel."""
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


def _card(title: str, content: QWidget) -> QFrame:
    """Rahmt ein Diagramm oder die Hinweise als Karte mit Ueberschrift - im Stil der Kacheln."""
    card = QFrame()
    card.setObjectName("PerfCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 6, 10, 8)
    layout.setSpacing(2)
    heading = QLabel(title)
    heading.setObjectName("PerfCardTitle")
    heading.setToolTip(content.toolTip())
    layout.addWidget(heading)
    layout.addWidget(content, 1)
    return card


class PerformanceView(QWidget):
    """Der Reiter mit Auswahl, Kacheln, Diagrammen, Hinweisen und Tickets."""

    # Andere Person gewaehlt: Name aus der Merkliste, leer = man selbst.
    member_changed = Signal(str)
    # Anderer Zeitraum gewaehlt: 1M, 3M, 6M oder YTD.
    period_changed = Signal(str)
    # Neu laden, auch wenn Person und Zeitraum gleich bleiben.
    refresh_requested = Signal()
    # Gewaehltes Ticket fuer die Vorschau: Nummer oder None.
    ticket_selected = Signal(object)
    # Ticketnummer in einem Hinweis angeklickt. Die Ansicht waehlt das Ticket
    # selbst; das Fenster oeffnet Jira, wenn die Vorschau ausgeschaltet ist.
    hint_ticket_clicked = Signal(str)

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._report: PerformanceReport | None = None
        self._build_ui()

    # --- Aufbau ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("Team-Mitglied:"))
        self._member_box = QComboBox()
        self._member_box.setObjectName("PerfMemberFilter")
        self._member_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._member_box.setMinimumContentsLength(18)
        self._member_box.addItem(SELF_LABEL, "")
        self._member_box.currentIndexChanged.connect(lambda _index: self.member_changed.emit(self.current_member()))
        head.addWidget(self._member_box)

        head.addSpacing(12)
        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        self._period_buttons: dict[str, QToolButton] = {}
        for kind in PERIODS:
            button = QToolButton()
            button.setObjectName("PerfPeriod")
            button.setText(kind)
            button.setCheckable(True)
            button.setToolTip("Seit Jahresbeginn" if kind == "YTD" else f"Die letzten {kind[:-1]} Monate")
            self._period_group.addButton(button)
            self._period_buttons[kind] = button
            head.addWidget(button)
        self._period_buttons[DEFAULT_PERIOD].setChecked(True)
        self._period_group.buttonClicked.connect(self._on_period_clicked)

        # Der gewaehlte Zeitraum steht gross im freien Platz der Kopfzeile, die
        # Vorperiode klein darunter.
        head.addSpacing(24)
        span = QVBoxLayout()
        span.setSpacing(0)
        self._range = QLabel("")
        self._range.setObjectName("PerfRange")
        self._prior_range = QLabel("")
        self._prior_range.setObjectName("PerfPriorRange")
        span.addWidget(self._range)
        span.addWidget(self._prior_range)
        head.addLayout(span)

        head.addStretch(1)
        refresh = QPushButton("Aktualisieren")
        refresh.setToolTip("Zeitraum und Person neu aus Jira laden")
        refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        head.addWidget(refresh)
        outer.addLayout(head)

        self._period_label = QLabel("")
        self._period_label.setObjectName("ChartNote")
        outer.addWidget(self._period_label)

        # Kacheln
        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self._tile_all = _Tile(
            "Alle Tickets",
            "Alle Tickets, an denen die Person im Zeitraum beteiligt war: erledigt, erstellt, "
            "geschlossen oder gerade in Arbeit.",
            clickable=True,
        )
        self._tile_done = _Tile(
            "Erledigt", "Tickets, die im Zeitraum in Jiras Kategorie Fertig gewechselt sind.", clickable=True
        )
        self._tile_cycle = _Tile(
            "Durchlaufzeit (Median)",
            "Arbeitstage in einem aktiven Status, Wartezeiten nicht mitgezählt. Weniger ist besser.",
        )
        self._tile_small = _Tile(
            "Anteil kleiner Tickets",
            "Anteil der erledigten, gebuchten Tickets unter der Schwelle aus den Einstellungen.",
        )
        self._tile_booked = _Tile("Gebucht", "Eigene Buchungen der Person im Zeitraum, auf beliebigen Tickets.")
        self._tile_created = _Tile(
            "Erstellt",
            "Tickets, die die Person im Zeitraum selbst angelegt hat - der Zulauf. Neutral bewertet.",
            clickable=True,
        )
        self._tile_points = _Tile(
            "Arbeitstage je Story Point",
            "Median der aktiven Arbeitstage je Story Point, nur über geschätzte Tickets. Weniger ist schneller.",
        )
        self._tile_all.clicked.connect(lambda: self.set_filter(FILTER_ALL))
        self._tile_done.clicked.connect(lambda: self.set_filter(INVOLVE_DONE))
        self._tile_created.clicked.connect(lambda: self.set_filter(INVOLVE_CREATED))
        for tile in self._tiles():
            tiles.addWidget(tile, 1)
        outer.addLayout(tiles)

        # Diagramme und Hinweise
        charts = QWidget()
        grid = QGridLayout(charts)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        self._course = CourseChart(self._mode)
        self._cycle = CycleChart(self._mode)
        self._size = SizeChart(self._mode)
        self._hints = QLabel("")
        self._hints.setObjectName("PerfHints")
        self._hints.setWordWrap(True)
        self._hints.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._hints.setTextFormat(Qt.TextFormat.RichText)
        self._hints.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._hints.setOpenExternalLinks(False)
        self._hints.linkActivated.connect(self._on_hint_link)
        self._hints.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Abstand zur Kartenueberschrift - sonst erschlaegt der fette erste
        # Hinweistitel direkt darunter die Ueberschrift.
        self._hints.setContentsMargins(0, 8, 0, 0)
        # Mehrere Hinweise sind laenger als die Zelle - ohne Bildlauf fehlt das Ende.
        hints_area = QScrollArea()
        hints_area.setWidgetResizable(True)
        hints_area.setFrameShape(QFrame.Shape.NoFrame)
        hints_area.setWidget(self._hints)
        self._profile = ProfileChart(self._mode)
        grid.addWidget(_card(self._course.card_title, self._course), 0, 0)
        grid.addWidget(_card(self._cycle.card_title, self._cycle), 0, 1)
        grid.addWidget(_card(self._size.card_title, self._size), 1, 0)
        grid.addWidget(_card(self._profile.card_title, self._profile), 1, 1)
        grid.addWidget(_card("Hinweise", hints_area), 0, 2, 2, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)

        # Filter ueber der Tabelle
        table_box = QWidget()
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
        filters = QHBoxLayout()
        filters.setSpacing(4)
        filters.addWidget(QLabel("Tickets:"))
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QToolButton] = {}
        for name in FILTERS:
            button = QToolButton()
            button.setObjectName("PerfFilter")
            button.setText(name)
            button.setCheckable(True)
            self._filter_group.addButton(button)
            self._filter_buttons[name] = button
            filters.addWidget(button)
        self._filter_buttons[FILTER_ALL].setChecked(True)
        self._filter_group.buttonClicked.connect(lambda _button: self._fill_table(self._report))
        filters.addStretch(1)
        table_layout.addLayout(filters)

        # Tabelle
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setObjectName("PerfTable")
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setItemDelegate(CellDelegate(self._table))
        vertical = self._table.verticalHeader()
        vertical.setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_STRETCH, QHeaderView.ResizeMode.Stretch)
        self._table.currentCellChanged.connect(lambda *_args: self.ticket_selected.emit(self.current_key()))
        table_layout.addWidget(self._table, 1)

        body = QSplitter(Qt.Orientation.Vertical)
        body.setChildrenCollapsible(False)
        body.addWidget(charts)
        body.addWidget(table_box)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)

        self._placeholder = QLabel("Noch nichts geladen.")
        self._placeholder.setObjectName("BoardPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._placeholder)
        self._pages.addWidget(body)

        # Rechts haengt das Fenster die Ticket-Vorschau ein, wie in den Ticketlisten.
        self._side = QSplitter(Qt.Orientation.Horizontal)
        self._side.setChildrenCollapsible(False)
        self._side.addWidget(self._pages)
        outer.addWidget(self._side, 1)

        self._show_range(*period_for(self.current_period(), dt.date.today()))

    def _tiles(self) -> tuple[_Tile, ...]:
        """Alle Kacheln in Anzeigereihenfolge."""
        return (
            self._tile_all,
            self._tile_done,
            self._tile_created,
            self._tile_cycle,
            self._tile_points,
            self._tile_small,
            self._tile_booked,
        )

    # --- Auswahl ---------------------------------------------------------

    def set_members(self, names: list[str]) -> None:
        """Fuellt die Personenauswahl. Der eigene Eintrag bleibt vorn.

        Die bisherige Auswahl bleibt erhalten, solange es sie noch gibt.
        """
        previous = self.current_member()
        self._member_box.blockSignals(True)
        self._member_box.clear()
        self._member_box.addItem(SELF_LABEL, "")
        for name in names:
            self._member_box.addItem(name, name)
        index = self._member_box.findData(previous)
        self._member_box.setCurrentIndex(max(0, index))
        self._member_box.blockSignals(False)
        if self.current_member() != previous:
            self.member_changed.emit(self.current_member())

    def current_member(self) -> str:
        """Name aus der Merkliste, leer fuer die eigenen Tickets."""
        return str(self._member_box.currentData() or "")

    def select_member(self, name: str) -> None:
        """Waehlt eine Person, leer = sich selbst. Loest member_changed aus."""
        index = self._member_box.findData(name)
        if index >= 0:
            self._member_box.setCurrentIndex(index)

    def current_period(self) -> str:
        """Das Kuerzel des gewaehlten Zeitraums."""
        button = self._period_group.checkedButton()
        return button.text() if button is not None else DEFAULT_PERIOD

    def set_period(self, kind: str) -> None:
        """Setzt den Zeitraum ohne Signal - fuer den gemerkten Stand beim Start."""
        button = self._period_buttons.get(kind)
        if button is not None:
            button.setChecked(True)
            self._show_range(*period_for(kind, dt.date.today()))

    def _on_period_clicked(self, button: QToolButton) -> None:
        """Zeigt den neuen Zeitraum sofort und meldet ihn."""
        self._show_range(*period_for(button.text(), dt.date.today()))
        self.period_changed.emit(button.text())

    def current_filter(self) -> str:
        """Der gewaehlte Filter ueber der Tabelle."""
        button = self._filter_group.checkedButton()
        return button.text().split(" (")[0] if button is not None else FILTER_ALL

    def set_filter(self, name: str) -> None:
        """Filtert die Tabelle auf eine Beteiligung, FILTER_ALL = alle."""
        button = self._filter_buttons.get(name)
        if button is not None:
            button.setChecked(True)
            self._fill_table(self._report)

    # --- Anzeige ---------------------------------------------------------

    def _show_range(self, period: Period, prior: Period) -> None:
        """Schreibt den Zeitraum gross und die Vorperiode klein in die Kopfzeile."""
        self._range.setText(f"{period.start:%d.%m.%Y} - {period.end:%d.%m.%Y}")
        self._prior_range.setText(f"verglichen mit {prior.start:%d.%m.%Y} - {prior.end:%d.%m.%Y}")

    def show_message(self, text: str) -> None:
        """Zeigt einen Hinweis statt der Auswertung und leert alles Angezeigte.

        Leeren ist Pflicht: ein Abruf dauert gut 20 Sekunden, und in dieser Zeit
        stuenden sonst Kacheln, Kopfzeile und Vorschau der vorherigen Person
        neben der neuen Auswahl - genau so am 23.09.2026 aufgefallen.
        """
        self._report = None
        for chart in (self._course, self._cycle, self._size, self._profile):
            chart.set_report(None)
        for tile in self._tiles():
            tile.set_values("-", "", "")
        self._hints.setText("")
        self._period_label.setText("")
        self._show_range(*period_for(self.current_period(), dt.date.today()))
        self._set_filter_counts(None)
        self._fill_table(None)
        self._placeholder.setText(f"{self._member_box.currentText()}: {text}")
        self._pages.setCurrentWidget(self._placeholder)

    def report(self) -> PerformanceReport | None:
        """Der angezeigte Bericht."""
        return self._report

    def set_report(self, report: PerformanceReport | None) -> None:
        """Zeigt einen Bericht, None leert die Ansicht."""
        if report is None:
            self.show_message("Noch nichts geladen.")
            return
        self._report = report
        for chart in (self._course, self._cycle, self._size, self._profile):
            chart.set_report(report)
        self._show_range(report.period, report.prior_period)
        parts: list[str] = []
        if report.current.done:
            parts.append(
                f"Story Points: {report.current.estimated} der {report.current.done} erledigten Tickets geschätzt"
            )
        parts += report.notes
        self._period_label.setText(" · ".join(parts))
        self._fill_tiles(report.current, report.prior)
        self._tile_all.set_values(str(len(report.all_tickets)), "im Zeitraum beteiligt", "")
        self._fill_hints(report)
        self._set_filter_counts(report)
        self._fill_table(report)
        self._pages.setCurrentIndex(1)

    def _set_filter_counts(self, report: PerformanceReport | None) -> None:
        """Schreibt die Anzahl je Filter an die Knoepfe."""
        for name, button in self._filter_buttons.items():
            if report is None:
                button.setText(name)
                continue
            count = sum(1 for t in report.all_tickets if name == FILTER_ALL or name in t.involvement)
            button.setText(f"{name} ({count})")

    def _fill_tiles(self, now: Figures, before: Figures) -> None:
        """Setzt die Kacheln samt Veraenderung."""
        colors = palette_for(self._mode)

        def tone(diff: float, better_up: bool) -> str:
            if diff == 0:
                return colors.text_tertiary
            return colors.green if (diff > 0) == better_up else colors.red

        diff = now.done - before.done
        percent = f" ({_signed(100.0 * diff / before.done, 0)} %)" if before.done else ""
        self._tile_done.set_values(str(now.done), f"{_signed(diff, 0)}{percent} ggü. Vorperiode", tone(diff, True))

        if now.median_active_days is None:
            self._tile_cycle.set_values("-", "keine aktiven Tickets", "")
        elif before.median_active_days is None:
            self._tile_cycle.set_values(f"{_number(now.median_active_days)} AT", "keine Vorperiode", "")
        else:
            delta = now.median_active_days - before.median_active_days
            self._tile_cycle.set_values(
                f"{_number(now.median_active_days)} AT", f"{_signed(delta)} AT ggü. Vorperiode", tone(delta, False)
            )

        if now.small_share is None:
            self._tile_small.set_values("-", "keine gebuchten Tickets", "")
        elif before.small_share is None:
            self._tile_small.set_values(f"{_number(now.small_share, 0)} %", "keine Vorperiode", "")
        else:
            delta = now.small_share - before.small_share
            self._tile_small.set_values(
                f"{_number(now.small_share, 0)} %", f"{_signed(delta, 0)} Pkt. ggü. Vorperiode", tone(delta, False)
            )

        delta = now.booked_hours - before.booked_hours
        self._tile_booked.set_values(
            f"{_number(now.booked_hours)} h", f"{_signed(delta)} h ggü. Vorperiode", colors.text_tertiary
        )

        # Erstellt ist weder gut noch schlecht - neutral wie die Buchungen.
        delta = now.created - before.created
        self._tile_created.set_values(str(now.created), f"{_signed(delta, 0)} ggü. Vorperiode", colors.text_tertiary)

        if now.median_days_per_point is None:
            self._tile_points.set_values("-", "keine geschätzten Tickets", "")
        elif before.median_days_per_point is None:
            self._tile_points.set_values(f"{_number(now.median_days_per_point)} AT", "keine Vorperiode", "")
        else:
            delta = now.median_days_per_point - before.median_days_per_point
            self._tile_points.set_values(
                f"{_number(now.median_days_per_point)} AT",
                f"{_signed(delta)} AT ggü. Vorperiode",
                tone(delta, False),
            )

    def _fill_hints(self, report: PerformanceReport) -> None:
        """Schreibt die Hinweise als kurze Liste, die Ticketnummern als Links."""
        if not report.hints:
            self._hints.setText("Keine Auffälligkeiten in diesem Zeitraum.")
            return
        parts: list[str] = []
        for hint in report.hints:
            links = [f'<a href="{_TICKET_LINK}{html.escape(key)}">{html.escape(key)}</a>' for key in hint.keys[:8]]
            keys = ", ".join(links) + (" ..." if len(hint.keys) > 8 else "")
            suffix = f"<br><i>{keys}</i>" if keys else ""
            parts.append(f"<p><b>{html.escape(hint.title)}</b><br>{html.escape(hint.text)}{suffix}</p>")
        self._hints.setText("".join(parts))

    def _on_hint_link(self, href: str) -> None:
        """Waehlt das Ticket aus einem Hinweis in der Tabelle - notfalls unter "Alle"."""
        if not href.startswith(_TICKET_LINK):
            return
        key = href[len(_TICKET_LINK) :]
        if not self.select_ticket(key):
            self.set_filter(FILTER_ALL)
            self.select_ticket(key)
        self.hint_ticket_clicked.emit(key)

    def _visible_tickets(self, report: PerformanceReport) -> list[PeriodTicket]:
        """Die Tickets des gewaehlten Filters."""
        wanted = self.current_filter()
        return [t for t in report.all_tickets if wanted == FILTER_ALL or wanted in t.involvement]

    def _fill_table(self, report: PerformanceReport | None) -> None:
        """Listet die Tickets des Filters, auffaellige zuerst."""
        previous = self.current_key()
        current = self.current_filter()
        for name, tile in (
            (FILTER_ALL, self._tile_all),
            (INVOLVE_DONE, self._tile_done),
            (INVOLVE_CREATED, self._tile_created),
        ):
            tile.set_active(name == current)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        if report is None:
            # Die Vorschau zeigt sonst weiter das Ticket der vorherigen Person.
            if previous is not None:
                self.ticket_selected.emit(None)
            return
        reasons: dict[str, list[str]] = {}
        for hint in report.hints:
            for key in hint.keys:
                reasons.setdefault(key, []).append(hint.title)

        def order(ticket: PeriodTicket) -> tuple[bool, float, tuple[str, int, str]]:
            done = ticket.metric.done_at.timestamp() if ticket.metric else float("inf")
            return (ticket.key not in reasons, done, key_sort_value(ticket.key))

        tickets = sorted(self._visible_tickets(report), key=order)
        colors = palette_for(self._mode)
        self._table.setRowCount(len(tickets))
        for row, ticket in enumerate(tickets):
            metric = ticket.metric
            active = metric.active_days if metric else None
            points = ticket.story_points if ticket.story_points else (metric.story_points if metric else None)
            per_point = active / points if active is not None and points else None
            reason = ", ".join(reasons.get(ticket.key, []))
            cells: dict[str, tuple[str, object]] = {
                "Ticket": (ticket.key, key_sort_value(ticket.key)),
                "Titel": (ticket.summary, ticket.summary.casefold()),
                "Typ": (ticket.issuetype, ticket.issuetype.casefold()),
                "Status": (ticket.status, ticket.status.casefold()),
                "Beteiligung": (", ".join(ticket.involvement), ", ".join(ticket.involvement)),
                "Erledigt": (
                    f"{metric.done_at:%d.%m.%Y}" if metric else "",
                    metric.done_at.timestamp() if metric else float("inf"),
                ),
                "Aktiv (AT)": (_number(active) if active is not None else "-", active if active is not None else -1.0),
                "Gebucht (h)": (_number(ticket.hours, 2), ticket.hours),
                "SP": (_number(points, 0 if points.is_integer() else 1) if points else "-", points or -1.0),
                "AT je SP": (
                    _number(per_point) if per_point is not None else "-",
                    per_point if per_point is not None else -1.0,
                ),
                "Auffällig": (reason, reason),
            }
            for name, (text, sort_value) in cells.items():
                item = _SortItem(text)
                item.setData(_SORT_ROLE, sort_value)
                column = COL[name]
                if column in _NUMERIC:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if name == "Auffällig" and text:
                    item.setForeground(QColor(colors.red))
                self._table.setItem(row, column, item)
        # Ohne Ruecksetzen des Indikators sortiert setSortingEnabled sofort nach
        # Spalte 0 und wirft die Reihenfolge "auffaellig zuerst" weg.
        self._table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
        # resizeColumnsToContents kennt den Innenabstand des Delegates nicht.
        header = self._table.horizontalHeader()
        for column in range(self._table.columnCount()):
            if column != _STRETCH:
                header.resizeSection(column, header.sectionSize(column) + 16)
        header.setSectionResizeMode(_STRETCH, QHeaderView.ResizeMode.Stretch)
        if previous is None or not self.select_ticket(previous):
            self.ticket_selected.emit(None)

    # --- Vorschau --------------------------------------------------------

    def preview_host(self) -> QSplitter:
        """Der waagerechte Trenner, in den das Fenster die Ticket-Vorschau haengt."""
        return self._side

    def current_key(self) -> str | None:
        """Nummer des gewaehlten Tickets, None ohne Auswahl."""
        row = self._table.currentRow()
        item = self._table.item(row, COL["Ticket"]) if row >= 0 else None
        return item.text() if item is not None else None

    def select_ticket(self, key: str) -> bool:
        """Waehlt ein Ticket der Tabelle ueber seine Nummer."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL["Ticket"])
            if item is not None and item.text() == key:
                self._table.setCurrentCell(row, COL["Ticket"])
                return True
        return False

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        for chart in (self._course, self._cycle, self._size, self._profile):
            chart.apply_mode(mode)
        if self._report is not None:
            self.set_report(self._report)
