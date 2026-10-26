"""Reiter "Ticketfluss": wer wem Tickets gibt, als Stern um eine Person.

Die Ansicht ist duenn: sie bekommt einen fertigen Abruf (FlowLoad), faltet
ihn mit build_star nach Zeitraum und Pfeilart und zeichnet das Ergebnis.
Zeitraum und Pfeilart schneiden nur die geladenen Daten - ob neu geladen
werden muss, entscheidet das Fenster.

Leitplanke: Wege, keine Leistung. Die Personen stehen alphabetisch im Kreis,
es gibt keine Rangliste und keine Summe je Person als Schlagzeile.
"""

from __future__ import annotations

import datetime as dt
import functools
import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.performance import SELF_NAME
from jira_timesheet_qt.services.ticket_flow import (
    DEFAULT_FLOW_PERIOD,
    EDGE_HANDOVER,
    EDGE_KINDS,
    EDGE_ORDER,
    FLOW_ALL,
    FLOW_PERIODS,
    FLOW_YTD,
    FlowLoad,
    FlowStar,
    Spoke,
    build_star,
    flow_since,
)

from .theme import Mode, Palette, palette_for

# Kennung des Gast-Eintrags in der Personenauswahl: jemand, der nicht auf der
# Merkliste steht und per Klick in die Mitte kam.
GUEST = "\x1fguest"

# Richtung eines Pfeils aus Sicht der Mitte.
OUT = "out"
IN = "in"

_KIND_LABELS = {EDGE_ORDER: "Auftrag", EDGE_HANDOVER: "Übergabe"}
_KIND_TIPS = {
    EDGE_ORDER: "Ersteller an den ersten Bearbeiter eines Tickets",
    EDGE_HANDOVER: "Bearbeiterwechsel: der bisherige gibt an den neuen ab",
}

# Masse des Sterns in Szenenkoordinaten - die Ansicht skaliert ihn ein.
_RADIUS = 230.0
_NODE = 30.0
_CENTER = 40.0
_LABEL_CHARS = 22


def _period_tip(kind: str) -> str:
    """Tooltip eines Zeitraum-Knopfs."""
    if kind == FLOW_YTD:
        return "Seit Jahresbeginn"
    if kind == FLOW_ALL:
        return "Ohne Untergrenze - der erste Abruf dauert entsprechend"
    return f"Die letzten {kind[:-1]} Monate"


def _elide(text: str) -> str:
    """Kuerzt lange Namen fuer die Beschriftung im Kreis."""
    return text if len(text) <= _LABEL_CHARS else f"{text[: _LABEL_CHARS - 3]}..."


def _tickets(count: int) -> str:
    """ "1 Ticket" oder "n Tickets"."""
    return f"{count} Ticket" if count == 1 else f"{count} Tickets"


