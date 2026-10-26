"""Reiter "Teamflow": wer wem Tickets gibt, als Stern um eine Person.

Die Ansicht ist duenn: sie bekommt einen fertigen Abruf (FlowLoad), faltet
ihn mit build_star nach Zeitraum und Pfeilart und zeichnet das Ergebnis.
Zeitraum und Pfeilart schneiden nur die geladenen Daten - ob neu geladen
werden muss, entscheidet das Fenster. Neu laden geht ueber die Werkzeugleiste
des Fensters, die Ansicht hat keinen eigenen Knopf dafuer.

Im Kreis stehen die Personen alphabetisch. Nach Menge geordnet ist nur die
Liste der engsten Kontakte daneben.
"""

from __future__ import annotations

import datetime as dt
import functools
import math
from collections.abc import Callable, Mapping

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QStackedWidget,
    QStyleOptionGraphicsItem,
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
    top_contacts,
)

from .theme import Mode, Palette, palette_for

# Kennung des Gast-Eintrags in der Personenauswahl: jemand, der nicht auf der
# Merkliste steht und per Klick in die Mitte kam.
GUEST = "\x1fguest"

# Richtung eines Pfeils aus Sicht der Mitte. BOTH nur fuer die Kontaktliste.
OUT = "out"
IN = "in"
BOTH = "both"

_KIND_LABELS = {EDGE_ORDER: "Auftrag", EDGE_HANDOVER: "Übergabe"}
_KIND_TIPS = {
    EDGE_ORDER: "Ersteller an den ersten Bearbeiter eines Tickets",
    EDGE_HANDOVER: "Bearbeiterwechsel: der bisherige gibt an den neuen ab",
}

# Masse des Sterns in Szenenkoordinaten - die Ansicht skaliert ihn ein.
_RADIUS = 250.0
_NODE = 34.0
_CENTER = 46.0
_LABEL_CHARS = 22

# Einpassen darf vergroessern, aber nicht beliebig - sonst wirkt ein Stern mit
# zwei Personen auf einem grossen Bildschirm wie ein Plakat.
_MAX_FIT = 2.2
# Zoom per Mausrad: Faktor je Raste und Grenzen relativ zur eingepassten Groesse.
_ZOOM_STEP = 1.15
_ZOOM_MIN = 0.4
_ZOOM_MAX = 5.0
# Deckkraft alles Uebrigen, solange die Maus ueber einer Person oder einem Pfeil steht.
_DIMMED = 0.22

# Rolle in der Kontaktliste: die Speiche hinter der Zeile.
_SPOKE_ROLE = Qt.ItemDataRole.UserRole + 1


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


def initials(name: str) -> str:
    """Zwei Buchstaben fuer einen Kreis ohne Profilbild.

    "Michael Blaess" und "Blaess, Michael" werden beide zu "MB".
    """
    if "," in name:
        last, _, first = name.partition(",")
        name = f"{first} {last}"
    words = [word for word in name.replace("-", " ").split() if word[:1].isalpha()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return f"{words[0][0]}{words[-1][0]}".upper()


def round_pixmap(data: bytes, diameter: int) -> QPixmap | None:
    """Macht aus Bilddaten ein rundes Bild der gewuenschten Groesse.

    Returns:
        Das Bild, None wenn die Daten kein lesbares Bild sind.
    """
    source = QPixmap()
    if not source.loadFromData(data) or source.isNull():
        return None
    scaled = source.scaled(
        diameter,
        diameter,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(diameter, diameter)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, diameter, diameter)
    painter.setClipPath(clip)
    painter.drawPixmap(
        (diameter - scaled.width()) // 2,
        (diameter - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return result


class _Node(QGraphicsEllipseItem):
    """Ein Kreis. Hover hebt ihn hervor, Klick meldet ihn, sofern er klickbar ist."""

    def __init__(
        self,
        center: QPointF,
        radius: float,
        on_click: Callable[[], None] | None,
        on_hover: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius))
        self._on_click = on_click
        self._on_hover = on_hover
        self._pen = QPen()
        self._hover_pen = QPen()
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        if on_hover is not None:
            self.setAcceptHoverEvents(True)

    def set_pens(self, normal: QPen, hover: QPen) -> None:
        """Rahmen im Ruhezustand und unter der Maus."""
        self._pen = normal
        self._hover_pen = hover
        self.setPen(normal)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        self.setPen(self._hover_pen)
        if self._on_hover is not None:
            self._on_hover(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        self.setPen(self._pen)
        if self._on_hover is not None:
            self._on_hover(False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Meldet den Klick, statt die Szene zu verschieben."""
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class _Arrow(QGraphicsPathItem):
    """Ein Pfeil mit Spitze. Hover hebt ihn hervor, Klick meldet ihn.

    Linie und Spitze werden getrennt gezeichnet, die Spitze nur gefuellt.
    Als ein Pfad mit Rand und Fuellung ueberlappten sich beide, und beim
    Verblassen (Hover auf einer anderen Speiche) sah die Spitze hohl aus.
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        head: float,
        pen: QPen,
        on_click: Callable[[], None],
        on_hover: Callable[[bool], None] | None = None,
    ) -> None:
        line, tip = _arrow_parts(start, end, head)
        outline = QPainterPath(line)
        outline.addPolygon(tip)
        # Der Pfad dient der Trefferflaeche, gezeichnet wird in paint().
        super().__init__(outline)
        self._line = line
        self._tip = tip
        self._pen = pen
        self._on_click = on_click
        self._on_hover = on_hover
        self.setPen(pen)
        self.setBrush(QBrush(pen.color()))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Linie mit dem Stift, Spitze nur als Flaeche."""
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._line)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush())
        painter.drawPolygon(self._tip)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        wide = QPen(self._pen)
        wide.setWidthF(self._pen.widthF() + 4.0)
        self.setPen(wide)
        if self._on_hover is not None:
            self._on_hover(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        self.setPen(self._pen)
        if self._on_hover is not None:
            self._on_hover(False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


def _arrow_parts(start: QPointF, end: QPointF, head: float) -> tuple[QPainterPath, QPolygonF]:
    """Linie von start bis zum Fuss der Spitze, und die Spitze als Dreieck."""
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    base = QPointF(end.x() - ux * head, end.y() - uy * head)
    line = QPainterPath(start)
    line.lineTo(base)
    half = head * 0.55
    tip = QPolygonF(
        [
            end,
            QPointF(base.x() - uy * half, base.y() + ux * half),
            QPointF(base.x() + uy * half, base.y() - ux * half),
        ]
    )
    return line, tip


class _StarView(QGraphicsView):
    """Die Zeichenflaeche: passt den Stern ein, zoomt per Mausrad, verschiebt per Ziehen."""

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setToolTip("Mausrad: zoomen, Ziehen: verschieben, Doppelklick ins Leere: einpassen")
        self._fit_scale = 1.0
        self._zoomed = False

    def fit(self) -> None:
        """Passt den Stern ein und vergisst einen eigenen Zoom."""
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect().adjusted(-24, -24, 24, 24)
        if rect.isEmpty():
            return
        # Viel Rand um den Stern, damit sich gezoomt auch verschieben laesst.
        scene.setSceneRect(rect.adjusted(-rect.width() * 2, -rect.height() * 2, rect.width() * 2, rect.height() * 2))
        view = self.viewport().rect()
        scale = min(view.width() / rect.width(), view.height() / rect.height(), _MAX_FIT)
        self._fit_scale = max(scale, 0.05)
        self._zoomed = False
        self.resetTransform()
        self.scale(self._fit_scale, self._fit_scale)
        self.centerOn(rect.center())

    def zoom(self, steps: float) -> None:
        """Zoomt um die Mitte der Ansicht oder den Mauszeiger, in Rasten."""
        current = self.transform().m11()
        target = current * (_ZOOM_STEP**steps)
        target = min(max(target, self._fit_scale * _ZOOM_MIN), self._fit_scale * _ZOOM_MAX)
        if current > 0:
            self.scale(target / current, target / current)
            self._zoomed = True

    def current_zoom(self) -> float:
        """Zoom relativ zur eingepassten Groesse, 1.0 = eingepasst."""
        return self.transform().m11() / self._fit_scale

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        self.zoom(event.angleDelta().y() / 120)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        if self.itemAt(event.position().toPoint()) is None:
            self.fit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        super().resizeEvent(event)
        # Ein eigener Zoom bleibt beim Groessenwechsel stehen.
        if not self._zoomed:
            self.fit()


class TicketFlowView(QWidget):
    """Der Reiter mit Personenauswahl, Zeitraum, Pfeilarten, Stern, Kontakten und Ticketliste."""

    # Andere Person gewaehlt: Name aus der Merkliste, leer = man selbst, GUEST = Gast.
    member_changed = Signal(str)
    # Anderer Zeitraum: YTD, 1M, 3M, 12M oder ALL.
    period_changed = Signal(str)
    # Pfeilart an- oder abgeschaltet - nur fuers Merken, gezeichnet wird hier.
    kinds_changed = Signal()
    # Person im Kreis angeklickt: Kennung und Name. Das Fenster setzt sie in die Mitte.
    person_clicked = Signal(str, str)
    # Ticket in der Liste doppelt angeklickt.
    ticket_activated = Signal(str)
    # Kennungen im Bild, fuer die noch kein Profilbild vorliegt.
    avatars_needed = Signal(list)

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None, today: dt.date | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._today = today
        self._load: FlowLoad | None = None
        self._center_name = ""
        self._star: FlowStar | None = None
        self._avatar_data: dict[str, bytes] = {}
        self._asked: set[str] = set()
        self._anonymized = False
        # Je Speiche die Elemente, die beim Hover sichtbar bleiben.
        self._groups: list[list[QGraphicsItem]] = []
        self._dimmable: list[QGraphicsItem] = []
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
        self._zoom_buttons: dict[str, QToolButton] = {}
        for name, text, tip in (
            ("out", "-", "Verkleinern (Mausrad zurück)"),
            ("in", "+", "Vergrößern (Mausrad vor)"),
            ("fit", "Einpassen", "Ganzen Stern zeigen (Doppelklick ins Leere)"),
        ):
            button = QToolButton()
            button.setObjectName("PerfPeriod")
            button.setText(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, n=name: self._on_zoom_button(n))
            self._zoom_buttons[name] = button
            head.addWidget(button)
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
        contacts_title = QLabel("Top 3 Kontakte")
        contacts_title.setObjectName("FlowListTitle")
        contacts_title.setToolTip(
            "Mit wem die Mitte im Zeitraum die meisten Tickets geteilt hat, in beide Richtungen.\n"
            "Klick: gemeinsame Tickets zeigen, Doppelklick: in die Mitte setzen."
        )
        side_layout.addWidget(contacts_title)
        self._contacts = QTreeWidget()
        self._contacts.setObjectName("FlowContacts")
        self._contacts.setHeaderLabels(["Person", "Tickets", "gibt ab", "bekommt"])
        self._contacts.setRootIsDecorated(False)
        self._contacts.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._contacts.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contacts_header = self._contacts.header()
        contacts_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            contacts_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._contacts.itemClicked.connect(lambda item, _col: self._on_contact_clicked(item))
        self._contacts.itemDoubleClicked.connect(lambda item, _col: self._on_contact_activated(item))
        side_layout.addWidget(self._contacts)

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

    def _on_zoom_button(self, name: str) -> None:
        if self._canvas is None:
            return
        if name == "fit":
            self._canvas.fit()
        else:
            # Ohne Mauszeiger ueber der Flaeche um deren Mitte zoomen.
            self._canvas.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self._canvas.zoom(1 if name == "in" else -1)
            self._canvas.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def zoom_level(self) -> float:
        """Zoom relativ zur eingepassten Groesse, fuer Tests. 1.0 ohne Stern."""
        return self._canvas.current_zoom() if self._canvas is not None else 1.0

    # --- Inhalt ----------------------------------------------------------

    def show_message(self, text: str) -> None:
        """Zeigt einen Hinweis statt des Sterns und vergisst den alten Abruf.

        Vergessen ist Pflicht: waehrend des Ladens stuende sonst der Stern der
        vorherigen Person neben der neuen Auswahl.
        """
        self._load = None
        self._star = None
        self._clear_scene()
        self._list.clear()
        self._contacts.clear()
        self._footer.setText("")
        self._message.setText(text)
        self._pages.setCurrentIndex(0)

    def flow(self) -> FlowLoad | None:
        """Der angezeigte Abruf."""
        return self._load

    def star(self) -> FlowStar | None:
        """Der zuletzt gezeichnete Stern."""
        return self._star

    def set_anonymized(self, anonymized: bool) -> None:
        """Im Screenshot-Modus keine Profilbilder - sie zeigen echte Menschen."""
        if anonymized != self._anonymized:
            self._anonymized = anonymized
            if self._star is not None:
                self._draw(self._star)

    def set_avatars(self, images: Mapping[str, bytes]) -> None:
        """Uebernimmt Profilbilder und zeichnet neu, wenn eines im Bild steht."""
        if not images:
            return
        self._avatar_data.update(images)
        if self._star is not None:
            self._draw(self._star)

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
        self._render(refit=True)

    def _render(self, refit: bool = False) -> None:
        """Faltet den Abruf nach Zeitraum und Pfeilart und zeichnet ihn neu."""
        load = self._load
        if load is None:
            return
        since = self.current_since()
        kinds = self.current_kinds()
        star = build_star(load.data, load.center, kinds, since, center_name=self._center_name)
        self._star = star
        self._list.clear()
        self._list_title.setText("Klick auf einen Pfeil zeigt seine Tickets.")
        self._fill_contacts(top_contacts(load.data, load.center, kinds, since))
        self._draw(star, refit=refit)
        self._footer.setText(self._footer_text(load, star, since))

    def _footer_text(self, load: FlowLoad, star: FlowStar, since: dt.date | None) -> str:
        parts = [f"Zeitraum ab {since:%d.%m.%Y}" if since is not None else "Gesamter Zeitraum"]
        parts.append(f"{len(star.spokes)} Personen einzeln")
        if star.others is not None:
            parts.append(f"{star.others.members} unter Sonstige")
        if load.data.missing:
            parts.append(f"{_tickets(len(load.data.missing))} ohne Änderungsverlauf - ohne Pfeile")
        return ", ".join(parts)

    def _fill_contacts(self, contacts: tuple[Spoke, ...]) -> None:
        self._contacts.clear()
        for spoke in contacts:
            if spoke.person is None:
                continue
            shared = len(set(spoke.outgoing) | set(spoke.incoming))
            item = QTreeWidgetItem([spoke.person.name, str(shared), str(len(spoke.outgoing)), str(len(spoke.incoming))])
            for column in (1, 2, 3):
                item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setData(0, _SPOKE_ROLE, spoke)
            item.setToolTip(0, "Klick: gemeinsame Tickets zeigen, Doppelklick: in die Mitte setzen")
            self._contacts.addTopLevelItem(item)
        # Genau so hoch wie die Zeilen - die Ticketliste bekommt den Rest.
        rows = max(1, self._contacts.topLevelItemCount())
        header = self._contacts.header().sizeHint().height()
        row = self._contacts.sizeHintForRow(0) if self._contacts.topLevelItemCount() else 20
        self._contacts.setFixedHeight(header + rows * max(row, 18) + 6)

    def contact_names(self) -> list[str]:
        """Die Namen in der Kontaktliste, fuer Tests."""
        items = (self._contacts.topLevelItem(row) for row in range(self._contacts.topLevelItemCount()))
        return [item.text(0) for item in items if item is not None]

    def _on_contact_clicked(self, item: QTreeWidgetItem) -> None:
        spoke = item.data(0, _SPOKE_ROLE)
        if isinstance(spoke, Spoke):
            self.show_tickets(spoke, BOTH)

    def _on_contact_activated(self, item: QTreeWidgetItem) -> None:
        spoke = item.data(0, _SPOKE_ROLE)
        if isinstance(spoke, Spoke) and spoke.person is not None:
            self.person_clicked.emit(spoke.person.account_id, spoke.person.name)

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

    def _text(self, text: str, color: str, bold: bool = False, size: float = 0.0) -> QGraphicsSimpleTextItem:
        item = self._scene.addSimpleText(text)
        item.setBrush(QBrush(QColor(color)))
        font = QFont(self.font())
        font.setBold(bold)
        if size > 0:
            font.setPointSizeF(size)
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
        """Drei Viertel fuer den Stern, ein Viertel fuer die Listen."""
        width = self._split.width()
        if width > 0:
            self._split.setSizes([width * 3 // 4, width - width * 3 // 4])
        if self._canvas is not None:
            self._canvas.fit()

    def _clear_scene(self) -> None:
        self._groups = []
        self._dimmable = []
        self._scene.clear()

    def _hover(self, group: int, active: bool) -> None:
        """Blendet beim Hover alles aus, was nicht zur Speiche unter der Maus gehoert."""
        keep = set(map(id, self._groups[group])) if active and 0 <= group < len(self._groups) else None
        for item in self._dimmable:
            item.setOpacity(1.0 if keep is None or id(item) in keep else _DIMMED)

    def _draw(self, star: FlowStar, refit: bool = False) -> None:
        self._clear_scene()
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
            group: list[QGraphicsItem] = []
            self._groups.append(group)
            self._draw_arrows(index, spoke, origin, point, top, colors, group)
            self._draw_node(index, spoke, point, colors, group)

        center = _Node(origin, _CENTER, None)
        # accent_subtle ist ein CSS-rgba-Wert, den QColor nicht liest (ergibt
        # Schwarz) - deshalb der Akzent mit eigener Deckkraft.
        fill = QColor(colors.accent)
        fill.setAlphaF(0.22)
        center.setBrush(QBrush(fill))
        ring = QPen(QColor(colors.accent), 2.5)
        center.set_pens(ring, ring)
        center.setToolTip(star.center.name)
        center.setZValue(3)
        self._scene.addItem(center)
        self._decorate(star.center.account_id, star.center.name, origin, _CENTER, colors, z=4)
        label = self._text(_elide(star.center.name), colors.text_primary, bold=True)
        box = label.boundingRect()
        label.setPos(-box.width() / 2, _CENTER + 8)
        # Der Name liegt zwischen den Pfeilen nach unten - ein Kaestchen in
        # Hintergrundfarbe haelt ihn lesbar.
        plate = self._scene.addRect(
            QRectF(-box.width() / 2 - 6, _CENTER + 6, box.width() + 12, box.height() + 4),
            QPen(QColor(colors.border)),
            QBrush(QColor(colors.bg_primary)),
        )
        plate.setZValue(5)
        label.setZValue(6)

        if not spokes:
            hint = self._text("Keine Wege in diesem Zeitraum.", colors.text_secondary)
            hint.setPos(-hint.boundingRect().width() / 2, -_CENTER - 36)
        if refit or not canvas._zoomed:
            canvas.fit()
        self._ask_for_avatars(star)

    def _ask_for_avatars(self, star: FlowStar) -> None:
        """Meldet einmal je Kennung, welche Bilder fehlen."""
        if self._anonymized:
            return
        accounts = [star.center.account_id, *(s.person.account_id for s in star.spokes if s.person)]
        wanted = [a for a in accounts if a and a not in self._avatar_data and a not in self._asked]
        if wanted:
            self._asked.update(wanted)
            self.avatars_needed.emit(wanted)

    def _decorate(
        self, account: str, name: str, point: QPointF, radius: float, colors: Palette, z: float
    ) -> QGraphicsItem:
        """Profilbild im Kreis, sonst die Initialen."""
        data = None if self._anonymized else self._avatar_data.get(account)
        diameter = int(2 * radius - 6)
        pixmap = round_pixmap(data, diameter * 2) if data else None
        if pixmap is not None:
            image = QGraphicsPixmapItem(pixmap)
            # Doppelt aufgeloest und halb skaliert, damit es gezoomt scharf bleibt.
            image.setScale(0.5)
            image.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            image.setPos(point.x() - diameter / 2, point.y() - diameter / 2)
            image.setZValue(z)
            image.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            image.setAcceptHoverEvents(False)
            self._scene.addItem(image)
            return image
        text = self._text(initials(name), colors.text_secondary, bold=True, size=radius * 0.42)
        box = text.boundingRect()
        text.setPos(point.x() - box.width() / 2, point.y() - box.height() / 2)
        text.setZValue(z)
        text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        return text

    def _draw_node(self, index: int, spoke: Spoke, point: QPointF, colors: Palette, group: list[QGraphicsItem]) -> None:
        person = spoke.person
        on_click: Callable[[], None] | None = None
        if person is not None:
            account, name = person.account_id, person.name

            def on_click() -> None:
                self.person_clicked.emit(account, name)

        node = _Node(point, _NODE, on_click, functools.partial(self._hover, index))
        node.setBrush(QBrush(QColor(colors.bg_elevated)))
        node.set_pens(QPen(QColor(colors.border_hover), 1.5), QPen(QColor(colors.accent), 4.0))
        node.setZValue(3)
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
        if person is not None:
            inner = self._decorate(person.account_id, person.name, point, _NODE, colors, z=4)
        else:
            inner = self._text(f"+{spoke.members}", colors.text_secondary, bold=True, size=_NODE * 0.42)
            box = inner.boundingRect()
            inner.setPos(point.x() - box.width() / 2, point.y() - box.height() / 2)
            inner.setZValue(4)
            inner.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label = self._text(_elide(title), colors.text_secondary if person is None else colors.text_primary)
        width = label.boundingRect().width()
        # Unter dem Kreis, oben im Kreis darueber - sonst laeuft die Schrift in die Pfeile.
        y = point.y() + _NODE + 4 if point.y() >= -1 else point.y() - _NODE - label.boundingRect().height() - 4
        label.setPos(point.x() - width / 2, y)
        for item in (node, inner, label):
            group.append(item)
            self._dimmable.append(item)

    def _draw_arrows(
        self,
        index: int,
        spoke: Spoke,
        origin: QPointF,
        point: QPointF,
        top: int,
        colors: Palette,
        group: list[QGraphicsItem],
    ) -> None:
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
                start,
                end,
                10.0 + width * 1.4,
                pen,
                functools.partial(self.show_tickets, spoke, direction),
                functools.partial(self._hover, index),
            )
            arrow.setToolTip(f"{self._arrow_title(spoke, direction)}: {_tickets(len(keys))}\nKlick: Tickets anzeigen")
            arrow.setZValue(1)
            self._scene.addItem(arrow)
            count = self._text(str(len(keys)), color, bold=True)
            mid = QPointF((near.x() + far.x()) / 2, (near.y() + far.y()) / 2)
            box = count.boundingRect()
            shift = side * (width / 2 + 10)
            count.setPos(mid.x() + vx * shift - box.width() / 2, mid.y() + vy * shift - box.height() / 2)
            count.setZValue(2)
            for item in (arrow, count):
                group.append(item)
                self._dimmable.append(item)

    def _arrow_title(self, spoke: Spoke, direction: str) -> str:
        center = self._star.center.name if self._star is not None else ""
        other = spoke.person.name if spoke.person is not None else f"Sonstige ({spoke.members})"
        if direction == BOTH:
            return f"{center} und {other}"
        return f"{center} an {other}" if direction == OUT else f"{other} an {center}"

    def show_tickets(self, spoke: Spoke, direction: str) -> None:
        """Fuellt die Liste mit den Tickets eines Pfeils, BOTH = beide Richtungen."""
        if direction == BOTH:
            keys: tuple[str, ...] = tuple(dict.fromkeys((*spoke.outgoing, *spoke.incoming)))
        else:
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