class _Node(QGraphicsEllipseItem):
    """Ein Kreis mit Namen. Klick meldet die Kennung, sofern es eine gibt."""

    def __init__(self, center: QPointF, radius: float, on_click: Callable[[], None] | None) -> None:
        super().__init__(QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius))
        self._on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Meldet den Klick, statt die Szene auszuwaehlen."""
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class _Arrow(QGraphicsPathItem):
    """Ein Pfeil mit Spitze. Hover hebt ihn hervor, Klick meldet ihn."""

    def __init__(self, path: QPainterPath, pen: QPen, on_click: Callable[[], None]) -> None:
        super().__init__(path)
        self._pen = pen
        self._on_click = on_click
        self.setPen(pen)
        self.setBrush(QBrush(pen.color()))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        wide = QPen(self._pen)
        wide.setWidthF(self._pen.widthF() + 2.5)
        self.setPen(wide)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        self.setPen(self._pen)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


def _arrow_path(start: QPointF, end: QPointF, head: float) -> QPainterPath:
    """Linie von start nach end mit gefuellter Spitze am Ende."""
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    base = QPointF(end.x() - ux * head, end.y() - uy * head)
    path = QPainterPath(start)
    path.lineTo(base)
    half = head * 0.55
    path.addPolygon(
        QPolygonF(
            [
                end,
                QPointF(base.x() - uy * half, base.y() + ux * half),
                QPointF(base.x() + uy * half, base.y() - ux * half),
                end,
            ]
        )
    )
    return path


class _StarView(QGraphicsView):
    """Die Zeichenflaeche. Skaliert den Stern in den verfuegbaren Platz."""

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def fit(self) -> None:
        """Passt den Stern ein, vergroessert aber nie ueber die Originalgroesse."""
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect().adjusted(-24, -24, 24, 24)
        if rect.isEmpty():
            return
        view = self.viewport().rect()
        scale = min(view.width() / rect.width(), view.height() / rect.height(), 1.0)
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        super().resizeEvent(event)
        self.fit()


class TicketFlowView(QWidget):
    """Der Reiter mit Personenauswahl, Zeitraum, Pfeilarten, Stern und Ticketliste."""

    # Andere Person gewaehlt: Name aus der Merkliste, leer = man selbst, GUEST = Gast.
    member_changed = Signal(str)
    # Anderer Zeitraum: YTD, 1M, 3M, 12M oder ALL.
    period_changed = Signal(str)
    # Pfeilart an- oder abgeschaltet - nur fuers Merken, gezeichnet wird hier.
    kinds_changed = Signal()
    # Neu laden, auch wenn Person und Zeitraum gleich bleiben.
    refresh_requested = Signal()
    # Person im Kreis angeklickt: Kennung und Name. Das Fenster setzt sie in die Mitte.
    person_clicked = Signal(str, str)
    # Ticket in der Liste doppelt angeklickt.
    ticket_activated = Signal(str)

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None, today: dt.date | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._today = today
        self._load: FlowLoad | None = None
        self._center_name = ""
        self._star: FlowStar | None = None
        self._build_ui()

    # --- Aufbau ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("Mitte:"))
        self._member_box = QComboBox()
        self._member_box.setObjectName("FlowMemberFilter")
        self._member_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._member_box.setMinimumContentsLength(18)
        self._member_box.addItem(SELF_NAME, "")
        self._member_box.currentIndexChanged.connect(lambda _index: self.member_changed.emit(self.current_member()))
        head.addWidget(self._member_box)

        head.addSpacing(12)
        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        self._period_buttons: dict[str, QToolButton] = {}
        for kind in FLOW_PERIODS:
            button = QToolButton()
            button.setObjectName("PerfPeriod")
            button.setText("Alle" if kind == FLOW_ALL else kind)
            button.setCheckable(True)
            button.setToolTip(_period_tip(kind))
            self._period_group.addButton(button)
            self._period_buttons[kind] = button
            head.addWidget(button)
        self._period_buttons[DEFAULT_FLOW_PERIOD].setChecked(True)
        self._period_group.buttonClicked.connect(lambda _button: self._on_period_clicked())

        head.addSpacing(12)
        self._kind_buttons: dict[str, QToolButton] = {}
        for kind in EDGE_KINDS:
            button = QToolButton()
            button.setObjectName("PerfPeriod")
            button.setText(_KIND_LABELS[kind])
            button.setCheckable(True)
            button.setChecked(True)
            button.setToolTip(_KIND_TIPS[kind])
            button.toggled.connect(lambda checked, k=kind: self._on_kind_toggled(k, checked))
            self._kind_buttons[kind] = button
            head.addWidget(button)

        head.addSpacing(16)
        self._legend = QLabel("")
        self._legend.setObjectName("FlowLegend")
        head.addWidget(self._legend)

        head.addStretch(1)
        refresh = QPushButton("Aktualisieren")
        refresh.setToolTip("Person und Zeitraum neu aus Jira laden")
        refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        head.addWidget(refresh)
        outer.addLayout(head)

        self._pages = QStackedWidget()
        self._message = QLabel("")
        self._message.setObjectName("FlowMessage")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._pages.addWidget(self._message)

        self._scene = QGraphicsScene(self)
        # Die Zeichenflaeche entsteht erst mit dem ersten Stern (_ensure_canvas).
        # Belegt am 26.10.2026: schon ein leeres QGraphicsView im Fenster
        # aendert, was processEvents an einem verborgenen Fenster nachholt -
        # test_description_fills_available_width wurde davon rot. Wer den
        # Reiter nie oeffnet, bekommt so ein Fenster wie vorher.
        self._canvas: _StarView | None = None
        self._canvas_slot = QWidget()

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(4)
        self._list_title = QLabel("Klick auf einen Pfeil zeigt seine Tickets.")
        self._list_title.setObjectName("FlowListTitle")
        self._list_title.setWordWrap(True)
        side_layout.addWidget(self._list_title)
        self._list = QTreeWidget()
        self._list.setObjectName("FlowTickets")
        self._list.setHeaderLabels(["Ticket", "Titel"])
        self._list.setRootIsDecorated(False)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setToolTip("Doppelklick öffnet das Ticket in Jira")
        header = self._list.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._list.itemDoubleClicked.connect(lambda item, _col: self.ticket_activated.emit(item.text(0)))
        side_layout.addWidget(self._list, 1)

        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._split.setChildrenCollapsible(False)
        self._split.addWidget(self._canvas_slot)
        self._split.addWidget(side)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 1)
        self._pages.addWidget(self._split)
        outer.addWidget(self._pages, 1)

        self._footer = QLabel("")
        self._footer.setObjectName("FlowFooter")
        outer.addWidget(self._footer)
        self._paint_legend()

    # --- Auswahl ---------------------------------------------------------

    def set_members(self, names: list[str]) -> None:
        """Fuellt die Personenauswahl. Der eigene Eintrag bleibt vorn, ein Gast hinten.

        Die bisherige Auswahl bleibt erhalten, solange es sie noch gibt.
        """
        previous = self.current_member()
        guest = self._guest_label()
        self._member_box.blockSignals(True)
        self._member_box.clear()
        self._member_box.addItem(SELF_NAME, "")
        for name in names:
            self._member_box.addItem(name, name)
        if guest:
            self._member_box.addItem(guest, GUEST)
        index = self._member_box.findData(previous)
        self._member_box.setCurrentIndex(max(0, index))
        self._member_box.blockSignals(False)
        if self.current_member() != previous:
            self.member_changed.emit(self.current_member())

    def _guest_label(self) -> str:
        index = self._member_box.findData(GUEST)
        return self._member_box.itemText(index) if index >= 0 else ""

    def current_member(self) -> str:
        """Name aus der Merkliste, leer fuer sich selbst, GUEST fuer einen Gast."""
        return str(self._member_box.currentData() or "")

    def select_member(self, name: str) -> None:
        """Waehlt eine Person, leer = sich selbst. Loest member_changed aus."""
        index = self._member_box.findData(name)
        if index >= 0:
            self._member_box.setCurrentIndex(index)

    def set_guest(self, name: str) -> None:
        """Setzt jemanden ausserhalb der Merkliste in die Mitte. Loest member_changed aus."""
        index = self._member_box.findData(GUEST)
        if index >= 0:
            self._member_box.blockSignals(True)
            self._member_box.removeItem(index)
            self._member_box.blockSignals(False)
        self._member_box.addItem(name, GUEST)
        self._member_box.setCurrentIndex(self._member_box.count() - 1)
        # Derselbe Gast-Eintrag, aber eine andere Person - der Index allein
        # wechselt nicht immer, das Signal muss trotzdem kommen.
        self.member_changed.emit(GUEST)

    def current_period(self) -> str:
        """Kuerzel des gewaehlten Zeitraums."""
        checked = self._period_group.checkedButton()
        return next((kind for kind, button in self._period_buttons.items() if button is checked), DEFAULT_FLOW_PERIOD)

    def set_period(self, kind: str) -> None:
        """Waehlt einen Zeitraum, ohne period_changed auszuloesen."""
        button = self._period_buttons.get(kind)
        if button is not None:
            button.setChecked(True)
            self._render()

    def current_since(self) -> dt.date | None:
        """Erster Tag des gewaehlten Zeitraums."""
        return flow_since(self.current_period(), self._today or dt.date.today())

    def _on_period_clicked(self) -> None:
        self._render()
        self.period_changed.emit(self.current_period())

    def current_kinds(self) -> tuple[str, ...]:
        """Die zugeschalteten Pfeilarten."""
        return tuple(kind for kind, button in self._kind_buttons.items() if button.isChecked())

    def set_kinds(self, kinds: tuple[str, ...]) -> None:
        """Schaltet Pfeilarten, ohne kinds_changed auszuloesen. Leer wird ignoriert."""
        if not any(kind in self._kind_buttons for kind in kinds):
            return
        for kind, button in self._kind_buttons.items():
            button.blockSignals(True)
            button.setChecked(kind in kinds)
            button.blockSignals(False)
        self._render()

    def _on_kind_toggled(self, kind: str, checked: bool) -> None:
        if not checked and not self.current_kinds():
            # Ohne jede Pfeilart bliebe der Stern leer, ohne dass klar wird,
            # warum - die letzte bleibt an.
            button = self._kind_buttons[kind]
            button.blockSignals(True)
            button.setChecked(True)
            button.blockSignals(False)
            return
        self._render()
        self.kinds_changed.emit()

    # --- Inhalt ----------------------------------------------------------

    def show_message(self, text: str) -> None:
        """Zeigt einen Hinweis statt des Sterns und vergisst den alten Abruf.

        Vergessen ist Pflicht: waehrend des Ladens stuende sonst der Stern der
        vorherigen Person neben der neuen Auswahl.
        """
        self._load = None
        self._star = None
        self._scene.clear()
        self._list.clear()
        self._footer.setText("")
        self._message.setText(text)
        self._pages.setCurrentIndex(0)

    def flow(self) -> FlowLoad | None:
        """Der angezeigte Abruf."""
        return self._load

    def star(self) -> FlowStar | None:
        """Der zuletzt gezeichnete Stern."""
        return self._star

    def set_flow(self, load: FlowLoad, center_name: str = "") -> None:
        """Zeigt einen Abruf.

        Args:
            load:
                Der Abruf, gegebenenfalls schon anonymisiert.
            center_name:
                Name der Mitte. Leer = der Jira-Name.
        """
        self._load = load
        self._center_name = center_name
        self._pages.setCurrentIndex(1)
        self._render()

    def _render(self) -> None:
        """Faltet den Abruf nach Zeitraum und Pfeilart und zeichnet ihn neu."""
        load = self._load
        if load is None:
            return
        since = self.current_since()
        star = build_star(load.data, load.center, self.current_kinds(), since, center_name=self._center_name)
        self._star = star
        self._list.clear()
        self._list_title.setText("Klick auf einen Pfeil zeigt seine Tickets.")
        self._draw(star)
        self._footer.setText(self._footer_text(load, star, since))

    def _footer_text(self, load: FlowLoad, star: FlowStar, since: dt.date | None) -> str:
        parts = [f"Zeitraum ab {since:%d.%m.%Y}" if since is not None else "Gesamter Zeitraum"]
        parts.append(f"{len(star.spokes)} Personen einzeln")
        if star.others is not None:
            parts.append(f"{star.others.members} unter Sonstige")
        if load.data.missing:
            parts.append(f"{_tickets(len(load.data.missing))} ohne Änderungsverlauf - ohne Pfeile")
        return ", ".join(parts)

    # --- Zeichnen --------------------------------------------------------

    def _paint_legend(self) -> None:
        colors = palette_for(self._mode)
        self._legend.setText(
            f'<span style="color:{self._out_color(colors)}">&#9632;</span> gibt ab &nbsp; '
            f'<span style="color:{self._in_color(colors)}">&#9632;</span> bekommt'
        )
        self._legend.setToolTip("Aus Sicht der Person in der Mitte. Die Pfeildicke folgt der Zahl der Tickets.")

    @staticmethod
    def _out_color(colors: Palette) -> str:
        return colors.accent

    @staticmethod
    def _in_color(colors: Palette) -> str:
        return colors.purple

    def _text(self, text: str, color: str, bold: bool = False) -> QGraphicsSimpleTextItem:
        item = self._scene.addSimpleText(text)
        item.setBrush(QBrush(QColor(color)))
        font = QFont(self.font())
        font.setBold(bold)
        item.setFont(font)
        return item

    def _ensure_canvas(self) -> _StarView:
        """Legt die Zeichenflaeche beim ersten Stern an, an Stelle des Platzhalters."""
        if self._canvas is None:
            self._canvas = _StarView(self._scene)
            self._canvas.setObjectName("FlowCanvas")
            self._split.replaceWidget(0, self._canvas)
            self._canvas_slot.deleteLater()
            # Der Platzhalter hatte keine Groesse - ohne Startbreiten bekaeme die
            # Liste die halbe Flaeche. Gesetzt wird erst nach dem Layout, vorher
            # kennt der Splitter seine Breite nicht.
            QTimer.singleShot(0, self._split_three_to_one)
        return self._canvas

    def _split_three_to_one(self) -> None:
        """Drei Viertel fuer den Stern, ein Viertel fuer die Ticketliste."""
        width = self._split.width()
        if width > 0:
            self._split.setSizes([width * 3 // 4, width - width * 3 // 4])

    def _draw(self, star: FlowStar) -> None:
        self._scene.clear()
        colors = palette_for(self._mode)
        canvas = self._ensure_canvas()
        canvas.setBackgroundBrush(QBrush(QColor(colors.bg_primary)))
        origin = QPointF(0.0, 0.0)

        spokes: list[Spoke] = list(star.spokes)
        if star.others is not None:
            spokes.append(star.others)
        top = max((max(len(s.outgoing), len(s.incoming)) for s in spokes), default=1) or 1

        for index, spoke in enumerate(spokes):
            angle = -math.pi / 2 + 2 * math.pi * index / len(spokes)
            point = QPointF(_RADIUS * math.cos(angle), _RADIUS * math.sin(angle))
            self._draw_arrows(spoke, origin, point, top, colors)
            self._draw_node(spoke, point, colors)

        center = _Node(origin, _CENTER, None)
        # accent_subtle ist ein CSS-rgba-Wert, den QColor nicht liest (ergibt
        # Schwarz) - deshalb der Akzent mit eigener Deckkraft.
        fill = QColor(colors.accent)
        fill.setAlphaF(0.22)
        center.setBrush(QBrush(fill))
        center.setPen(QPen(QColor(colors.accent), 2.0))
        center.setToolTip(star.center.name)
        self._scene.addItem(center)
        label = self._text(_elide(star.center.name), colors.text_primary, bold=True)
        box = label.boundingRect()
        label.setPos(-box.width() / 2, _CENTER + 6)
        # Der Name liegt zwischen den Pfeilen nach unten - ein Kaestchen in
        # Hintergrundfarbe haelt ihn lesbar.
        plate = self._scene.addRect(
            QRectF(-box.width() / 2 - 6, _CENTER + 4, box.width() + 12, box.height() + 4),
            QPen(QColor(colors.border)),
            QBrush(QColor(colors.bg_primary)),
        )
        plate.setZValue(1)
        label.setZValue(2)

        if not spokes:
            hint = self._text("Keine Wege in diesem Zeitraum.", colors.text_secondary)
            hint.setPos(-hint.boundingRect().width() / 2, -_CENTER - 36)
        canvas.fit()

    def _draw_node(self, spoke: Spoke, point: QPointF, colors: Palette) -> None:
        person = spoke.person
        on_click: Callable[[], None] | None = None
        if person is not None:
            account, name = person.account_id, person.name

            def on_click() -> None:
                self.person_clicked.emit(account, name)

        node = _Node(point, _NODE, on_click)
        node.setBrush(QBrush(QColor(colors.bg_elevated)))
        node.setPen(QPen(QColor(colors.border_hover), 1.5))
        title = person.name if person is not None else f"Sonstige ({spoke.members})"
        # Aus Sicht dieser Person: was die Mitte abgibt, bekommt sie.
        tip = (
            f"{title}\nbekommt von der Mitte: {_tickets(len(spoke.outgoing))}\n"
            f"gibt an die Mitte: {_tickets(len(spoke.incoming))}"
        )
        if person is not None:
            tip += "\nKlick: in die Mitte setzen"
        node.setToolTip(tip)
        self._scene.addItem(node)
        label = self._text(_elide(title), colors.text_secondary if person is None else colors.text_primary)
        width = label.boundingRect().width()
        # Unter dem Kreis, oben im Kreis darueber - sonst laeuft die Schrift in die Pfeile.
        y = point.y() + _NODE + 4 if point.y() >= -1 else point.y() - _NODE - label.boundingRect().height() - 4
        label.setPos(point.x() - width / 2, y)

    def _draw_arrows(self, spoke: Spoke, origin: QPointF, point: QPointF, top: int, colors: Palette) -> None:
        dx, dy = point.x() - origin.x(), point.y() - origin.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        vx, vy = -uy, ux
        for direction, keys, color in (
            (OUT, spoke.outgoing, self._out_color(colors)),
            (IN, spoke.incoming, self._in_color(colors)),
        ):
            if not keys:
                continue
            width = 1.5 + 7.0 * len(keys) / top
            side = 1.0 if direction == OUT else -1.0
            offset = side * (6.0 + width / 2)
            near = QPointF(origin.x() + ux * (_CENTER + 4) + vx * offset, origin.y() + uy * (_CENTER + 4) + vy * offset)
            far = QPointF(point.x() - ux * (_NODE + 4) + vx * offset, point.y() - uy * (_NODE + 4) + vy * offset)
            start, end = (near, far) if direction == OUT else (far, near)
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            arrow = _Arrow(
                _arrow_path(start, end, 8.0 + width),
                pen,
                functools.partial(self.show_tickets, spoke, direction),
            )
            arrow.setToolTip(f"{self._arrow_title(spoke, direction)}: {_tickets(len(keys))}\nKlick: Tickets anzeigen")
            self._scene.addItem(arrow)
            count = self._text(str(len(keys)), color, bold=True)
            mid = QPointF((near.x() + far.x()) / 2, (near.y() + far.y()) / 2)
            box = count.boundingRect()
            shift = side * (width / 2 + 10)
            count.setPos(mid.x() + vx * shift - box.width() / 2, mid.y() + vy * shift - box.height() / 2)

    def _arrow_title(self, spoke: Spoke, direction: str) -> str:
        center = self._star.center.name if self._star is not None else ""
        other = spoke.person.name if spoke.person is not None else f"Sonstige ({spoke.members})"
        return f"{center} an {other}" if direction == OUT else f"{other} an {center}"

    def show_tickets(self, spoke: Spoke, direction: str) -> None:
        """Fuellt die Liste mit den Tickets eines Pfeils."""
        keys = spoke.outgoing if direction == OUT else spoke.incoming
        titles = self._load.data.titles if self._load is not None else {}
        self._list_title.setText(f"{self._arrow_title(spoke, direction)}: {_tickets(len(keys))}")
        self._list.clear()
        for key in keys:
            self._list.addTopLevelItem(QTreeWidgetItem([key, titles.get(key, "")]))

    def listed_keys(self) -> list[str]:
        """Die Tickets in der Liste, fuer Tests."""
        items = (self._list.topLevelItem(row) for row in range(self._list.topLevelItemCount()))
        return [item.text(0) for item in items if item is not None]

    def apply_mode(self, mode: Mode) -> None:
        """Zeichnet in den Farben des neuen Erscheinungsbilds neu."""
        self._mode = mode
        self._paint_legend()
        if self._star is not None:
            self._draw(self._star)
